"""Password hashing built on Argon2id.

Argon2id is the current password-hashing recommendation: it resists both GPU
and side-channel attacks, and its cost parameters can be raised over time
without invalidating existing hashes thanks to the rehash check below.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from truvix.shared.config import SecuritySettings

# Argon2 reference implementation defaults for a 256-bit hash and 128-bit salt.
_HASH_LENGTH_BYTES = 32
_SALT_LENGTH_BYTES = 16


class PasswordHasherService:
    """Hashes and verifies user passwords.

    Cost parameters come from configuration so they can be tuned per
    environment: tests run with cheap parameters, production runs with
    parameters calibrated to the deployment hardware.
    """

    def __init__(self, settings: SecuritySettings) -> None:
        """Initialise the hasher with configured cost parameters.

        Args:
            settings: Security configuration supplying Argon2 cost parameters.
        """
        self._hasher = PasswordHasher(
            time_cost=settings.argon2_time_cost,
            memory_cost=settings.argon2_memory_cost_kib,
            parallelism=settings.argon2_parallelism,
            hash_len=_HASH_LENGTH_BYTES,
            salt_len=_SALT_LENGTH_BYTES,
        )

    def hash(self, plain_password: str) -> str:
        """Hash a plaintext password.

        Args:
            plain_password: The user-supplied password.

        Returns:
            An encoded Argon2 hash that embeds the salt and cost parameters.
        """
        return self._hasher.hash(plain_password)

    def verify(self, plain_password: str, password_hash: str) -> bool:
        """Check a password against a stored hash.

        Args:
            plain_password: The user-supplied password.
            password_hash: The stored Argon2 hash.

        Returns:
            ``True`` when the password matches. A malformed stored hash is
            treated as a mismatch rather than an error, so a corrupted row
            cannot be used to distinguish accounts.
        """
        try:
            self._hasher.verify(password_hash, plain_password)
        except VerifyMismatchError, VerificationError, InvalidHashError:
            return False
        return True

    def needs_rehash(self, password_hash: str) -> bool:
        """Whether a stored hash was produced with outdated cost parameters.

        Call after a successful verification: when this returns ``True`` the
        caller should rehash the password it just verified and store the result,
        transparently upgrading the account's protection.

        Args:
            password_hash: The stored Argon2 hash.
        """
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True
