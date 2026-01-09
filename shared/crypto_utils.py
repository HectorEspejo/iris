"""
Iris Cryptographic Utilities

E2E encryption using X25519 for key exchange and AES-256-GCM for data encryption.
"""

import os
import base64
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


# Constants
NONCE_SIZE = 12  # 96 bits for AES-GCM
KEY_SIZE = 32    # 256 bits for AES-256
SALT_SIZE = 16   # 128 bits for HKDF salt


@dataclass
class KeyPair:
    """
    X25519 key pair for asymmetric encryption.

    The private key is used to derive shared secrets.
    The public key is shared with other parties.
    """
    private_key: X25519PrivateKey
    public_key: X25519PublicKey

    @property
    def public_key_bytes(self) -> bytes:
        """Get raw public key bytes."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )

    @property
    def public_key_b64(self) -> str:
        """Get base64-encoded public key."""
        return base64.b64encode(self.public_key_bytes).decode()

    @property
    def private_key_bytes(self) -> bytes:
        """Get raw private key bytes."""
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )

    def save(self, path: Path) -> None:
        """
        Save the private key to a file.

        Args:
            path: File path to save the key
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.private_key_bytes)
        # Set restrictive permissions (owner read/write only)
        os.chmod(path, 0o600)

    @classmethod
    def load(cls, path: Path) -> "KeyPair":
        """
        Load a key pair from a private key file.

        Args:
            path: Path to the private key file

        Returns:
            KeyPair instance
        """
        private_key_bytes = path.read_bytes()
        private_key = X25519PrivateKey.from_private_bytes(private_key_bytes)
        return cls(
            private_key=private_key,
            public_key=private_key.public_key()
        )

    @classmethod
    def load_or_generate(cls, path: Path) -> "KeyPair":
        """
        Load existing key pair or generate a new one.

        Args:
            path: Path to the private key file

        Returns:
            KeyPair instance
        """
        if path.exists():
            return cls.load(path)
        keypair = generate_keypair()
        keypair.save(path)
        return keypair


def generate_keypair() -> KeyPair:
    """
    Generate a new X25519 key pair.

    Returns:
        New KeyPair instance
    """
    private_key = X25519PrivateKey.generate()
    return KeyPair(
        private_key=private_key,
        public_key=private_key.public_key()
    )


def public_key_from_b64(b64_key: str) -> X25519PublicKey:
    """
    Create a public key from base64 encoding.

    Args:
        b64_key: Base64-encoded public key

    Returns:
        X25519PublicKey instance
    """
    key_bytes = base64.b64decode(b64_key)
    return X25519PublicKey.from_public_bytes(key_bytes)


def derive_shared_key(
    private_key: X25519PrivateKey,
    peer_public_key: X25519PublicKey,
    salt: Optional[bytes] = None,
    info: bytes = b"clubai-e2e"
) -> tuple[bytes, bytes]:
    """
    Derive a shared symmetric key using X25519 + HKDF.

    Args:
        private_key: Our private key
        peer_public_key: The other party's public key
        salt: Optional salt for HKDF (random if not provided)
        info: Context info for HKDF

    Returns:
        Tuple of (derived_key, salt)
    """
    # Perform X25519 key exchange
    shared_secret = private_key.exchange(peer_public_key)

    # Generate salt if not provided
    if salt is None:
        salt = os.urandom(SALT_SIZE)

    # Derive key using HKDF
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=salt,
        info=info,
    )
    derived_key = hkdf.derive(shared_secret)

    return derived_key, salt


def encrypt_data(key: bytes, plaintext: bytes) -> bytes:
    """
    Encrypt data using AES-256-GCM.

    Args:
        key: 32-byte AES key
        plaintext: Data to encrypt

    Returns:
        nonce || ciphertext || tag (concatenated)
    """
    nonce = os.urandom(NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext


def decrypt_data(key: bytes, encrypted: bytes) -> bytes:
    """
    Decrypt data encrypted with AES-256-GCM.

    Args:
        key: 32-byte AES key
        encrypted: nonce || ciphertext || tag

    Returns:
        Decrypted plaintext

    Raises:
        cryptography.exceptions.InvalidTag: If decryption fails
    """
    nonce = encrypted[:NONCE_SIZE]
    ciphertext = encrypted[NONCE_SIZE:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def encrypt_for_recipient(
    our_keypair: KeyPair,
    recipient_public_key: str | X25519PublicKey,
    plaintext: str | bytes
) -> str:
    """
    Encrypt a message for a specific recipient.

    The encrypted format is: base64(salt || nonce || ciphertext || tag)

    Args:
        our_keypair: Our key pair
        recipient_public_key: Recipient's public key (base64 string or key object)
        plaintext: Message to encrypt (string or bytes)

    Returns:
        Base64-encoded encrypted message
    """
    # Convert types
    if isinstance(recipient_public_key, str):
        recipient_public_key = public_key_from_b64(recipient_public_key)
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")

    # Derive shared key
    key, salt = derive_shared_key(
        our_keypair.private_key,
        recipient_public_key
    )

    # Encrypt
    encrypted = encrypt_data(key, plaintext)

    # Prepend salt and encode
    return base64.b64encode(salt + encrypted).decode()


def decrypt_from_sender(
    our_keypair: KeyPair,
    sender_public_key: str | X25519PublicKey,
    encrypted_b64: str
) -> str:
    """
    Decrypt a message from a specific sender.

    Args:
        our_keypair: Our key pair
        sender_public_key: Sender's public key (base64 string or key object)
        encrypted_b64: Base64-encoded encrypted message

    Returns:
        Decrypted plaintext as string

    Raises:
        cryptography.exceptions.InvalidTag: If decryption fails
    """
    # Convert types
    if isinstance(sender_public_key, str):
        sender_public_key = public_key_from_b64(sender_public_key)

    # Decode
    data = base64.b64decode(encrypted_b64)
    salt = data[:SALT_SIZE]
    encrypted = data[SALT_SIZE:]

    # Derive shared key (same key derivation as sender)
    key, _ = derive_shared_key(
        our_keypair.private_key,
        sender_public_key,
        salt=salt
    )

    # Decrypt
    plaintext = decrypt_data(key, encrypted)
    return plaintext.decode("utf-8")


class CryptoError(Exception):
    """Custom exception for cryptographic errors."""
    pass
