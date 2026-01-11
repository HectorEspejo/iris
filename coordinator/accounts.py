"""
Iris Account Key Generator

Generates and validates Mullvad-style numeric account keys.
Format: 16 digits grouped as "1234 5678 9012 3456"
"""

import secrets
import hashlib
import re
from typing import Optional
import structlog

logger = structlog.get_logger()


class AccountKeyGenerator:
    """
    Generates and validates Mullvad-style numeric Account Keys.

    Format: 16 numeric digits (e.g., "7294 8156 3047 9821")
    - ~53 bits of entropy (10^16 combinations)
    - Easy to read, dictate, and write
    - Grouped in 4 blocks of 4 digits for readability
    """

    LENGTH = 16  # 16 digits total

    @classmethod
    def generate(cls) -> str:
        """
        Generate a new 16-digit account number.

        Returns:
            Formatted account key like "7294 8156 3047 9821"
        """
        digits = ''.join(str(secrets.randbelow(10)) for _ in range(cls.LENGTH))
        formatted = cls.format_key(digits)

        logger.debug("account_key_generated", prefix=digits[:4])
        return formatted

    @classmethod
    def format_key(cls, key: str) -> str:
        """
        Format key as "1234 5678 9012 3456".

        Args:
            key: Raw digits (with or without formatting)

        Returns:
            Formatted key with spaces
        """
        raw = cls.normalize(key)
        if len(raw) != cls.LENGTH:
            raise ValueError(f"Account key must be {cls.LENGTH} digits")
        return f"{raw[:4]} {raw[4:8]} {raw[8:12]} {raw[12:16]}"

    @classmethod
    def normalize(cls, key: str) -> str:
        """
        Remove spaces, dashes, and other formatting.

        Args:
            key: Account key in any format

        Returns:
            Raw 16-digit string
        """
        return re.sub(r'[\s\-]', '', key)

    @classmethod
    def hash_key(cls, account_key: str) -> str:
        """
        Hash the account key for secure storage.

        The actual key is NEVER stored - only its hash.

        Args:
            account_key: The account key to hash

        Returns:
            SHA256 hex digest
        """
        normalized = cls.normalize(account_key)
        return hashlib.sha256(normalized.encode()).hexdigest()

    @classmethod
    def get_prefix(cls, account_key: str) -> str:
        """
        Get the first 4 digits for partial identification.

        Used for logging and display without revealing full key.

        Args:
            account_key: The account key

        Returns:
            First 4 digits
        """
        return cls.normalize(account_key)[:4]

    @classmethod
    def validate_format(cls, account_key: str) -> bool:
        """
        Validate that the key has exactly 16 digits.

        Args:
            account_key: The account key to validate

        Returns:
            True if valid format, False otherwise
        """
        normalized = cls.normalize(account_key)
        return len(normalized) == cls.LENGTH and normalized.isdigit()

    @classmethod
    def mask_key(cls, account_key: str) -> str:
        """
        Mask the key for safe display: "7294 **** **** ****".

        Args:
            account_key: The account key to mask

        Returns:
            Masked key showing only first 4 digits
        """
        raw = cls.normalize(account_key)
        return f"{raw[:4]} **** **** ****"

    @classmethod
    def validate_and_hash(cls, account_key: str) -> Optional[str]:
        """
        Validate format and return hash if valid.

        Convenience method combining validation and hashing.

        Args:
            account_key: The account key to process

        Returns:
            Hash if valid, None if invalid format
        """
        if not cls.validate_format(account_key):
            logger.warning(
                "invalid_account_key_format",
                prefix=account_key[:4] if len(account_key) >= 4 else "???"
            )
            return None
        return cls.hash_key(account_key)


# Convenience functions
def generate_account_key() -> str:
    """Generate a new account key."""
    return AccountKeyGenerator.generate()


def validate_account_key(key: str) -> bool:
    """Validate account key format."""
    return AccountKeyGenerator.validate_format(key)


def hash_account_key(key: str) -> str:
    """Hash an account key for storage."""
    return AccountKeyGenerator.hash_key(key)


def mask_account_key(key: str) -> str:
    """Mask account key for display."""
    return AccountKeyGenerator.mask_key(key)
