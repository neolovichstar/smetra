"""Authenticated cloud credentials support controlled key rotation."""
import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet, InvalidToken
from backend import cloud_drives, business


class CloudKeyRotationTests(unittest.TestCase):
    def test_existing_token_decrypts_with_retired_key_but_new_writes_use_primary(self):
        old, current = Fernet.generate_key(), Fernet.generate_key()
        old_token = Fernet(old).encrypt(b"old credential").decode()
        with patch.dict("os.environ", CLOUD_TOKEN_ENCRYPTION_KEY=current.decode(), CLOUD_TOKEN_DECRYPTION_KEYS=old.decode()):
            self.assertEqual(cloud_drives._decrypt(old_token), "old credential")
            fresh = cloud_drives._encrypt("new credential").encode()
            self.assertEqual(Fernet(current).decrypt(fresh), b"new credential")
            with self.assertRaises(InvalidToken):
                Fernet(old).decrypt(fresh)

    def test_removed_or_invalid_keys_fail_closed(self):
        old, current = Fernet.generate_key(), Fernet.generate_key()
        token = Fernet(old).encrypt(b"secret").decode()
        with patch.dict("os.environ", CLOUD_TOKEN_ENCRYPTION_KEY=current.decode(), CLOUD_TOKEN_DECRYPTION_KEYS=""):
            with self.assertRaises(business.DomainError):
                cloud_drives._decrypt(token)
        with patch.dict("os.environ", CLOUD_TOKEN_ENCRYPTION_KEY=current.decode(), CLOUD_TOKEN_DECRYPTION_KEYS="invalid"):
            with self.assertRaises(business.DomainError) as error:
                cloud_drives._encrypt("secret")
            self.assertNotIn(current.decode(), str(error.exception))

    def test_ciphertext_is_randomized_and_tampering_is_detected(self):
        with patch.dict("os.environ", CLOUD_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode(), CLOUD_TOKEN_DECRYPTION_KEYS=""):
            first, second = cloud_drives._encrypt("secret"), cloud_drives._encrypt("secret")
            self.assertNotEqual(first, second)
            data = bytearray(first.encode())
            data[len(data) // 2] = ord("A") if data[len(data) // 2] != ord("A") else ord("B")
            with self.assertRaises(business.DomainError):
                cloud_drives._decrypt(data.decode())
