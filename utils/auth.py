"""
Utilidades para autenticación JWT y manejo de contraseñas
"""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status


# Configuración de seguridad
SECRET_KEY = "tu-clave-secreta-super-segura-cambiala-en-produccion-123456789"  # ⚠️ CAMBIAR EN PRODUCCIÓN
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Contexto de encriptación para passwords
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ========== FUNCIONES DE PASSWORD ==========

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifica si una contraseña plana coincide con el hash
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Genera el hash de una contraseña
    Bcrypt tiene un límite de 72 bytes, truncamos si es necesario
    """
    # Bcrypt tiene un límite de 72 bytes
    if len(password.encode('utf-8')) > 72:
        password = password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    return pwd_context.hash(password)


# ========== FUNCIONES DE JWT ==========

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Crea un token de acceso JWT
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """
    Crea un token de refresco JWT con mayor duración
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    })
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str, token_type: str = "access") -> dict:
    """
    Verifica y decodifica un token JWT
    
    Args:
        token: El token JWT a verificar
        token_type: Tipo de token esperado ("access" o "refresh")
    
    Returns:
        dict: Payload del token decodificado
    
    Raises:
        HTTPException: Si el token es inválido o expirado
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Verificar tipo de token
        if payload.get("type") != token_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Tipo de token inválido. Se esperaba '{token_type}'",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Verificar expiración
        exp = payload.get("exp")
        if exp is None:
            raise credentials_exception
        
        if datetime.utcfromtimestamp(exp) < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expirado",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return payload
        
    except JWTError:
        raise credentials_exception


def decode_token(token: str) -> Optional[dict]:
    """
    Decodifica un token sin verificar (útil para debugging)
    """
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_signature": False})
    except JWTError:
        return None


# ========== CONFIGURACIÓN PERSONALIZABLE ==========

def configurar_seguridad(
    secret_key: Optional[str] = None,
    algorithm: Optional[str] = None,
    access_token_expire_minutes: Optional[int] = None,
    refresh_token_expire_days: Optional[int] = None
):
    """
    Permite configurar los parámetros de seguridad dinámicamente
    (útil para cargar desde variables de entorno)
    """
    global SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS
    
    if secret_key:
        SECRET_KEY = secret_key
    if algorithm:
        ALGORITHM = algorithm
    if access_token_expire_minutes:
        ACCESS_TOKEN_EXPIRE_MINUTES = access_token_expire_minutes
    if refresh_token_expire_days:
        REFRESH_TOKEN_EXPIRE_DAYS = refresh_token_expire_days


# ========== UTILIDADES ADICIONALES ==========

def generar_codigo_temporal(longitud: int = 6) -> str:
    """
    Genera un código temporal numérico para verificaciones
    """
    import random
    return ''.join([str(random.randint(0, 9)) for _ in range(longitud)])


def es_password_seguro(password: str) -> tuple[bool, list[str]]:
    """
    Valida si una contraseña cumple con los requisitos de seguridad
    
    Returns:
        tuple: (es_valido, lista_de_errores)
    """
    errores = []
    
    if len(password) < 8:
        errores.append("Debe tener al menos 8 caracteres")
    
    if not any(c.isupper() for c in password):
        errores.append("Debe contener al menos una mayúscula")
    
    if not any(c.islower() for c in password):
        errores.append("Debe contener al menos una minúscula")
    
    if not any(c.isdigit() for c in password):
        errores.append("Debe contener al menos un número")
    
    # Caracteres especiales (opcional)
    caracteres_especiales = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    if not any(c in caracteres_especiales for c in password):
        errores.append("Se recomienda incluir caracteres especiales")
    
    return (len(errores) == 0, errores)
