"""
Authentication module for Kalkulai.
Handles user registration, login, password management with JWT tokens.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

# JWT handling (simple implementation without external deps)
import base64
import json

# Database path
DB_PATH = Path(__file__).parent.parent / "var" / "kalkulai.db"

# Secret key for JWT (should be in env in production)
JWT_SECRET = os.getenv("JWT_SECRET", "kalkulai-dev-secret-change-in-prod-" + secrets.token_hex(16))
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24 * 7  # 1 week


@dataclass
class User:
    id: int
    email: str
    name: str
    created_at: str
    updated_at: str


def _get_db() -> sqlite3.Connection:
    """Get database connection with row factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_tables() -> None:
    """Initialize authentication tables."""
    conn = _get_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)
        """)
        conn.commit()
        
        # Create default admin user if no users exist
        cursor = conn.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            _create_default_user(conn)
    finally:
        conn.close()


def _create_default_user(conn: sqlite3.Connection) -> None:
    """Create default admin user."""
    default_email = os.getenv("DEFAULT_USER_EMAIL", "admin@kalkulai.de")
    default_password = os.getenv("DEFAULT_USER_PASSWORD", "kalkulai2024")
    default_name = os.getenv("DEFAULT_USER_NAME", "Administrator")
    
    password_hash = hash_password(default_password)
    conn.execute(
        "INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)",
        (default_email, password_hash, default_name)
    )
    conn.commit()
    print(f"✅ Default user created: {default_email}")


def hash_password(password: str) -> str:
    """Hash password using SHA-256 with salt."""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return f"{salt}${pwd_hash.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash."""
    try:
        salt, stored_hash = password_hash.split('$')
        pwd_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        return hmac.compare_digest(pwd_hash.hex(), stored_hash)
    except (ValueError, AttributeError):
        return False


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')


def _base64url_decode(data: str) -> bytes:
    padding = 4 - len(data) % 4
    if padding != 4:
        data += '=' * padding
    return base64.urlsafe_b64decode(data)


def create_jwt(payload: Dict[str, Any]) -> str:
    """Create a JWT token."""
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    
    # Add expiry
    payload = {
        **payload,
        "exp": int(time.time()) + (JWT_EXPIRY_HOURS * 3600),
        "iat": int(time.time()),
    }
    
    header_b64 = _base64url_encode(json.dumps(header).encode())
    payload_b64 = _base64url_encode(json.dumps(payload).encode())
    
    signature_input = f"{header_b64}.{payload_b64}"
    signature = hmac.new(
        JWT_SECRET.encode(),
        signature_input.encode(),
        hashlib.sha256
    ).digest()
    signature_b64 = _base64url_encode(signature)
    
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def verify_jwt(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode a JWT token."""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        
        header_b64, payload_b64, signature_b64 = parts
        
        # Verify signature
        signature_input = f"{header_b64}.{payload_b64}"
        expected_sig = hmac.new(
            JWT_SECRET.encode(),
            signature_input.encode(),
            hashlib.sha256
        ).digest()
        
        actual_sig = _base64url_decode(signature_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        
        # Decode payload
        payload = json.loads(_base64url_decode(payload_b64))
        
        # Check expiry
        if payload.get("exp", 0) < time.time():
            return None
        
        return payload
    except Exception:
        return None


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Get user by email."""
    conn = _get_db()
    try:
        cursor = conn.execute(
            "SELECT id, email, password_hash, name, created_at, updated_at FROM users WHERE email = ?",
            (email.lower(),)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user by ID."""
    conn = _get_db()
    try:
        cursor = conn.execute(
            "SELECT id, email, name, created_at, updated_at FROM users WHERE id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate user and return user data if successful."""
    user = get_user_by_email(email.lower())
    if not user:
        return None
    
    if not verify_password(password, user["password_hash"]):
        return None
    
    # Remove password hash from response
    del user["password_hash"]
    return user


def create_user(email: str, password: str, name: str = "") -> Dict[str, Any]:
    """Create a new user."""
    conn = _get_db()
    try:
        password_hash = hash_password(password)
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)",
            (email.lower(), password_hash, name)
        )
        conn.commit()
        
        return {
            "id": cursor.lastrowid,
            "email": email.lower(),
            "name": name,
        }
    except sqlite3.IntegrityError:
        raise ValueError("Email already exists")
    finally:
        conn.close()


def update_user_email(user_id: int, new_email: str) -> bool:
    """Update user email."""
    conn = _get_db()
    try:
        conn.execute(
            "UPDATE users SET email = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_email.lower(), user_id)
        )
        conn.commit()
        return conn.total_changes > 0
    except sqlite3.IntegrityError:
        raise ValueError("Email already exists")
    finally:
        conn.close()


def update_user_password(user_id: int, new_password: str) -> bool:
    """Update user password."""
    conn = _get_db()
    try:
        password_hash = hash_password(new_password)
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (password_hash, user_id)
        )
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def update_user_name(user_id: int, new_name: str) -> bool:
    """Update user name."""
    conn = _get_db()
    try:
        conn.execute(
            "UPDATE users SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_name, user_id)
        )
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def verify_current_password(user_id: int, password: str) -> bool:
    """Verify current password for a user."""
    conn = _get_db()
    try:
        cursor = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        if not row:
            return False
        return verify_password(password, row["password_hash"])
    finally:
        conn.close()

