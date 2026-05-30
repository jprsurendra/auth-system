"""
scripts/create_superuser.py
────────────────────────────
Bootstrap the first admin user without going through
the registration flow.

Usage:
    docker-compose exec backend \
        python scripts/create_superuser.py \
        --email admin@example.com \
        --username admin \
        --password "StrongPass@123" \
        --full-name "Admin User" \
        --phone "+919876543210"
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, ".")

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.user import User


async def create_superuser(
    email:     str,
    username:  str,
    password:  str,
    full_name: str,
    phone:     str,
) -> None:
    async with AsyncSessionLocal() as db:
        # Check for existing user
        result = await db.execute(
            select(User).where(User.email == email)
        )
        if result.scalar_one_or_none():
            print(f"User with email {email} already exists.")
            return

        user = User(
            email=email,
            username=username,
            full_name=full_name,
            phone=phone,
            hashed_password=hash_password(password),
            email_verified=True,
            phone_verified=True,
            is_active=True,
            is_superuser=True,
        )
        db.add(user)
        await db.commit()
        print(f"Superuser created: {email}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--email",     required=True)
    parser.add_argument("--username",  required=True)
    parser.add_argument("--password",  required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--phone",     required=True)
    args = parser.parse_args()

    asyncio.run(create_superuser(
        email=args.email,
        username=args.username,
        password=args.password,
        full_name=args.full_name,
        phone=args.phone,
    ))
