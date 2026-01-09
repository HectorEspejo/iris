"""
Iris Coordinator Cryptography

Manages the coordinator's key pair for E2E encryption.
"""

from pathlib import Path
from typing import Optional
import structlog

from shared.crypto_utils import (
    KeyPair,
    encrypt_for_recipient,
    decrypt_from_sender,
)

logger = structlog.get_logger()


class CoordinatorCrypto:
    """
    Manages cryptographic operations for the coordinator.

    The coordinator maintains its own key pair and manages
    encryption/decryption with nodes and clients.
    """

    def __init__(self, key_path: str = "data/coordinator.key"):
        self.key_path = Path(key_path)
        self._keypair: Optional[KeyPair] = None

    def initialize(self) -> None:
        """Load or generate the coordinator's key pair."""
        self._keypair = KeyPair.load_or_generate(self.key_path)
        logger.info(
            "coordinator_crypto_initialized",
            public_key=self._keypair.public_key_b64[:16] + "..."
        )

    @property
    def keypair(self) -> KeyPair:
        """Get the coordinator's key pair."""
        if not self._keypair:
            raise RuntimeError("Crypto not initialized. Call initialize() first.")
        return self._keypair

    @property
    def public_key(self) -> str:
        """Get the coordinator's public key (base64)."""
        return self.keypair.public_key_b64

    def encrypt_for_node(self, node_public_key: str, plaintext: str) -> str:
        """
        Encrypt a message for a specific node.

        Args:
            node_public_key: Node's public key (base64)
            plaintext: Message to encrypt

        Returns:
            Base64-encoded encrypted message
        """
        return encrypt_for_recipient(
            our_keypair=self.keypair,
            recipient_public_key=node_public_key,
            plaintext=plaintext
        )

    def decrypt_from_node(self, node_public_key: str, encrypted: str) -> str:
        """
        Decrypt a message from a node.

        Args:
            node_public_key: Node's public key (base64)
            encrypted: Base64-encoded encrypted message

        Returns:
            Decrypted plaintext
        """
        return decrypt_from_sender(
            our_keypair=self.keypair,
            sender_public_key=node_public_key,
            encrypted_b64=encrypted
        )

    def encrypt_for_user(self, user_public_key: str, plaintext: str) -> str:
        """
        Encrypt a message for a specific user.

        Args:
            user_public_key: User's public key (base64)
            plaintext: Message to encrypt

        Returns:
            Base64-encoded encrypted message
        """
        return encrypt_for_recipient(
            our_keypair=self.keypair,
            recipient_public_key=user_public_key,
            plaintext=plaintext
        )

    def decrypt_from_user(self, user_public_key: str, encrypted: str) -> str:
        """
        Decrypt a message from a user.

        Args:
            user_public_key: User's public key (base64)
            encrypted: Base64-encoded encrypted message

        Returns:
            Decrypted plaintext
        """
        return decrypt_from_sender(
            our_keypair=self.keypair,
            sender_public_key=user_public_key,
            encrypted_b64=encrypted
        )


# Global coordinator crypto instance
coordinator_crypto = CoordinatorCrypto()
