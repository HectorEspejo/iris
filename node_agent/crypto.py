"""
Iris Node Agent Cryptography

Manages the node's key pair for E2E encryption.
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


class NodeCrypto:
    """
    Manages cryptographic operations for a node agent.

    Each node maintains its own key pair for secure communication
    with the coordinator.
    """

    def __init__(self, key_path: str = "data/node.key"):
        self._key_path: Path = Path(key_path)
        self._keypair: Optional[KeyPair] = None
        self._coordinator_public_key: Optional[str] = None

    @property
    def key_path(self) -> Path:
        return self._key_path

    @key_path.setter
    def key_path(self, value: str | Path) -> None:
        self._key_path = Path(value) if isinstance(value, str) else value

    def initialize(self) -> None:
        """Load or generate the node's key pair."""
        self._keypair = KeyPair.load_or_generate(self._key_path)
        logger.info(
            "node_crypto_initialized",
            public_key=self._keypair.public_key_b64[:16] + "..."
        )

    @property
    def keypair(self) -> KeyPair:
        """Get the node's key pair."""
        if not self._keypair:
            raise RuntimeError("Crypto not initialized. Call initialize() first.")
        return self._keypair

    @property
    def public_key(self) -> str:
        """Get the node's public key (base64)."""
        return self.keypair.public_key_b64

    @property
    def coordinator_public_key(self) -> Optional[str]:
        """Get the coordinator's public key."""
        return self._coordinator_public_key

    def set_coordinator_public_key(self, public_key: str) -> None:
        """
        Set the coordinator's public key after registration.

        Args:
            public_key: Coordinator's public key (base64)
        """
        self._coordinator_public_key = public_key
        logger.info("coordinator_public_key_set")

    def encrypt_for_coordinator(self, plaintext: str) -> str:
        """
        Encrypt a message for the coordinator.

        Args:
            plaintext: Message to encrypt

        Returns:
            Base64-encoded encrypted message

        Raises:
            RuntimeError: If coordinator public key not set
        """
        if not self._coordinator_public_key:
            raise RuntimeError("Coordinator public key not set")

        return encrypt_for_recipient(
            our_keypair=self.keypair,
            recipient_public_key=self._coordinator_public_key,
            plaintext=plaintext
        )

    def decrypt_from_coordinator(self, encrypted: str) -> str:
        """
        Decrypt a message from the coordinator.

        Args:
            encrypted: Base64-encoded encrypted message

        Returns:
            Decrypted plaintext

        Raises:
            RuntimeError: If coordinator public key not set
        """
        if not self._coordinator_public_key:
            raise RuntimeError("Coordinator public key not set")

        return decrypt_from_sender(
            our_keypair=self.keypair,
            sender_public_key=self._coordinator_public_key,
            encrypted_b64=encrypted
        )


# Create node crypto instance (configured via environment or args)
node_crypto = NodeCrypto()
