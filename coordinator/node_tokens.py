"""
Iris Node Enrollment Tokens

Generates and validates enrollment tokens for node registration.
Tokens are JWT-like structures with HMAC-SHA256 signatures.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()

# Token secret key - should be set via environment variable in production
TOKEN_SECRET = os.environ.get("NODE_TOKEN_SECRET", secrets.token_hex(32))


class TokenPayload(BaseModel):
    """Payload structure for enrollment tokens."""
    jti: str  # JWT ID - unique token identifier
    iat: int  # Issued at timestamp
    exp: Optional[int] = None  # Expiration timestamp (None = never expires)
    type: str = "node_enrollment"
    label: Optional[str] = None  # Optional human-readable label


class TokenInfo(BaseModel):
    """Information about a token for API responses."""
    id: str
    label: Optional[str]
    created_at: str
    expires_at: Optional[str]
    used: bool
    used_at: Optional[str]
    used_by_node_id: Optional[str]
    revoked: bool


class TokenValidationResult(BaseModel):
    """Result of token validation."""
    valid: bool
    token_id: Optional[str] = None
    error: Optional[str] = None
    coordinator_ws: Optional[str] = None


def _sign_payload(payload: str) -> str:
    """Create HMAC-SHA256 signature for payload."""
    signature = hmac.new(
        TOKEN_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(signature).decode().rstrip("=")


def _verify_signature(payload: str, signature: str) -> bool:
    """Verify HMAC-SHA256 signature."""
    # Pad signature if needed
    padding = 4 - len(signature) % 4
    if padding != 4:
        signature += "=" * padding

    expected_sig = _sign_payload(payload)
    return hmac.compare_digest(expected_sig, signature.rstrip("="))


def generate_token(
    label: Optional[str] = None,
    expires_in_days: Optional[int] = None
) -> tuple[str, TokenPayload]:
    """
    Generate a new enrollment token.

    Args:
        label: Optional human-readable label for the token
        expires_in_days: Optional expiration in days (None = never expires)

    Returns:
        Tuple of (token_string, payload)
    """
    now = datetime.utcnow()

    payload = TokenPayload(
        jti=secrets.token_urlsafe(16),
        iat=int(now.timestamp()),
        exp=int((now + timedelta(days=expires_in_days)).timestamp()) if expires_in_days else None,
        label=label
    )

    # Encode payload
    payload_json = payload.model_dump_json()
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")

    # Sign
    signature = _sign_payload(payload_b64)

    # Format: iris_v1.<payload>.<signature>
    token = f"iris_v1.{payload_b64}.{signature}"

    logger.info(
        "token_generated",
        token_id=payload.jti,
        label=label,
        expires=payload.exp
    )

    return token, payload


def parse_token(token: str) -> Optional[TokenPayload]:
    """
    Parse and validate token structure and signature.

    Args:
        token: The token string to parse

    Returns:
        TokenPayload if valid, None if invalid format or signature
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            logger.warning("token_invalid_format", reason="wrong_parts_count")
            return None

        version, payload_b64, signature = parts

        if version != "iris_v1":
            logger.warning("token_invalid_format", reason="unknown_version", version=version)
            return None

        # Verify signature
        if not _verify_signature(payload_b64, signature):
            logger.warning("token_invalid_signature")
            return None

        # Decode payload
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload_json = base64.urlsafe_b64decode(payload_b64).decode()
        payload_dict = json.loads(payload_json)

        return TokenPayload(**payload_dict)

    except Exception as e:
        logger.warning("token_parse_error", error=str(e))
        return None


def hash_token(token: str) -> str:
    """
    Create a hash of the token for storage.
    We store hashes instead of raw tokens for security.
    """
    return hashlib.sha256(token.encode()).hexdigest()


