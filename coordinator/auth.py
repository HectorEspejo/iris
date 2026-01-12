"""
Iris Authentication

JWT-based authentication for users.
"""

import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import bcrypt
from pydantic import BaseModel
import structlog

from shared.models import User, UserCreate, UserLogin, TokenResponse, generate_id
from .database import db

logger = structlog.get_logger()

# Configuration - Load from environment variables
SECRET_KEY = os.environ.get("JWT_SECRET", "iris-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# Security scheme
security = HTTPBearer()


class TokenData(BaseModel):
    user_id: str
    email: str


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


def hash_password(password: str) -> str:
    """Hash a password."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[TokenData]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        email = payload.get("email")
        if user_id is None or email is None:
            return None
        return TokenData(user_id=user_id, email=email)
    except JWTError:
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """
    Dependency to get the current authenticated user.

    Usage:
        @app.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            return {"user_id": user.id}
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials
    token_data = decode_token(token)
    if token_data is None:
        raise credentials_exception

    user_data = await db.get_user_by_id(token_data.user_id)
    if user_data is None:
        raise credentials_exception

    return User(**user_data)


async def register_user(user_data: UserCreate) -> User:
    """
    Register a new user.

    Args:
        user_data: User registration data

    Returns:
        Created user

    Raises:
        HTTPException: If email already exists
    """
    # Check if email exists
    existing = await db.get_user_by_email(user_data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create user
    user_id = generate_id()
    password_hash = hash_password(user_data.password)

    user_record = await db.create_user(
        id=user_id,
        email=user_data.email,
        password_hash=password_hash
    )

    logger.info("user_registered", user_id=user_id, email=user_data.email)
    return User(**user_record)


async def login_user(credentials: UserLogin) -> TokenResponse:
    """
    Authenticate a user and return a token.

    Args:
        credentials: Login credentials

    Returns:
        Access token

    Raises:
        HTTPException: If credentials are invalid
    """
    user_data = await db.get_user_by_email(credentials.email)

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not verify_password(credentials.password, user_data["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Create token
    access_token = create_access_token(
        data={"sub": user_data["id"], "email": user_data["email"]}
    )

    logger.info("user_logged_in", user_id=user_data["id"], email=credentials.email)
    return TokenResponse(access_token=access_token)


async def get_user_info(user: User) -> dict:
    """Get full user information including stats."""
    tasks = await db.get_tasks_by_user(user.id, limit=1000)
    nodes = await db.get_nodes_by_owner(user.id)

    return {
        "id": user.id,
        "email": user.email,
        "membership_status": user.membership_status,
        "monthly_quota": user.monthly_quota,
        "created_at": user.created_at,
        "total_tasks": len(tasks),
        "nodes_count": len(nodes)
    }
