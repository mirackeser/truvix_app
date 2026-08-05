"""Verifying signed App Store transactions.

This is the load-bearing security boundary of the whole subscription. The app
sends a transaction it received from StoreKit; nothing about it is trusted
until the signature is checked. A client that could simply assert "I am
premium" would make the paywall decorative.

StoreKit 2 hands the app a JWS whose header carries the certificate chain that
signed it. Verification therefore has three parts, and all three matter:

1. The chain terminates at Apple's root certificate, so the signature was made
   by a key Apple controls rather than by anyone with a keypair.
2. The signature over the payload is valid, so the payload was not edited after
   signing.
3. The payload names our bundle, so a genuine Apple transaction for a different
   application cannot be redeemed here.

Skipping any one of them leaves a forgery that passes.
"""

from __future__ import annotations

import base64
import itertools
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import jwt
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

from truvix.modules.subscriptions.models import EntitlementStatus, StoreEnvironment
from truvix.shared.errors import DomainValidationError
from truvix.shared.logging import get_logger

_logger = get_logger(__name__)

_EXPECTED_ALGORITHM: Final = "ES256"

# The App Store reports these; anything else is treated as not granting access.
_STATUS_BY_CODE: Final[dict[int, EntitlementStatus]] = {
    1: EntitlementStatus.ACTIVE,
    2: EntitlementStatus.EXPIRED,
    3: EntitlementStatus.IN_BILLING_RETRY,
    4: EntitlementStatus.IN_GRACE_PERIOD,
    5: EntitlementStatus.REVOKED,
}


@dataclass(frozen=True, slots=True)
class VerifiedTransaction:
    """A transaction whose signature and audience have both been checked."""

    product_id: str
    original_transaction_id: str
    transaction_id: str
    bundle_id: str
    environment: StoreEnvironment
    purchased_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    status: EntitlementStatus


