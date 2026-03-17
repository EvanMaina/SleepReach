"""
Setup Fresh Admin Account
========================
Creates an admin account with a temporary password.
Clears ALL existing users first (fresh start).

Usage (inside Docker):
    docker compose exec backend python /app/scripts/setup_fresh_admin.py --email admin@clinic.com
    docker compose exec backend python /app/scripts/setup_fresh_admin.py --email admin@clinic.com --role primary_admin
    docker compose exec backend python /app/scripts/setup_fresh_admin.py --email evans@clinic.com --first-name Evans --last-name Mwaniki

Usage (outside Docker, from project root):
    python backend/scripts/setup_fresh_admin.py --email admin@clinic.com --role administrator

Flags:
    --email      EMAIL   (required) The admin's email address
    --role       ROLE    (optional) One of: primary_admin, administrator, coordinator, specialist
                         Default: primary_admin
    --first-name NAME    (optional) First name. If omitted, derived from email.
    --last-name  NAME    (optional) Last name. If omitted, derived from email.
"""

import argparse
import sys
import os
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import bcrypt
import psycopg2

# =============================================================================
# Configuration -- auto-detects Docker vs local via DATABASE_URL
# =============================================================================

DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL:
    # Parse DATABASE_URL (e.g. postgresql://user:pass@host:port/dbname)
    parsed = urlparse(DATABASE_URL)
    DB_HOST = parsed.hostname or "localhost"
    DB_PORT = str(parsed.port or 5432)
    DB_NAME = parsed.path.lstrip("/") or "neuroreach"
    DB_USER = parsed.username or "neuroreach"
    DB_PASSWORD = parsed.password or "neuroreach_dev_password"
else:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "neuroreach")
    DB_USER = os.getenv("DB_USER", "neuroreach")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "neuroreach_dev_password")

# SMTP config -- uses SMTP_HOST (matches backend/.env) with fallback
SMTP_HOST = os.getenv("SMTP_HOST", os.getenv("MAILDEV_HOST", "localhost"))
SMTP_PORT = int(os.getenv("SMTP_PORT", os.getenv("MAILDEV_PORT", "1025")))

VALID_ROLES = {"primary_admin", "administrator", "coordinator", "specialist"}
TEMP_PASSWORD_EXPIRY_HOURS = 48
LOGIN_URL = os.getenv("LOGIN_URL", "http://localhost:5173")

# =============================================================================
# Helpers
# =============================================================================


def hash_password(password: str) -> str:
    """Hash password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def generate_temp_password() -> str:
    """Generate a readable temporary password (12 chars URL-safe)."""
    return secrets.token_urlsafe(9)


def parse_name_from_email(email: str) -> tuple:
    """
    Derive a first/last name from the email local part.
    Examples:
        admin@clinic.com       -> ("Admin", "User")
        jane.smith@clinic.com  -> ("Jane", "Smith")
        jsmith@clinic.com      -> ("Jsmith", "User")
    """
    local = email.split("@")[0]
    if "." in local:
        parts = local.split(".", 1)
        return parts[0].capitalize(), parts[1].capitalize()
    return local.capitalize(), "User"


def send_invitation_email(email, first_name, last_name, temp_password, role):
    """Send invitation email via SMTP (MailDev in dev, real SMTP in prod). Best-effort."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Welcome to TMS NeuroReach -- Your Account Has Been Created"
    msg["From"] = "noreply@tmsinstitute.co"
    msg["To"] = email

    role_label = role.replace("_", " ").title()

    text = (
        f"Hi {first_name} {last_name},\n\n"
        f"An administrator has created your TMS NeuroReach account.\n\n"
        f"Role: {role_label}\n"
        f"Email (Username): {email}\n"
        f"Temporary Password: {temp_password}\n\n"
        f"Log in at: {LOGIN_URL}\n\n"
        f"Important: You will be prompted to change this temporary password on your "
        f"first login. This password expires in {TEMP_PASSWORD_EXPIRY_HOURS} hours.\n\n"
        f"-- TMS Institute of Arizona Team"
    )

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0; padding:0; background-color:#f5f5f5; font-family:Arial, Helvetica, sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f5f5f5; padding:40px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.08);">
<tr><td style="background:linear-gradient(135deg, #3D6B6B 0%, #2d5252 100%); padding:32px 40px; text-align:center;">
    <h1 style="color:#ffffff; margin:0; font-size:24px; font-weight:bold;">TMS NeuroReach</h1>
    <p style="color:rgba(255,255,255,0.8); margin:8px 0 0; font-size:14px;">AI Platform</p>
