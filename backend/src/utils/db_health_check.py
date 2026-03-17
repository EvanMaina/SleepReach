"""
Database Health Check Utility

Provides comprehensive health checks for PostgreSQL database.
Used for monitoring, debugging, and ensuring HIPAA compliance.
"""

import sys
import os
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError

from src.core.database import engine, SessionLocal
from src.core.config import settings

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health check status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class CheckResult:
    """Result of a single health check."""
    name: str
    status: HealthStatus
    message: str
    details: Optional[Dict[str, Any]] = None
    duration_ms: Optional[float] = None


class DatabaseHealthCheck:
    """
    Comprehensive database health checker.
    
    Performs various checks to ensure:
    - Database connectivity
    - Schema integrity
    - Performance metrics
    - Security configurations
    """
    
    def __init__(self):
        self.results: List[CheckResult] = []
    
    def run_all_checks(self) -> Dict[str, Any]:
        """
        Run all health checks and return comprehensive report.
        
        Returns:
            Dictionary with overall status and individual check results
        """
        self.results = []
        
        # Core connectivity checks
        self._check_connection()
        self._check_read_write()
        
        # Schema checks
        self._check_tables_exist()
        self._check_required_columns()
        self._check_indexes()
        
        # Security checks
        self._check_rls_enabled()
        self._check_encryption_columns()
        
        # Performance checks
        self._check_connection_pool()
        self._check_table_sizes()
        
        # Determine overall status
        overall_status = self._calculate_overall_status()
        
        return {
            "status": overall_status.value,
            "timestamp": datetime.utcnow().isoformat(),
            "database": settings.database_url.split("/")[-1] if "/" in settings.database_url else "unknown",
            "environment": settings.environment,
            "checks": [
                {
                    "name": r.name,
                    "status": r.status.value,
                    "message": r.message,
                    "details": r.details,
                    "duration_ms": r.duration_ms
                }
                for r in self.results
            ]
        }
    
    def _calculate_overall_status(self) -> HealthStatus:
        """Calculate overall health status from individual checks."""
        if any(r.status == HealthStatus.UNHEALTHY for r in self.results):
            return HealthStatus.UNHEALTHY
        if any(r.status == HealthStatus.DEGRADED for r in self.results):
            return HealthStatus.DEGRADED
        if all(r.status == HealthStatus.HEALTHY for r in self.results):
            return HealthStatus.HEALTHY
        return HealthStatus.UNKNOWN
    
    def _check_connection(self):
        """Check basic database connectivity."""
        start = datetime.now()
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                assert result.scalar() == 1
            
            duration = (datetime.now() - start).total_seconds() * 1000
            self.results.append(CheckResult(
                name="database_connection",
                status=HealthStatus.HEALTHY,
                message="Database connection successful",
                duration_ms=round(duration, 2)
            ))
        except Exception as e:
            self.results.append(CheckResult(
                name="database_connection",
                status=HealthStatus.UNHEALTHY,
                message=f"Database connection failed: {str(e)}"
            ))
    
    def _check_read_write(self):
        """Check read/write capability."""
        try:
            session = SessionLocal()
            try:
                # Try to read from leads table
                result = session.execute(text("SELECT COUNT(*) FROM leads"))
                count = result.scalar()
                
                self.results.append(CheckResult(
                    name="read_write_access",
                    status=HealthStatus.HEALTHY,
                    message="Read access confirmed",
                    details={"leads_count": count}
                ))
            finally:
                session.close()
        except Exception as e:
            self.results.append(CheckResult(
                name="read_write_access",
                status=HealthStatus.UNHEALTHY,
                message=f"Read/write check failed: {str(e)}"
            ))
    
    def _check_tables_exist(self):
        """Verify required tables exist."""
        required_tables = ['leads', 'audit_logs']
        
        try:
            inspector = inspect(engine)
            existing_tables = inspector.get_table_names()
            
            missing = [t for t in required_tables if t not in existing_tables]
            
            if missing:
                self.results.append(CheckResult(
                    name="required_tables",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Missing tables: {missing}",
                    details={"missing": missing, "existing": existing_tables}
                ))
            else:
                self.results.append(CheckResult(
                    name="required_tables",
                    status=HealthStatus.HEALTHY,
                    message="All required tables exist",
                    details={"tables": required_tables}
                ))
        except Exception as e:
            self.results.append(CheckResult(
                name="required_tables",
                status=HealthStatus.UNHEALTHY,
                message=f"Table check failed: {str(e)}"
            ))
    
    def _check_required_columns(self):
        """Verify required columns exist in leads table."""
        required_columns = [
            'id', 'lead_number', 'first_name_encrypted', 'email_encrypted',
            'phone_encrypted', 'condition', 'symptom_duration', 'has_insurance',
            'zip_code', 'urgency', 'hipaa_consent', 'score', 'priority',
            'status', 'created_at', 'updated_at'
        ]
        
        try:
            inspector = inspect(engine)
            columns = [col['name'] for col in inspector.get_columns('leads')]
            
            missing = [c for c in required_columns if c not in columns]
            
            if missing:
                self.results.append(CheckResult(
                    name="required_columns",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Missing columns in leads table: {missing}",
                    details={"missing": missing}
                ))
            else:
                self.results.append(CheckResult(
                    name="required_columns",
                    status=HealthStatus.HEALTHY,
                    message="All required columns exist",
                    details={"column_count": len(columns)}
                ))
        except Exception as e:
            self.results.append(CheckResult(
                name="required_columns",
                status=HealthStatus.UNHEALTHY,
                message=f"Column check failed: {str(e)}"
            ))
    
    def _check_indexes(self):
        """Verify required indexes exist."""
        try:
            inspector = inspect(engine)
            indexes = inspector.get_indexes('leads')
            index_names = [idx['name'] for idx in indexes]
            
            # Check for key indexes
            has_priority_idx = any('priority' in (idx.get('name', '') or '').lower() 
                                  for idx in indexes)
            has_status_idx = any('status' in (idx.get('name', '') or '').lower() 
                                for idx in indexes)
            
            if has_priority_idx and has_status_idx:
                self.results.append(CheckResult(
                    name="database_indexes",
                    status=HealthStatus.HEALTHY,
                    message="Required indexes exist",
                    details={"index_count": len(indexes)}
                ))
            else:
                self.results.append(CheckResult(
                    name="database_indexes",
                    status=HealthStatus.DEGRADED,
                    message="Some recommended indexes may be missing",
                    details={"indexes": index_names}
                ))
        except Exception as e:
            self.results.append(CheckResult(
                name="database_indexes",
                status=HealthStatus.UNKNOWN,
                message=f"Index check failed: {str(e)}"
            ))
    
    def _check_rls_enabled(self):
        """Check if Row Level Security is enabled."""
        try:
            session = SessionLocal()
            try:
                result = session.execute(text("""
                    SELECT relname, relrowsecurity 
                    FROM pg_class 
                    WHERE relname IN ('leads', 'audit_logs')
                """))
                rows = result.fetchall()
                
                rls_status = {row[0]: row[1] for row in rows}
                
                all_enabled = all(rls_status.values())
                
                self.results.append(CheckResult(
                    name="row_level_security",
                    status=HealthStatus.HEALTHY if all_enabled else HealthStatus.DEGRADED,
                    message="RLS enabled on all tables" if all_enabled else "RLS not fully configured",
                    details=rls_status
                ))
            finally:
                session.close()
        except Exception as e:
            self.results.append(CheckResult(
                name="row_level_security",
                status=HealthStatus.UNKNOWN,
                message=f"RLS check failed: {str(e)}"
            ))
    
    def _check_encryption_columns(self):
        """Verify PHI columns are encrypted type (BYTEA)."""
        phi_columns = ['first_name_encrypted', 'last_name_encrypted', 
                       'email_encrypted', 'phone_encrypted']
        
        try:
            inspector = inspect(engine)
            columns = {col['name']: col for col in inspector.get_columns('leads')}
            
            non_bytea = []
            for col_name in phi_columns:
                if col_name in columns:
                    col_type = str(columns[col_name]['type']).upper()
                    if 'BYTEA' not in col_type and 'BINARY' not in col_type:
                        non_bytea.append(col_name)
            
            if non_bytea:
                self.results.append(CheckResult(
                    name="phi_encryption_columns",
                    status=HealthStatus.UNHEALTHY,
                    message=f"PHI columns not using BYTEA: {non_bytea}",
                    details={"non_encrypted": non_bytea}
                ))
            else:
                self.results.append(CheckResult(
                    name="phi_encryption_columns",
                    status=HealthStatus.HEALTHY,
                    message="All PHI columns use encrypted storage type",
                    details={"columns": phi_columns}
                ))
        except Exception as e:
            self.results.append(CheckResult(
                name="phi_encryption_columns",
                status=HealthStatus.UNKNOWN,
                message=f"Encryption column check failed: {str(e)}"
            ))
    
    def _check_connection_pool(self):
        """Check connection pool status."""
        try:
            pool = engine.pool
            
            self.results.append(CheckResult(
                name="connection_pool",
                status=HealthStatus.HEALTHY,
                message="Connection pool configured",
                details={
                    "pool_size": pool.size(),
                    "checked_in": pool.checkedin(),
                    "checked_out": pool.checkedout(),
                    "overflow": pool.overflow()
                }
            ))
        except Exception as e:
            self.results.append(CheckResult(
                name="connection_pool",
                status=HealthStatus.UNKNOWN,
                message=f"Pool check failed: {str(e)}"
            ))
    
    def _check_table_sizes(self):
        """Check table sizes for monitoring."""
        try:
            session = SessionLocal()
            try:
                result = session.execute(text("""
                    SELECT 
                        relname as table_name,
                        pg_size_pretty(pg_total_relation_size(relid)) as total_size,
                        n_live_tup as row_count
                    FROM pg_stat_user_tables 
                    WHERE relname IN ('leads', 'audit_logs')
                """))
                rows = result.fetchall()
                
                table_info = {
                    row[0]: {"size": row[1], "rows": row[2]}
                    for row in rows
                }
                
                self.results.append(CheckResult(
                    name="table_sizes",
                    status=HealthStatus.HEALTHY,
                    message="Table size information retrieved",
                    details=table_info
                ))
            finally:
                session.close()
        except Exception as e:
            self.results.append(CheckResult(
                name="table_sizes",
                status=HealthStatus.UNKNOWN,
                message=f"Table size check failed: {str(e)}"
            ))


