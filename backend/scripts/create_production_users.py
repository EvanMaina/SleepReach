"""
Create Production Users
=======================
Creates admin users WITHOUT deleting existing ones.
Uses INSERT ... ON CONFLICT to safely upsert.

Usage (ECS one-time task):
    python /app/scripts/create_production_users.py
"""

import os
import sys
from datetime import datetime, timezone, timedelta

import bcrypt
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL", "")

USERS = [
    {
        "email": "rpatel@tmsinstitute.co",
        "first_name": "R",
        "last_name": "Patel",
        "role": "primary_admin",
        "password": "TMS@2025!Change",
    },
    {
        "email": "rlpatel@tmsinstitute.co",
        "first_name": "RL",
        "last_name": "Patel",
        "role": "primary_admin",
        "password": "TMS@2025!Change",
    },
    {
        "email": "emwaniki@tmsinstitute.co",
        "first_name": "Evans",
        "last_name": "Mwaniki",
        "role": "administrator",
        "password": "TMS@2025!Change",
    },
]

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def main():
    print("=" * 60)
    print("  CREATE PRODUCTION USERS")
    print("=" * 60)

    if not DATABASE_URL:
        print("  [FAIL] DATABASE_URL not set")
        sys.exit(1)

    print("\n1. Connecting to database...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        cur = conn.cursor()
        print("  [OK] Connected")
    except Exception as e:
        print(f"  [FAIL] Connection failed: {e}")
        sys.exit(1)

    # Check users table exists
    cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='users')")
    if not cur.fetchone()[0]:
        print("  [FAIL] 'users' table does not exist. Run init_database.py first.")
        sys.exit(1)

    expires_at = datetime.now(timezone.utc) + timedelta(hours=48)

    print(f"\n2. Creating {len(USERS)} user(s)...")
    for user in USERS:
        email = user["email"]
        password_hash = hash_password(user["password"])

        print(f"\n  User: {email}")
        print(f"    Role: {user['role']}")
        print(f"    Name: {user['first_name']} {user['last_name']}")

        try:
            cur.execute("""
                INSERT INTO users (
                    email, password_hash, first_name, last_name,
                    role, status, must_change_password, password_expires_at,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (email) DO UPDATE SET
                    password_hash = EXCLUDED.password_hash,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    role = EXCLUDED.role,
                    status = EXCLUDED.status,
                    must_change_password = EXCLUDED.must_change_password,
                    password_expires_at = EXCLUDED.password_expires_at,
                    updated_at = NOW()
                RETURNING id;
            """, (
                email, password_hash, user["first_name"], user["last_name"],
                user["role"], "active", True, expires_at,
            ))
            user_id = cur.fetchone()[0]
            print(f"    [OK] User ID: {user_id}")

            # Create preferences if not exist
            cur.execute("""
                INSERT INTO user_preferences (user_id)
                VALUES (%s)
                ON CONFLICT (user_id) DO NOTHING;
            """, (str(user_id),))

        except Exception as e:
            conn.rollback()
            print(f"    [FAIL] {e}")
            sys.exit(1)

    conn.commit()

    # Verify
    print("\n3. Verification:")
    cur.execute("SELECT id, email, role, status, must_change_password FROM users ORDER BY id")
    users = cur.fetchall()
    print(f"  Total users: {len(users)}")
    for u in users:
        print(f"    - ID={u[0]} | {u[1]} | role={u[2]} | status={u[3]} | must_change_pw={u[4]}")

    conn.close()

    print()
    print("=" * 60)
    print("  PRODUCTION USERS CREATED SUCCESSFULLY")
    print("=" * 60)
    print()
    for user in USERS:
        print(f"  Email: {user['email']}")
        print(f"  Password: {user['password']}")
        print(f"  Role: {user['role']}")
        print(f"  Must change password on first login: Yes")
        print()


if __name__ == "__main__":
    main()
