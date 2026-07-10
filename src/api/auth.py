# src/api/auth.py — Utilidades de Autenticación JWT y Hash de Contraseñas
# ==============================================================================
# Migrado de api/auth.py.
# Contiene hashing bcrypt y generación/validación de tokens JWT.
# ==============================================================================

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from src.utils.config import JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRE_MINUTES

# ─── Contexto de hashing bcrypt ───────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Retorna el hash bcrypt de una contraseña en texto plano."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica si una contraseña en texto plano coincide con su hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Genera un token JWT firmado con los datos proporcionados.

    Args:
        data: Payload del token (debe incluir al menos 'sub').
        expires_delta: Duración del token.

    Returns:
        Token JWT como string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=JWT_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decodifica y valida un token JWT.

    Returns:
        Payload del token si es válido, None si expiró o es inválido.
    """
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