</td></tr>
<tr><td style="padding:40px;">
    <h2 style="color:#1e3a5f; margin:0 0 16px; font-size:20px;">Welcome to TMS NeuroReach!</h2>
    <p style="color:#555; line-height:1.6;">Hi <strong>{first_name} {last_name}</strong>,</p>
    <p style="color:#555; line-height:1.6;">An administrator has created your TMS NeuroReach account. Use the credentials below to log in for the first time.</p>
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f0f7f7; border-radius:8px; border:1px solid #d0e0e0; margin:24px 0;">
    <tr><td style="padding:24px;">
        <p style="color:#3D6B6B; font-weight:bold; margin:0 0 12px; font-size:14px; text-transform:uppercase; letter-spacing:0.5px;">Your Login Credentials</p>
        <table cellpadding="4" cellspacing="0">
            <tr><td style="color:#777; font-size:14px;">Role:</td><td style="color:#333; font-weight:bold; font-size:14px;">{role_label}</td></tr>
            <tr><td style="color:#777; font-size:14px;">Email:</td><td style="color:#333; font-weight:bold; font-size:14px;">{email}</td></tr>
            <tr><td style="color:#777; font-size:14px;">Temporary Password:</td><td style="color:#333; font-weight:bold; font-size:14px; font-family:monospace; background:#fff; padding:6px 10px; border-radius:4px; border:1px solid #ddd;">{temp_password}</td></tr>
        </table>
    </td></tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:8px 0 24px;">
        <a href="{LOGIN_URL}" style="display:inline-block; background:linear-gradient(135deg, #1e3a5f, #2d5986); color:#ffffff; text-decoration:none; padding:14px 40px; border-radius:8px; font-weight:bold; font-size:16px;">Log In to Your Account</a>
    </td></tr></table>
    <div style="background-color:#fff8e6; border:1px solid #ffd54f; border-radius:8px; padding:16px; margin:0 0 20px;">
        <p style="color:#856404; margin:0; font-size:13px; line-height:1.5;">
            <strong>Important:</strong> You will be prompted to change this temporary password on your first login. This temporary password expires in {TEMP_PASSWORD_EXPIRY_HOURS} hours.
        </p>
    </div>
    <p style="color:#777; font-size:13px;">If you have any questions, contact your administrator.</p>
