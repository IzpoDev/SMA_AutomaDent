# auth.py — Utilidades de Autenticación JWT y Hash de Contraseñas
# ==============================================================================
# Contiene la lógica de hashing con bcrypt y generación/validación de tokens JWT.
# Usado internamente por las rutas de la API.
# ==============================================================================

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from jose import JWTError, jwt
from passlib.context import CryptContext

load_dotenv()

# ─── Configuración JWT ────────────────────────────────────────────────────────
SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY", "automadent-super-secret-change-in-production")
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("JWT_EXPIRE_MINUTES", 480))  # 8 horas

# ─── Contexto de hashing bcrypt ───────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ==============================================================================
#  FUNCIONES DE CONTRASEÑA
# ==============================================================================

def hash_password(plain_password: str) -> str:
    """Retorna el hash bcrypt de una contraseña en texto plano."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica si una contraseña en texto plano coincide con su hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ==============================================================================
#  FUNCIONES DE TOKEN JWT
# ==============================================================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Genera un token JWT firmado con los datos proporcionados.
    
    Args:
        data: Payload del token (debe incluir al menos 'sub').
        expires_delta: Duración del token. Usa el valor por defecto si no se especifica.
    
    Returns:
        Token JWT como string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decodifica y valida un token JWT.
    
    Returns:
        Payload del token si es válido, None si expiró o es inválido.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
