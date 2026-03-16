import hashlib
import os

import psycopg2


def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=int(os.getenv("DB_PORT", 5432)),
        database=os.getenv("DB_NAME", "airport"),
        user=os.getenv("DB_USER", "airport_user"),
        password=os.getenv("DB_PASS", "airport_dev_pass"),
    )


def hash_password(password: str) -> str:
    salt = os.urandom(32)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return (salt + pwd_hash).hex()


def verify_password(password: str, stored_hex: str) -> bool:
    try:
        combined = bytes.fromhex(stored_hex)
        salt = combined[:32]
        stored_hash = combined[32:]
        pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
        return pwd_hash == stored_hash
    except Exception:
        return False
