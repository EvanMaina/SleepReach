#!/usr/bin/env python3
"""
NeuroReach AI — Database Backup Script
Runs pg_dump and uploads to S3 bucket.
Designed to run inside ECS Fargate task (same VPC as RDS).

Usage:
    python backup_database.py [--type daily|weekly]

Environment variables required:
    DATABASE_URL  — PostgreSQL connection string
    AWS_REGION    — AWS region (default: us-east-2)
    S3_BACKUP_BUCKET — S3 bucket name (default: neuroreach-backups-prod)
"""

import os
import sys
import subprocess
import logging
import gzip
import boto3
from datetime import datetime, timezone
from urllib.parse import urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backup")

# Configuration
S3_BUCKET = os.environ.get("S3_BACKUP_BUCKET", "neuroreach-backups-prod")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-2")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
BACKUP_TYPE = "daily"  # daily or weekly


def parse_database_url(url: str) -> dict:
    """Parse DATABASE_URL into connection components."""
    parsed = urlparse(url)
    return {
        "host": parsed.hostname,
        "port": str(parsed.port or 5432),
        "user": parsed.username,
        "password": parsed.password,
        "database": parsed.path.lstrip("/"),
    }


def run_pg_dump(db_config: dict, output_file: str) -> bool:
    """Run pg_dump and compress the output."""
    env = os.environ.copy()
    env["PGPASSWORD"] = db_config["password"]

    cmd = [
        "pg_dump",
        "-h", db_config["host"],
        "-p", db_config["port"],
        "-U", db_config["user"],
        "-d", db_config["database"],
        "--format=custom",       # Custom format (supports parallel restore)
        "--compress=6",          # Compression level
        "--no-owner",            # Don't output ownership commands
        "--no-privileges",       # Don't output privilege commands
        "--verbose",
    ]

    logger.info(f"Running pg_dump for database: {db_config['database']} on {db_config['host']}")

    try:
        with open(output_file, "wb") as f:
            result = subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.PIPE,
                env=env,
                timeout=1800,  # 30 minute timeout
            )

        if result.returncode != 0:
            logger.error(f"pg_dump failed with return code {result.returncode}")
            logger.error(f"stderr: {result.stderr.decode('utf-8', errors='replace')}")
            return False

        file_size = os.path.getsize(output_file)
        logger.info(f"pg_dump completed. File size: {file_size / 1024 / 1024:.2f} MB")
        return True

    except subprocess.TimeoutExpired:
        logger.error("pg_dump timed out after 30 minutes")
        return False
    except FileNotFoundError:
        logger.error("pg_dump not found. Falling back to Python-based backup.")
        return run_python_backup(db_config, output_file)