</td></tr>
<tr><td style="background-color:#f8f9fa; padding:20px 40px; text-align:center; border-top:1px solid #eee;">
    <p style="color:#999; font-size:12px; margin:0;">2026 TMS Institute of Arizona. All rights reserved.</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""

    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.sendmail("noreply@tmsinstitute.co", [email], msg.as_string())

    print(f"  [OK] Invitation email sent to {email} via SMTP ({SMTP_HOST}:{SMTP_PORT})")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Create a fresh admin account for NeuroReach AI."
    )
    parser.add_argument(
        "--email",
        required=True,
        help="The admin's email address (required)",
    )
    parser.add_argument(
        "--role",
        default="primary_admin",
        choices=sorted(VALID_ROLES),
        help="The user role to assign (default: primary_admin)",
    )
    parser.add_argument(
        "--first-name",
        default=None,
        help="First name (optional). If omitted, derived from the email address.",
    )
    parser.add_argument(
        "--last-name",
        default=None,
        help="Last name (optional). If omitted, derived from the email address.",
    )
    args = parser.parse_args()

    email = args.email.strip().lower()
    role = args.role.strip().lower()

    if role not in VALID_ROLES:
        print(f"  [FAIL] Invalid role: {role}. Must be one of: {', '.join(sorted(VALID_ROLES))}")
        sys.exit(1)

    # Use explicit names if provided, otherwise derive from email
    derived_first, derived_last = parse_name_from_email(email)
    first_name = args.first_name.strip() if args.first_name else derived_first
    last_name = args.last_name.strip() if args.last_name else derived_last

    print("=" * 60)
    print("  SETUP FRESH ADMIN ACCOUNT")
    print("=" * 60)
    print()

    # Connect to database
    print("1. Connecting to database...")
    print(f"   Host: {DB_HOST}:{DB_PORT}  DB: {DB_NAME}  User: {DB_USER}")
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
            user=DB_USER, password=DB_PASSWORD
        )
        conn.autocommit = False
        cur = conn.cursor()
        print("  [OK] Connected to database")
    except Exception as e:
        print(f"  [FAIL] Database connection failed: {e}")
        sys.exit(1)

    # Clear all existing users (and related tables)
    print("\n2. Clearing all existing users...")
    try:
        cur.execute("SELECT COUNT(*) FROM users;")
        count = cur.fetchone()[0]
        print(f"  Found {count} existing user(s)")

        # Delete in order to respect foreign keys
        cur.execute("DELETE FROM password_reset_tokens;")
        cur.execute("DELETE FROM user_preferences;")
        cur.execute("DELETE FROM users;")
        conn.commit()
        print(f"  [OK] Cleared {count} user(s) and related data")
    except Exception as e:
        conn.rollback()
        print(f"  [FAIL] Failed to clear users: {e}")
        sys.exit(1)

    # Generate temp password
    temp_password = generate_temp_password()
    password_hash = hash_password(temp_password)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=TEMP_PASSWORD_EXPIRY_HOURS)

    # Create admin account
    print(f"\n3. Creating {role.replace('_', ' ')} account...")
    print(f"  Email:    {email}")
    print(f"  Name:     {first_name} {last_name}")
    print(f"  Role:     {role}")
    print(f"  Temp PW:  {temp_password}")
    print(f"  Expires:  {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    try:
        cur.execute("""
            INSERT INTO users (
                email, password_hash, first_name, last_name,
                role, status, must_change_password, password_expires_at,
                created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            RETURNING id;
        """, (
            email, password_hash, first_name, last_name,
            role, "active", True, expires_at,
        ))
        user_id = cur.fetchone()[0]

        # Create default preferences
        cur.execute("""
            INSERT INTO user_preferences (user_id) VALUES (%s);
        """, (str(user_id),))

        conn.commit()
        print(f"  [OK] User created (ID: {user_id})")
    except Exception as e:
        conn.rollback()
        print(f"  [FAIL] Failed to create user: {e}")
        sys.exit(1)

    # Send invitation email (best-effort)
    print("\n4. Sending invitation email...")
    try:
        send_invitation_email(email, first_name, last_name, temp_password, role)
    except Exception as e:
        print(f"  [WARN] Email failed (non-fatal): {e}")
        print(f"     You can still log in with the temp password above.")

    # Verify
    print("\n5. Verification...")
    cur.execute("SELECT id, email, role, status, must_change_password FROM users;")
    users = cur.fetchall()
    print(f"  Total users: {len(users)}")
    for u in users:
        print(f"    - {u[1]} | role={u[2]} | status={u[3]} | must_change={u[4]}")

    conn.close()

    print()
    print("=" * 60)
    print("  SETUP COMPLETE!")
    print("=" * 60)
    print()
    print(f"  Login URL:    {LOGIN_URL}")
    print(f"  Email:        {email}")
    print(f"  Temp PW:      {temp_password}")
    print(f"  Role:         {role}")
    print()
    print("  NEXT STEPS:")
    print("  1. Log in with the temp password")
    print("  2. Set a new strong password when prompted")
    print("  3. Create additional users from Settings -> Users")
    print()


if __name__ == "__main__":
    main()
