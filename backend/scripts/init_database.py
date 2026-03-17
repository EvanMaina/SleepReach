"""
Initialize Database Schema
==========================
Runs the combined SQL init scripts against the database.
All statements use IF NOT EXISTS / IF EXISTS, so this is idempotent.

Executes each statement individually so that non-critical failures
(e.g. expression index syntax issues) don't block table creation.

Usage (ECS one-time task):
    python /app/scripts/init_database.py
"""

import os
import re
import sys
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SQL_FILE = os.path.join(os.path.dirname(__file__), "combined_init.sql")


def split_sql_statements(sql: str) -> list[str]:
    """
    Split SQL into individual statements, respecting dollar-quoted strings
    and function bodies ($$...$$).
    """
    statements = []
    current = []
    in_dollar_quote = False
    dollar_tag = ""
    lines = sql.split("\n")

    for line in lines:
        stripped = line.strip()

        # Skip pure comment lines and empty lines when not in a statement
        if not current and (not stripped or stripped.startswith("--")):
            continue

        current.append(line)

        # Handle dollar quoting ($$, $func$, etc.)
        if not in_dollar_quote:
            # Check for opening dollar quote
            dollar_matches = re.findall(r'\$[a-zA-Z_]*\$', line)
            if dollar_matches:
                # If odd number of same dollar quotes on this line, we're entering a block
                for dm in dollar_matches:
                    count = line.count(dm)
                    if count % 2 == 1:
                        in_dollar_quote = True
                        dollar_tag = dm
                        break
        else:
            # Check for closing dollar quote
            if dollar_tag in line:
                count = line.count(dollar_tag)
                if count % 2 == 1:
                    in_dollar_quote = False
                    dollar_tag = ""

        # If not in dollar quote and line ends with semicolon, statement is complete
        if not in_dollar_quote and stripped.endswith(";"):
            stmt = "\n".join(current).strip()
            if stmt and not all(l.strip().startswith("--") or not l.strip() for l in current):
                statements.append(stmt)
            current = []

    # Handle any remaining content
    if current:
        stmt = "\n".join(current).strip()
        if stmt and not all(l.strip().startswith("--") or not l.strip() for l in current):
            statements.append(stmt)

    return statements


def main():
    print("=" * 60)
    print("  DATABASE INITIALIZATION")
    print("=" * 60)

    if not DATABASE_URL:
        print("  [FAIL] DATABASE_URL not set")
        sys.exit(1)

    # Read SQL
    print(f"\n1. Reading SQL from {SQL_FILE}...")
    if not os.path.exists(SQL_FILE):
        print(f"  [FAIL] SQL file not found: {SQL_FILE}")
        sys.exit(1)

    with open(SQL_FILE, "r", encoding="utf-8-sig") as f:
        sql = f.read()
    print(f"  [OK] Read {len(sql)} bytes of SQL")

    # CONCURRENTLY cannot run inside a transaction block.
    # Since we're initializing a fresh DB, regular CREATE INDEX is fine and faster.
    concurrently_count = sql.count(" CONCURRENTLY")
    if concurrently_count:
        sql = sql.replace(" CONCURRENTLY", "")
        print(f"  [OK] Stripped {concurrently_count} CONCURRENTLY keywords (not needed for fresh init)")

    # Split into individual statements
    statements = split_sql_statements(sql)
    print(f"  [OK] Split into {len(statements)} SQL statements")

    # Connect
    print("\n2. Connecting to database...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        cur = conn.cursor()
        print("  [OK] Connected")
    except Exception as e:
        print(f"  [FAIL] Connection failed: {e}")
        sys.exit(1)

    # Check tables before
    cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")
    before = cur.fetchone()[0]
    print(f"  Tables before: {before}")

    # Execute SQL statements individually
    print("\n3. Executing SQL statements...")
    success = 0
    failed = 0
    skipped_errors = []

    for i, stmt in enumerate(statements):
        # Get first meaningful line for logging
        first_line = ""
        for line in stmt.split("\n"):
            line = line.strip()
            if line and not line.startswith("--"):
                first_line = line[:80]
                break

        try:
            cur.execute(stmt)
            success += 1
        except Exception as e:
            failed += 1
            error_msg = str(e).strip().split("\n")[0]
            # Non-critical: indexes, comments, etc.
            is_critical = any(kw in first_line.upper() for kw in [
                "CREATE TABLE", "CREATE TYPE", "ALTER TABLE", "CREATE EXTENSION"
            ])
            if is_critical:
                print(f"  [CRITICAL FAIL] Statement {i+1}: {first_line}")
                print(f"    Error: {error_msg}")
                conn.close()
                sys.exit(1)
            else:
                skipped_errors.append((first_line, error_msg))
                # Reset connection state after error
                conn.rollback() if not conn.autocommit else None
                # Reconnect cursor after error
                try:
                    cur.close()
                    cur = conn.cursor()
                except Exception:
                    conn = psycopg2.connect(DATABASE_URL)
                    conn.autocommit = True
                    cur = conn.cursor()

    print(f"  [OK] Executed: {success} succeeded, {failed} non-critical failures")

    if skipped_errors:
        print(f"\n  Non-critical failures ({len(skipped_errors)}):")
        for fl, err in skipped_errors[:15]:
            print(f"    - {fl[:60]}...")
            print(f"      {err[:80]}")
        if len(skipped_errors) > 15:
            print(f"    ... and {len(skipped_errors) - 15} more")

    # Check tables after
    cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")
    after = cur.fetchone()[0]
    print(f"\n  Tables after: {after}")

    # List tables
    print("\n4. Tables in database:")
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    for row in cur.fetchall():
        print(f"    - {row[0]}")

    conn.close()

    print()
    print("=" * 60)
    print("  DATABASE INITIALIZATION COMPLETE")
    print(f"  Tables: {before} -> {after}")
    print(f"  Statements: {success} OK, {failed} skipped")
    print("=" * 60)

    # Fail if no tables were created
    if after == 0:
        print("\n  [FAIL] No tables created!")
        sys.exit(1)


if __name__ == "__main__":
    main()
