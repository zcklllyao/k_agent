"""安全工具：密码哈希、JWT、API Key 对称加密。"""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(raw: str) -> str:
    return _pwd.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return _pwd.verify(raw, hashed)


def _create_token(sub: str, expires: timedelta, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": sub, "type": token_type, "iat": now, "exp": now + expires}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(sub: str) -> str:
    return _create_token(
        sub, timedelta(minutes=settings.access_token_expire_minutes), "access"
    )


def create_refresh_token(sub: str) -> str:
    return _create_token(
        sub, timedelta(days=settings.refresh_token_expire_days), "refresh"
    )


def decode_token(token: str) -> Optional[dict[str, Any]]:
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except JWTError:
        return None


# ---- API Key 对称加密（Fernet）----
def _fernet() -> Fernet:
    return Fernet(settings.fernet_key.encode())


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def mask_secret(plain: str) -> str:
    """接口返回掩码，仅展示尾部 4 位。"""
    if not plain:
        return ""
    if len(plain) <= 4:
        return "*" * len(plain)
    return "*" * (len(plain) - 4) + plain[-4:]