def run_python_backup(db_config: dict, output_file: str) -> bool:
    """Fallback: Use psycopg2 to create a SQL dump when pg_dump is not available."""
    try:
        import psycopg2

        conn = psycopg2.connect(
            host=db_config["host"],
            port=db_config["port"],
            user=db_config["user"],
            password=db_config["password"],
            dbname=db_config["database"],
            sslmode="require",
        )
        cursor = conn.cursor()

        # Get all table names
        cursor.execute("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        tables = [row[0] for row in cursor.fetchall()]

        logger.info(f"Found {len(tables)} tables to backup")

        with gzip.open(output_file, "wt", encoding="utf-8") as f:
            f.write(f"-- NeuroReach AI Database Backup\n")
            f.write(f"-- Date: {datetime.now(timezone.utc).isoformat()}\n")
            f.write(f"-- Database: {db_config['database']}\n")
            f.write(f"-- Tables: {len(tables)}\n\n")

            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                logger.info(f"  Backing up {table} ({count} rows)")

                # Get column names
                cursor.execute(f"SELECT * FROM {table} LIMIT 0")
                columns = [desc[0] for desc in cursor.description]

                f.write(f"\n-- Table: {table} ({count} rows)\n")
                f.write(f"-- Columns: {', '.join(columns)}\n")

                if count > 0:
                    # Use COPY for efficient export
                    copy_sql = f"COPY {table} TO STDOUT WITH (FORMAT CSV, HEADER TRUE)"
                    f.write(f"-- BEGIN CSV DATA for {table}\n")
                    cursor.copy_expert(copy_sql, f)
                    f.write(f"\n-- END CSV DATA for {table}\n")

        cursor.close()
        conn.close()

        file_size = os.path.getsize(output_file)
        logger.info(f"Python backup completed. File size: {file_size / 1024 / 1024:.2f} MB")
        return True

    except ImportError:
        logger.error("psycopg2 not available for Python backup fallback")
        return False
    except Exception as e:
        logger.error(f"Python backup failed: {e}")
        return False


def upload_to_s3(local_file: str, s3_key: str) -> bool:
    """Upload backup file to S3."""
    try:
        s3 = boto3.client("s3", region_name=AWS_REGION)
        file_size = os.path.getsize(local_file)

        logger.info(f"Uploading {local_file} ({file_size / 1024 / 1024:.2f} MB) to s3://{S3_BUCKET}/{s3_key}")

        # Use multipart upload for large files
        from boto3.s3.transfer import TransferConfig
        config = TransferConfig(
            multipart_threshold=50 * 1024 * 1024,  # 50 MB
            max_concurrency=4,
        )

        s3.upload_file(
            local_file,
            S3_BUCKET,
            s3_key,
            Config=config,
            ExtraArgs={
                "ServerSideEncryption": "AES256",
                "Metadata": {
                    "backup-type": BACKUP_TYPE,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "ecs-scheduled-task",
                },
            },
        )

        logger.info(f"✅ Upload complete: s3://{S3_BUCKET}/{s3_key}")
        return True

    except Exception as e:
        logger.error(f"S3 upload failed: {e}")
        return False


def cleanup_old_local_files(directory: str, max_age_hours: int = 24):
    """Remove old backup files from local storage."""
    import glob
    now = datetime.now(timezone.utc).timestamp()
    for f in glob.glob(os.path.join(directory, "*.dump*")):
        if now - os.path.getmtime(f) > max_age_hours * 3600:
            os.remove(f)
            logger.info(f"Cleaned up old file: {f}")


def main():
    global BACKUP_TYPE

    # Parse arguments
    if len(sys.argv) > 1 and sys.argv[1] == "--type":
        BACKUP_TYPE = sys.argv[2] if len(sys.argv) > 2 else "daily"

    if not DATABASE_URL:
        logger.error("DATABASE_URL environment variable is required")
        sys.exit(1)

    # Parse database URL
    db_config = parse_database_url(DATABASE_URL)
    logger.info(f"Starting {BACKUP_TYPE} backup for database: {db_config['database']}")

    # Generate filenames
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    date_prefix = now.strftime("%Y/%m/%d")

    local_file = f"/tmp/neuroreach-backup-{timestamp}.dump"
    s3_key = f"rds/{BACKUP_TYPE}/{date_prefix}/neuroreach-{BACKUP_TYPE}-{timestamp}.dump"

    # Run backup
    success = run_pg_dump(db_config, local_file)
    if not success:
        logger.error("❌ Database backup failed!")
        sys.exit(1)

    # Upload to S3
    uploaded = upload_to_s3(local_file, s3_key)
    if not uploaded:
        logger.error("❌ S3 upload failed!")
        sys.exit(1)

    # Cleanup local file
    try:
        os.remove(local_file)
        logger.info(f"Cleaned up local file: {local_file}")
    except OSError:
        pass

    logger.info(f"🎉 {BACKUP_TYPE.capitalize()} backup completed successfully!")
    logger.info(f"   S3: s3://{S3_BUCKET}/{s3_key}")


if __name__ == "__main__":
    main()
