"""A stand-in App Store for tests.

Mints a real certificate hierarchy and signs real transactions with it, so tests
exercise the verifier's actual cryptography rather than a stubbed-out answer.
Shared between the verification unit tests and the subscription endpoint tests,
which need the same forged and genuine payloads.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

BUNDLE_ID = "app.truvix.ios"
PRODUCT_ID = "app.truvix.premium.monthly"


def b64url(raw: bytes) -> str:
    """Base64url without padding, the encoding a JWS uses."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@dataclass(frozen=True)
class Authority:
    """A certificate and the key that owns it."""

    certificate: x509.Certificate
    private_key: ec.EllipticCurvePrivateKey

    @property
    def der(self) -> bytes:
        """The certificate in DER form."""
        return self.certificate.public_bytes(serialization.Encoding.DER)


def issue(
    subject: str,
    *,
    issuer: Authority | None = None,
    not_before: datetime | None = None,
    not_after: datetime | None = None,
) -> Authority:
    """Mint a certificate, self-signed unless an issuer is given."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)])
    now = datetime.now(UTC)

    signing_key = issuer.private_key if issuer else key
    issuer_name = issuer.certificate.subject if issuer else name

    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(issuer_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before or now - timedelta(days=1))
        .not_valid_after(not_after or now + timedelta(days=365))
        .sign(signing_key, hashes.SHA256())
    )
    return Authority(certificate=certificate, private_key=key)


class FakeAppStore:
    """Stands in for Apple: issues chains and signs transactions with them."""

    def __init__(self) -> None:
        self.root = issue("Apple Root CA - G3")
        self.intermediate = issue("Apple Worldwide Developer Relations", issuer=self.root)
        self.leaf = issue("Prod ECC Mac App Store", issuer=self.intermediate)

    def chain(self) -> list[str]:
        """The x5c header value: leaf first, root last."""
        return [
            base64.b64encode(authority.der).decode()
            for authority in (self.leaf, self.intermediate, self.root)
        ]

    def sign(self, claims: dict[str, Any]) -> str:
        """Sign claims the way StoreKit does."""
        return jwt.encode(
            claims,
            self.leaf.private_key,
            algorithm="ES256",
            headers={"x5c": self.chain()},
        )

    def transaction(self, **overrides: Any) -> str:
        """Sign a transaction, overriding any of its claims."""
        return self.sign(claims(**overrides))


def claims(**overrides: Any) -> dict[str, Any]:
    """A transaction as the App Store sends one."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "bundleId": BUNDLE_ID,
        "productId": PRODUCT_ID,
        "originalTransactionId": "2000000891234567",
        "transactionId": "2000000891234567",
        "environment": "Production",
        "purchaseDate": int(now.timestamp() * 1000),
        "expiresDate": int((now + timedelta(days=30)).timestamp() * 1000),
        "status": 1,
    }
    payload.update(overrides)
    return payload


def milliseconds(moment: datetime) -> int:
    """Apple reports instants as milliseconds since the epoch."""
    return int(moment.timestamp() * 1000)


def notification(store: FakeAppStore, notification_type: str, **overrides: Any) -> str:
    """Sign a server notification wrapping a signed transaction.

    Apple nests two signatures: the envelope, and the transaction inside it.
    Both are produced here so tests exercise the real unwrapping.
    """
    return store.sign(
        {
            "notificationType": notification_type,
            "notificationUUID": "c2f6b0a4-0c15-4b6b-9a3f-2b8e6a1d4f77",
            "data": {
                "bundleId": BUNDLE_ID,
                "environment": "Production",
                "signedTransactionInfo": store.transaction(**overrides),
            },
        }
    )