class NodeTokenManager:
    """
    Manager for node enrollment tokens.

    Handles token generation, validation, and consumption.
    Works with the database to persist token state.
    """

    def __init__(self, db):
        """
        Initialize the token manager.

        Args:
            db: Database instance for persistence
        """
        self.db = db
        self._coordinator_ws_url = os.environ.get(
            "COORDINATOR_WS_URL",
            "wss://168.119.10.189:8000/nodes/connect"
        )

    async def generate(
        self,
        label: Optional[str] = None,
        expires_in_days: Optional[int] = None
    ) -> tuple[str, str]:
        """
        Generate and store a new enrollment token.

        Args:
            label: Optional human-readable label
            expires_in_days: Optional expiration in days

        Returns:
            Tuple of (token_string, token_id)
        """
        token, payload = generate_token(label, expires_in_days)
        token_hash = hash_token(token)

        # Store in database
        await self.db.conn.execute(
            """
            INSERT INTO node_tokens (id, token_hash, expires_at, label)
            VALUES (?, ?, ?, ?)
            """,
            (
                payload.jti,
                token_hash,
                datetime.fromtimestamp(payload.exp) if payload.exp else None,
                label
            )
        )
        await self.db.conn.commit()

        return token, payload.jti

    async def validate(self, token: str) -> TokenValidationResult:
        """
        Validate an enrollment token.

        Checks:
        1. Token format and signature
        2. Token not expired
        3. Token not already used
        4. Token not revoked

        Args:
            token: The token string to validate

        Returns:
            TokenValidationResult with validation status
        """
        # Parse and verify signature
        payload = parse_token(token)
        if not payload:
            return TokenValidationResult(
                valid=False,
                error="Invalid token format or signature"
            )

        # Check expiration
        if payload.exp and datetime.utcnow().timestamp() > payload.exp:
            return TokenValidationResult(
                valid=False,
                token_id=payload.jti,
                error="Token has expired"
            )

        # Check database state
        token_hash = hash_token(token)
        async with self.db.conn.execute(
            "SELECT * FROM node_tokens WHERE id = ? AND token_hash = ?",
            (payload.jti, token_hash)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return TokenValidationResult(
                valid=False,
                token_id=payload.jti,
                error="Token not found"
            )

        token_data = dict(row)

        if token_data.get("revoked"):
            return TokenValidationResult(
                valid=False,
                token_id=payload.jti,
                error="Token has been revoked"
            )

        if token_data.get("used_at"):
            return TokenValidationResult(
                valid=False,
                token_id=payload.jti,
                error="Token has already been used"
            )

        return TokenValidationResult(
            valid=True,
            token_id=payload.jti,
            coordinator_ws=self._coordinator_ws_url
        )

    async def consume(self, token: str, node_id: str) -> bool:
        """
        Mark a token as used by a specific node.

        Args:
            token: The token string
            node_id: The node ID that used the token

        Returns:
            True if successfully consumed, False otherwise
        """
        payload = parse_token(token)
        if not payload:
            return False

        token_hash = hash_token(token)

        result = await self.db.conn.execute(
            """
            UPDATE node_tokens
            SET used_at = ?, used_by_node_id = ?
            WHERE id = ? AND token_hash = ? AND used_at IS NULL AND revoked = FALSE
            """,
            (datetime.utcnow(), node_id, payload.jti, token_hash)
        )
        await self.db.conn.commit()

        if result.rowcount > 0:
            logger.info(
                "token_consumed",
                token_id=payload.jti,
                node_id=node_id
            )
            return True

        return False

    async def is_node_enrolled(self, node_id: str) -> bool:
        """
        Check if a node was enrolled with a valid token.

        Args:
            node_id: The node ID to check

        Returns:
            True if the node was enrolled with a token
        """
        async with self.db.conn.execute(
            "SELECT id FROM node_tokens WHERE used_by_node_id = ?",
            (node_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None

    async def get_token_for_node(self, node_id: str) -> Optional[str]:
        """
        Get the token ID that was used to enroll a node.

        Args:
            node_id: The node ID to look up

        Returns:
            Token ID if found, None otherwise
        """
        async with self.db.conn.execute(
            "SELECT id FROM node_tokens WHERE used_by_node_id = ?",
            (node_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row["id"] if row else None

    async def revoke(self, token_id: str) -> bool:
        """
        Revoke a token.

        Args:
            token_id: The token ID to revoke

        Returns:
            True if successfully revoked, False otherwise
        """
        result = await self.db.conn.execute(
            "UPDATE node_tokens SET revoked = TRUE WHERE id = ?",
            (token_id,)
        )
        await self.db.conn.commit()

        if result.rowcount > 0:
            logger.info("token_revoked", token_id=token_id)
            return True

        return False

    async def list_tokens(
        self,
        include_used: bool = True,
        include_revoked: bool = False
    ) -> list[TokenInfo]:
        """
        List all tokens.

        Args:
            include_used: Include used tokens
            include_revoked: Include revoked tokens

        Returns:
            List of TokenInfo objects
        """
        conditions = []
        if not include_used:
            conditions.append("used_at IS NULL")
        if not include_revoked:
            conditions.append("revoked = FALSE")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        async with self.db.conn.execute(
            f"SELECT * FROM node_tokens {where_clause} ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()

        return [
            TokenInfo(
                id=row["id"],
                label=row["label"],
                created_at=str(row["created_at"]),
                expires_at=str(row["expires_at"]) if row["expires_at"] else None,
                used=row["used_at"] is not None,
                used_at=str(row["used_at"]) if row["used_at"] else None,
                used_by_node_id=row["used_by_node_id"],
                revoked=bool(row["revoked"])
            )
            for row in rows
        ]

    async def get_token_info(self, token_id: str) -> Optional[TokenInfo]:
        """
        Get information about a specific token.

        Args:
            token_id: The token ID to look up

        Returns:
            TokenInfo if found, None otherwise
        """
        async with self.db.conn.execute(
            "SELECT * FROM node_tokens WHERE id = ?",
            (token_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return None

        return TokenInfo(
            id=row["id"],
            label=row["label"],
            created_at=str(row["created_at"]),
            expires_at=str(row["expires_at"]) if row["expires_at"] else None,
            used=row["used_at"] is not None,
            used_at=str(row["used_at"]) if row["used_at"] else None,
            used_by_node_id=row["used_by_node_id"],
            revoked=bool(row["revoked"])
        )
