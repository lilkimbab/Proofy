from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

from app.core.config import settings


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_password(password: str, salt: bytes | None = None) -> str:
    final_salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), final_salt, 120000)
    return f"{final_salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        salt_hex, digest_hex = encoded.split("$", maxsplit=1)
    except ValueError:
        return False
    candidate = _hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate, encoded)


class AuthRepository(Protocol):
    def get_by_email(self, email: str) -> dict | None: ...
    def get_by_user_id(self, user_id: str) -> dict | None: ...
    def create_user(self, *, email: str, display_name: str, password_hash: str) -> dict: ...


@dataclass
class MemoryAuthRepository:
    users_by_email: dict[str, dict] = field(default_factory=dict)
    users_by_id: dict[str, dict] = field(default_factory=dict)

    def get_by_email(self, email: str) -> dict | None:
        user = self.users_by_email.get(_normalize_email(email))
        return dict(user) if user else None

    def get_by_user_id(self, user_id: str) -> dict | None:
        user = self.users_by_id.get(user_id)
        return dict(user) if user else None

    def create_user(self, *, email: str, display_name: str, password_hash: str) -> dict:
        normalized = _normalize_email(email)
        user = {
            "userId": f"user-{uuid4().hex[:12]}",
            "email": normalized,
            "displayName": display_name.strip() or normalized.split("@")[0],
            "passwordHash": password_hash,
        }
        self.users_by_email[normalized] = user
        self.users_by_id[user["userId"]] = user
        return dict(user)


class PostgresAuthRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self._ensure_schema()

    def _connect(self):
        import psycopg

        return psycopg.connect(self.database_url)

    def _ensure_schema(self) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.commit()

    def get_by_email(self, email: str) -> dict | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id, email, display_name, password_hash
                FROM auth_users
                WHERE email = %s
                """,
                (_normalize_email(email),),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                "userId": row[0],
                "email": row[1],
                "displayName": row[2],
                "passwordHash": row[3],
            }

    def get_by_user_id(self, user_id: str) -> dict | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id, email, display_name, password_hash
                FROM auth_users
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                "userId": row[0],
                "email": row[1],
                "displayName": row[2],
                "passwordHash": row[3],
            }

    def create_user(self, *, email: str, display_name: str, password_hash: str) -> dict:
        normalized = _normalize_email(email)
        with self._connect() as connection, connection.cursor() as cursor:
            user_id = f"user-{uuid4().hex[:12]}"
            cursor.execute(
                """
                INSERT INTO auth_users (user_id, email, display_name, password_hash)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    user_id,
                    normalized,
                    display_name.strip() or normalized.split("@")[0],
                    password_hash,
                ),
            )
            connection.commit()
        return {
            "userId": user_id,
            "email": normalized,
            "displayName": display_name.strip() or normalized.split("@")[0],
            "passwordHash": password_hash,
        }


class AuthService:
    def __init__(self, repository: AuthRepository):
        self.repository = repository

    def signup(self, email: str, password: str, display_name: str) -> dict:
        normalized = _normalize_email(email)
        if not normalized or "@" not in normalized:
            raise ValueError("올바른 이메일을 입력해 주세요.")
        if len(password) < 8:
            raise ValueError("비밀번호는 8자 이상으로 설정해 주세요.")
        if self.repository.get_by_email(normalized) is not None:
            raise ValueError("이미 가입된 이메일입니다.")
        user = self.repository.create_user(
            email=normalized,
            display_name=display_name,
            password_hash=_hash_password(password),
        )
        return {
            "session": {
                "userId": user["userId"],
                "email": user["email"],
                "displayName": user["displayName"],
            }
        }

    def login(self, email: str, password: str) -> dict:
        normalized = _normalize_email(email)
        user = self.repository.get_by_email(normalized)
        if user is None or not _verify_password(password, str(user["passwordHash"])):
            raise ValueError("이메일 또는 비밀번호가 맞지 않습니다.")
        return {
            "session": {
                "userId": user["userId"],
                "email": user["email"],
                "displayName": user["displayName"],
            }
        }

    def session(self, user_id: str) -> dict:
        user = self.repository.get_by_user_id(user_id)
        if user is None:
            return {
                "session": {
                    "userId": settings.demo_user_id,
                    "email": "",
                    "displayName": "Demo User",
                }
            }
        return {
            "session": {
                "userId": user["userId"],
                "email": user["email"],
                "displayName": user["displayName"],
            }
        }


def build_auth_repository() -> AuthRepository:
    if settings.storage_backend == "postgres":
        return PostgresAuthRepository(settings.database_url)
    return MemoryAuthRepository()


auth_service = AuthService(build_auth_repository())