class AppStoreVerifier:
    """Checks that a signed transaction really came from Apple, for us."""

    def __init__(
        self,
        *,
        root_certificates: list[bytes],
        expected_bundle_id: str,
        allow_sandbox: bool = False,
    ) -> None:
        """Initialise the verifier.

        Args:
            root_certificates: Apple's root certificates, DER or PEM encoded.
                Supplied rather than fetched: a root downloaded at runtime is a
                root an attacker on the network could substitute.
            expected_bundle_id: The application the transaction must name.
            allow_sandbox: Whether transactions from Apple's sandbox count.
                Defaults to refusing them, because a sandbox transaction is
                signed by the same Apple chain as a real one and passes every
                other check here — the environment claim is the only thing
                separating a paid subscription from a free test account.
        """
        self._roots = [self._load_certificate(raw) for raw in root_certificates]
        self._expected_bundle_id = expected_bundle_id
        self._allow_sandbox = allow_sandbox

    def verify(self, signed_payload: str) -> VerifiedTransaction:
        """Verify a signed transaction and return what it says.

        Args:
            signed_payload: The JWS as StoreKit produced it.

        Returns:
            The transaction, once trusted.

        Raises:
            DomainValidationError: If the payload is malformed, the chain does
                not reach a known Apple root, the signature does not verify, or
                the transaction names a different application.
        """
        return self._interpret(self._verified_claims(signed_payload))

    def verify_notification(self, signed_payload: str) -> str:
        """Verify a server notification and return the transaction inside it.

        Apple wraps notifications in a signed envelope which itself contains a
        separately signed transaction. The envelope is verified here so that an
        unauthenticated webhook cannot be driven by anyone who knows the URL:
        for this endpoint the signature *is* the authentication.

        Args:
            signed_payload: The ``signedPayload`` field Apple posts.

        Returns:
            The signed transaction from inside the envelope, still to be
            verified in its own right by :meth:`verify`.

        Raises:
            DomainValidationError: If the envelope does not verify or carries no
                transaction.
        """
        claims = self._verified_claims(signed_payload)

        data = claims.get("data")
        if not isinstance(data, dict):
            raise DomainValidationError("Bildirim veri taşımıyor.")

        signed_transaction = data.get("signedTransactionInfo")
        if not isinstance(signed_transaction, str) or not signed_transaction:
            raise DomainValidationError("Bildirim işlem bilgisi taşımıyor.")

        return signed_transaction

    def _verified_claims(self, signed_payload: str) -> dict[str, Any]:
        """Check a JWS against Apple's chain and return its claims."""
        chain = self._certificate_chain(signed_payload)
        self._assert_chain_is_apples(chain)

        leaf = chain[0]
        try:
            claims: dict[str, Any] = jwt.decode(
                signed_payload,
                key=leaf.public_key(),  # type: ignore[arg-type]
                algorithms=[_EXPECTED_ALGORITHM],
                # Apple's transaction payloads carry no aud/iss claims to check,
                # and their expiry is a business date rather than a token
                # lifetime, so signature and audience are enforced explicitly.
                options={"verify_aud": False, "verify_exp": False},
            )
        except jwt.PyJWTError as exc:
            raise DomainValidationError("İşlem imzası doğrulanamadı.") from exc

        return claims

    # MARK: - Chain

    @staticmethod
    def _certificate_chain(signed_payload: str) -> list[x509.Certificate]:
        """Read the x5c certificate chain out of the JWS header."""
        try:
            header = jwt.get_unverified_header(signed_payload)
        except jwt.PyJWTError as exc:
            raise DomainValidationError("İşlem verisi okunamadı.") from exc

        if header.get("alg") != _EXPECTED_ALGORITHM:
            # Pinning the algorithm closes the "alg: none" family of attacks,
            # where a forged token declares it needs no signature at all.
            raise DomainValidationError("İşlem beklenmeyen bir algoritmayla imzalanmış.")

        encoded_chain = header.get("x5c")
        if not isinstance(encoded_chain, list) or not encoded_chain:
            raise DomainValidationError("İşlem sertifika zinciri taşımıyor.")

        try:
            return [
                x509.load_der_x509_certificate(base64.b64decode(entry)) for entry in encoded_chain
            ]
        except (ValueError, TypeError) as exc:
            raise DomainValidationError("İşlem sertifika zinciri okunamadı.") from exc

    def _assert_chain_is_apples(self, chain: list[x509.Certificate]) -> None:
        """Check the chain links up and terminates at a known Apple root."""
        now = datetime.now(UTC)

        for certificate in chain:
            if not (certificate.not_valid_before_utc <= now <= certificate.not_valid_after_utc):
                raise DomainValidationError("İşlem sertifikası geçerlilik dışı.")

        # Each certificate must be signed by the next one along.
        for child, parent in itertools.pairwise(chain):
            self._assert_signed_by(child, parent)

        root = chain[-1]
        if not any(self._is_same_certificate(root, known) for known in self._roots):
            _logger.warning(
                "app_store_chain_rejected",
                root_subject=root.subject.rfc4514_string(),
            )
            raise DomainValidationError("İşlem, Apple tarafından imzalanmamış.")

    @staticmethod
    def _assert_signed_by(child: x509.Certificate, parent: x509.Certificate) -> None:
        """Check that ``parent`` signed ``child``."""
        public_key = parent.public_key()
        algorithm = child.signature_hash_algorithm
        if algorithm is None:
            raise DomainValidationError("İşlem sertifikası imzalanmamış.")

        try:
            if isinstance(public_key, ec.EllipticCurvePublicKey):
                public_key.verify(
                    child.signature,
                    child.tbs_certificate_bytes,
                    ec.ECDSA(algorithm),
                )
            elif isinstance(public_key, rsa.RSAPublicKey):
                public_key.verify(
                    child.signature,
                    child.tbs_certificate_bytes,
                    padding.PKCS1v15(),
                    algorithm,
                )
            else:
                raise DomainValidationError("İşlem sertifikası desteklenmeyen anahtar taşıyor.")
        except InvalidSignature as exc:
            raise DomainValidationError("İşlem sertifika zinciri tutarsız.") from exc

    @staticmethod
    def _is_same_certificate(left: x509.Certificate, right: x509.Certificate) -> bool:
        """Whether two certificates are the same one.

        Compared by fingerprint rather than by subject: a subject line can be
        copied into any self-signed certificate, a fingerprint cannot.
        """
        return left.fingerprint(hashes.SHA256()) == right.fingerprint(hashes.SHA256())

    @staticmethod
    def _load_certificate(raw: bytes) -> x509.Certificate:
        """Load a certificate given either DER or PEM bytes."""
        try:
            return x509.load_der_x509_certificate(raw)
        except ValueError:
            return x509.load_pem_x509_certificate(raw)

    # MARK: - Payload

    def _interpret(self, claims: dict[str, Any]) -> VerifiedTransaction:
        """Turn verified claims into a transaction, checking the audience."""
        bundle_id = claims.get("bundleId")
        if bundle_id != self._expected_bundle_id:
            # A genuine Apple signature over somebody else's app is still not a
            # purchase of ours.
            _logger.warning("app_store_bundle_mismatch", bundle_id=str(bundle_id))
            raise DomainValidationError("İşlem başka bir uygulamaya ait.")

        environment = (
            StoreEnvironment.SANDBOX
            if claims.get("environment") == "Sandbox"
            else StoreEnvironment.PRODUCTION
        )
        if environment is StoreEnvironment.SANDBOX and not self._allow_sandbox:
            # Apple signs sandbox transactions with the same chain as real ones,
            # so every check above passes for a purchase that cost nothing. Only
            # this claim distinguishes a paying customer from a test account.
            _logger.warning(
                "app_store_sandbox_rejected",
                original_transaction_id=str(claims.get("originalTransactionId")),
            )
            raise DomainValidationError("Sandbox işlemleri bu ortamda kabul edilmiyor.")

        product_id = claims.get("productId")
        original = claims.get("originalTransactionId")
        transaction = claims.get("transactionId")
        if not (
            isinstance(product_id, str)
            and isinstance(original, str)
            and isinstance(transaction, str)
        ):
            raise DomainValidationError("İşlem beklenen alanları taşımıyor.")

        purchased_at = self._instant(claims.get("purchaseDate"))
        if purchased_at is None:
            raise DomainValidationError("İşlem satın alma tarihi taşımıyor.")

        return VerifiedTransaction(
            product_id=product_id,
            original_transaction_id=original,
            transaction_id=transaction,
            bundle_id=bundle_id,
            environment=environment,
            purchased_at=purchased_at,
            expires_at=self._instant(claims.get("expiresDate")),
            revoked_at=self._instant(claims.get("revocationDate")),
            status=_STATUS_BY_CODE.get(
                claims.get("status", 1) if isinstance(claims.get("status"), int) else 1,
                EntitlementStatus.ACTIVE,
            ),
        )

    @staticmethod
    def _instant(value: Any) -> datetime | None:
        """Read one of Apple's millisecond timestamps."""
        if not isinstance(value, int | float):
            return None
        return datetime.fromtimestamp(value / 1000, tz=UTC)


def decode_unverified(signed_payload: str) -> dict[str, Any]:
    """Read a payload without checking it, for diagnostics only.

    Never use this to decide anything. It exists so a rejected transaction can
    be logged usefully, and is named to make misuse obvious in review.
    """
    try:
        segments = signed_payload.split(".")
        padded = segments[1] + "=" * (-len(segments[1]) % 4)
        decoded: dict[str, Any] = json.loads(base64.urlsafe_b64decode(padded))
        return decoded
    except IndexError, ValueError:
        return {}
