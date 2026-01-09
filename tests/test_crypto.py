"""
Tests for cryptographic utilities.
"""

import pytest
import tempfile
from pathlib import Path

from shared.crypto_utils import (
    KeyPair,
    generate_keypair,
    encrypt_for_recipient,
    decrypt_from_sender,
    public_key_from_b64,
    derive_shared_key,
    encrypt_data,
    decrypt_data,
)


class TestKeyPair:
    """Tests for KeyPair class."""

    def test_generate_keypair(self):
        """Test key pair generation."""
        keypair = generate_keypair()
        assert keypair.private_key is not None
        assert keypair.public_key is not None
        assert len(keypair.public_key_b64) > 0

    def test_keypair_save_load(self):
        """Test saving and loading key pair."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "test.key"

            # Generate and save
            original = generate_keypair()
            original.save(key_path)

            # Load and compare
            loaded = KeyPair.load(key_path)
            assert loaded.public_key_b64 == original.public_key_b64

    def test_keypair_load_or_generate_new(self):
        """Test load_or_generate creates new key if not exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "new.key"

            assert not key_path.exists()
            keypair = KeyPair.load_or_generate(key_path)
            assert key_path.exists()
            assert keypair.public_key_b64 is not None

    def test_keypair_load_or_generate_existing(self):
        """Test load_or_generate loads existing key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "existing.key"

            # Create key
            original = generate_keypair()
            original.save(key_path)

            # Load existing
            loaded = KeyPair.load_or_generate(key_path)
            assert loaded.public_key_b64 == original.public_key_b64


class TestPublicKeyConversion:
    """Tests for public key conversion."""

    def test_public_key_from_b64(self):
        """Test converting base64 to public key."""
        keypair = generate_keypair()
        b64_key = keypair.public_key_b64

        restored = public_key_from_b64(b64_key)
        assert restored is not None


class TestKeyDerivation:
    """Tests for key derivation."""

    def test_derive_shared_key(self):
        """Test that two parties derive the same shared key."""
        alice = generate_keypair()
        bob = generate_keypair()

        # Alice derives key with Bob's public key
        alice_key, salt = derive_shared_key(alice.private_key, bob.public_key)

        # Bob derives key with Alice's public key (using same salt)
        bob_key, _ = derive_shared_key(bob.private_key, alice.public_key, salt=salt)

        assert alice_key == bob_key

    def test_derive_shared_key_different_pairs(self):
        """Test that different pairs get different keys."""
        alice = generate_keypair()
        bob = generate_keypair()
        charlie = generate_keypair()

        alice_bob_key, salt = derive_shared_key(alice.private_key, bob.public_key)
        alice_charlie_key, _ = derive_shared_key(alice.private_key, charlie.public_key, salt=salt)

        assert alice_bob_key != alice_charlie_key


class TestEncryption:
    """Tests for encryption/decryption."""

    def test_encrypt_decrypt_data(self):
        """Test raw data encryption/decryption."""
        key = b"0123456789abcdef0123456789abcdef"  # 32 bytes
        plaintext = b"Hello, World!"

        encrypted = encrypt_data(key, plaintext)
        assert encrypted != plaintext

        decrypted = decrypt_data(key, encrypted)
        assert decrypted == plaintext

    def test_encrypt_for_recipient_string(self):
        """Test encrypting string for recipient."""
        sender = generate_keypair()
        recipient = generate_keypair()

        plaintext = "This is a secret message"

        encrypted = encrypt_for_recipient(
            sender,
            recipient.public_key_b64,
            plaintext
        )

        assert encrypted != plaintext
        assert len(encrypted) > len(plaintext)

    def test_decrypt_from_sender_string(self):
        """Test decrypting string from sender."""
        sender = generate_keypair()
        recipient = generate_keypair()

        original = "This is a secret message"

        encrypted = encrypt_for_recipient(sender, recipient.public_key_b64, original)
        decrypted = decrypt_from_sender(recipient, sender.public_key_b64, encrypted)

        assert decrypted == original

    def test_encrypt_decrypt_roundtrip_bytes(self):
        """Test encryption roundtrip with bytes."""
        sender = generate_keypair()
        recipient = generate_keypair()

        original = b"Binary data \x00\x01\x02"

        encrypted = encrypt_for_recipient(sender, recipient.public_key_b64, original)
        decrypted = decrypt_from_sender(recipient, sender.public_key_b64, encrypted)

        assert decrypted == original.decode("utf-8")

    def test_encrypt_decrypt_unicode(self):
        """Test encryption with unicode characters."""
        sender = generate_keypair()
        recipient = generate_keypair()

        original = "Hello 世界 🌍 émoji"

        encrypted = encrypt_for_recipient(sender, recipient.public_key_b64, original)
        decrypted = decrypt_from_sender(recipient, sender.public_key_b64, encrypted)

        assert decrypted == original

    def test_encrypt_decrypt_empty_string(self):
        """Test encryption with empty string."""
        sender = generate_keypair()
        recipient = generate_keypair()

        original = ""

        encrypted = encrypt_for_recipient(sender, recipient.public_key_b64, original)
        decrypted = decrypt_from_sender(recipient, sender.public_key_b64, encrypted)

        assert decrypted == original

    def test_decrypt_wrong_sender_fails(self):
        """Test that decryption fails with wrong sender key."""
        sender = generate_keypair()
        recipient = generate_keypair()
        wrong_sender = generate_keypair()

        encrypted = encrypt_for_recipient(sender, recipient.public_key_b64, "secret")

        with pytest.raises(Exception):  # Will raise InvalidTag
            decrypt_from_sender(recipient, wrong_sender.public_key_b64, encrypted)

    def test_decrypt_wrong_recipient_fails(self):
        """Test that decryption fails with wrong recipient key."""
        sender = generate_keypair()
        recipient = generate_keypair()
        wrong_recipient = generate_keypair()

        encrypted = encrypt_for_recipient(sender, recipient.public_key_b64, "secret")

        with pytest.raises(Exception):  # Will raise InvalidTag
            decrypt_from_sender(wrong_recipient, sender.public_key_b64, encrypted)


class TestLargeData:
    """Tests for handling large data."""

    def test_encrypt_large_message(self):
        """Test encryption of large messages."""
        sender = generate_keypair()
        recipient = generate_keypair()

        # 1 MB of data
        original = "x" * (1024 * 1024)

        encrypted = encrypt_for_recipient(sender, recipient.public_key_b64, original)
        decrypted = decrypt_from_sender(recipient, sender.public_key_b64, encrypted)

        assert decrypted == original