def run_health_check() -> Dict[str, Any]:
    """
    Run database health check and return results.
    
    Returns:
        Dictionary with health check results
    """
    checker = DatabaseHealthCheck()
    return checker.run_all_checks()


def print_health_report():
    """Print formatted health check report to console (CLI usage only)."""
    import json

    report = run_health_check()

    status_emoji = {
        "healthy": "✅",
        "degraded": "⚠️",
        "unhealthy": "❌",
        "unknown": "❓"
    }

    logger.info("=" * 60)
    logger.info("NeuroReach AI - Database Health Check")
    logger.info("=" * 60)
    logger.info("Overall Status: %s %s", status_emoji.get(report['status'], '❓'), report['status'].upper())
    logger.info("Timestamp: %s", report['timestamp'])
    logger.info("Database: %s", report['database'])
    logger.info("Environment: %s", report['environment'])

    for check in report['checks']:
        emoji = status_emoji.get(check['status'], '❓')
        logger.info("%s %s — %s: %s", emoji, check['name'], check['status'], check['message'])
        if check.get('duration_ms'):
            logger.info("   Duration: %sms", check['duration_ms'])
        if check.get('details'):
            logger.info("   Details: %s", check['details'])

    return report


# =============================================================================
# CLI Entry Point
# =============================================================================

if __name__ == "__main__":
    import json
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    parser = argparse.ArgumentParser(description="Database Health Check")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--check", type=str, help="Run specific check only")
    
    args = parser.parse_args()
    
    if args.json:
        report = run_health_check()
        print(json.dumps(report, indent=2))
    else:
        report = print_health_report()
        
        # Exit with appropriate code
        if report['status'] == 'healthy':
            sys.exit(0)
        elif report['status'] == 'degraded':
            sys.exit(1)
        else:
            sys.exit(2)
