"""Tests for App Store transaction verification.

These are the tests that decide whether the paywall means anything. Each one
mints a real certificate hierarchy and a real signature, then attacks it the way
somebody wanting free premium would: swapping the root, editing the payload,
declaring no signature at all, replaying another app's purchase, or presenting a
sandbox transaction that cost nothing.

A helper that produced pre-canned strings would prove nothing, so every payload
here is signed with keys generated in the test.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from tests.support.app_store import BUNDLE_ID, FakeAppStore
from tests.support.app_store import b64url as _b64url
from tests.support.app_store import claims as _claims
from tests.support.app_store import issue as _issue
from truvix.modules.subscriptions.models import EntitlementStatus, StoreEnvironment
from truvix.modules.subscriptions.verification import AppStoreVerifier, decode_unverified
from truvix.shared.errors import DomainValidationError


@pytest.fixture
def store() -> FakeAppStore:
    """A stand-in App Store with its own root."""
    return FakeAppStore()


@pytest.fixture
def verifier(store: FakeAppStore) -> AppStoreVerifier:
    """A verifier trusting the stand-in store's root, production only."""
    return AppStoreVerifier(
        root_certificates=[store.root.der],
        expected_bundle_id=BUNDLE_ID,
    )


class TestGenuineTransaction:
    """A properly signed transaction must be accepted and read correctly."""

    def test_accepts_a_transaction_signed_by_the_trusted_root(
        self, store: FakeAppStore, verifier: AppStoreVerifier
    ) -> None:
        transaction = verifier.verify(store.sign(_claims()))

        assert transaction.bundle_id == BUNDLE_ID
        assert transaction.product_id == "app.truvix.premium.monthly"
        assert transaction.original_transaction_id == "2000000891234567"
        assert transaction.status is EntitlementStatus.ACTIVE
        assert transaction.environment is StoreEnvironment.PRODUCTION

    def test_reads_the_expiry_apple_reported(
        self, store: FakeAppStore, verifier: AppStoreVerifier
    ) -> None:
        expiry = datetime.now(UTC) + timedelta(days=7)
        signed = store.sign(_claims(expiresDate=int(expiry.timestamp() * 1000)))

        transaction = verifier.verify(signed)

        assert transaction.expires_at is not None
        assert abs((transaction.expires_at - expiry).total_seconds()) < 1

    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            (1, EntitlementStatus.ACTIVE),
            (2, EntitlementStatus.EXPIRED),
            (3, EntitlementStatus.IN_BILLING_RETRY),
            (4, EntitlementStatus.IN_GRACE_PERIOD),
            (5, EntitlementStatus.REVOKED),
        ],
    )
    def test_maps_every_status_apple_reports(
        self,
        store: FakeAppStore,
        verifier: AppStoreVerifier,
        code: int,
        expected: EntitlementStatus,
    ) -> None:
        transaction = verifier.verify(store.sign(_claims(status=code)))

        assert transaction.status is expected


class TestForgery:
    """Every one of these is somebody trying to get premium without paying."""

    def test_rejects_a_chain_that_does_not_reach_the_trusted_root(self) -> None:
        """The whole point: a well-formed chain of somebody else's making."""
        impostor = FakeAppStore()
        genuine = FakeAppStore()
        verifier = AppStoreVerifier(
            root_certificates=[genuine.root.der],
            expected_bundle_id=BUNDLE_ID,
        )

        with pytest.raises(DomainValidationError):
            verifier.verify(impostor.sign(_claims()))

    def test_rejects_a_forged_root_wearing_apples_name(self) -> None:
        """A subject line is not an identity.

        The impostor's root carries exactly the common name Apple's does. Only
        comparing key material rather than text catches this.
        """
        genuine = FakeAppStore()
        impostor = FakeAppStore()
        assert impostor.root.certificate.subject == genuine.root.certificate.subject

        verifier = AppStoreVerifier(
            root_certificates=[genuine.root.der],
            expected_bundle_id=BUNDLE_ID,
        )

        with pytest.raises(DomainValidationError):
            verifier.verify(impostor.sign(_claims()))

    def test_rejects_a_payload_edited_after_signing(
        self, store: FakeAppStore, verifier: AppStoreVerifier
    ) -> None:
        """Swapping the claims for a longer subscription must break the signature."""
        signed = store.sign(_claims())
        header, _, signature = signed.split(".")

        forged_claims = _claims(
            expiresDate=int((datetime.now(UTC) + timedelta(days=3650)).timestamp() * 1000)
        )
        forged_body = _b64url(json.dumps(forged_claims).encode())

        with pytest.raises(DomainValidationError):
            verifier.verify(f"{header}.{forged_body}.{signature}")

    def test_rejects_a_transaction_claiming_it_needs_no_signature(
        self, store: FakeAppStore, verifier: AppStoreVerifier
    ) -> None:
        """The classic ``alg: none`` attack."""
        header = _b64url(json.dumps({"alg": "none", "x5c": store.chain()}).encode())
        body = _b64url(json.dumps(_claims()).encode())

        with pytest.raises(DomainValidationError):
            verifier.verify(f"{header}.{body}.")

    def test_rejects_a_transaction_signed_with_the_public_key_as_a_password(
        self, store: FakeAppStore, verifier: AppStoreVerifier
    ) -> None:
        """Algorithm confusion, the attack the ``alg`` allowlist exists for.

        The certificate chain is genuine and public, so an attacker holds the
        leaf's public key. If the verifier honoured the header's choice of
        algorithm, they could declare HS256 and use that public key as the
        shared secret — signing anything they like with material we handed them.
        """
        public_key = store.leaf.certificate.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        # Assembled by hand: PyJWT refuses to *produce* this, so building it
        # with the library would test PyJWT's encoder rather than our verifier.
        header = _b64url(json.dumps({"alg": "HS256", "x5c": store.chain()}).encode())
        body = _b64url(
            json.dumps(
                _claims(
                    expiresDate=int((datetime.now(UTC) + timedelta(days=3650)).timestamp() * 1000)
                )
            ).encode()
        )
        signature = _b64url(
            hmac.new(public_key, f"{header}.{body}".encode(), hashlib.sha256).digest()
        )

        with pytest.raises(DomainValidationError):
            verifier.verify(f"{header}.{body}.{signature}")

    def test_rejects_a_transaction_carrying_no_chain_at_all(
        self, verifier: AppStoreVerifier
    ) -> None:
        key = ec.generate_private_key(ec.SECP256R1())
        signed = jwt.encode(_claims(), key, algorithm="ES256")

        with pytest.raises(DomainValidationError):
            verifier.verify(signed)

    def test_rejects_a_chain_whose_links_do_not_match(self, verifier: AppStoreVerifier) -> None:
        """A leaf spliced under a genuine root it was never issued by."""
        store = FakeAppStore()
        unrelated_leaf = _issue("Attacker Leaf")

        header_chain = [
            base64.b64encode(unrelated_leaf.der).decode(),
            base64.b64encode(store.intermediate.der).decode(),
            base64.b64encode(store.root.der).decode(),
        ]
        signed = jwt.encode(
            _claims(),
            unrelated_leaf.private_key,
            algorithm="ES256",
            headers={"x5c": header_chain},
        )

        trusting = AppStoreVerifier(
            root_certificates=[store.root.der], expected_bundle_id=BUNDLE_ID
        )
        with pytest.raises(DomainValidationError):
            trusting.verify(signed)

    def test_rejects_an_expired_certificate(self) -> None:
        past = datetime.now(UTC) - timedelta(days=400)
        store = FakeAppStore()
        store.leaf = _issue(
            "Expired Leaf",
            issuer=store.intermediate,
            not_before=past,
            not_after=past + timedelta(days=30),
        )
        verifier = AppStoreVerifier(
            root_certificates=[store.root.der], expected_bundle_id=BUNDLE_ID
        )

        with pytest.raises(DomainValidationError):
            verifier.verify(store.sign(_claims()))

    def test_rejects_a_genuine_purchase_made_in_another_app(
        self, store: FakeAppStore, verifier: AppStoreVerifier
    ) -> None:
        """Apple really signed it — for somebody else's application."""
        signed = store.sign(_claims(bundleId="com.competitor.app"))

        with pytest.raises(DomainValidationError):
            verifier.verify(signed)

    def test_rejects_rubbish(self, verifier: AppStoreVerifier) -> None:
        with pytest.raises(DomainValidationError):
            verifier.verify("not-a-token")


class TestSandboxPolicy:
    """Sandbox purchases are free, and Apple signs them with the same chain."""

    def test_rejects_a_sandbox_transaction_by_default(
        self, store: FakeAppStore, verifier: AppStoreVerifier
    ) -> None:
        signed = store.sign(_claims(environment="Sandbox"))

        with pytest.raises(DomainValidationError):
            verifier.verify(signed)

    def test_accepts_a_sandbox_transaction_where_that_is_configured(
        self, store: FakeAppStore
    ) -> None:
        """Testing against the sandbox has to work somewhere — just not in production."""
        verifier = AppStoreVerifier(
            root_certificates=[store.root.der],
            expected_bundle_id=BUNDLE_ID,
            allow_sandbox=True,
        )

        transaction = verifier.verify(store.sign(_claims(environment="Sandbox")))

        assert transaction.environment is StoreEnvironment.SANDBOX

    def test_production_transactions_are_unaffected_by_the_sandbox_setting(
        self, store: FakeAppStore
    ) -> None:
        verifier = AppStoreVerifier(
            root_certificates=[store.root.der],
            expected_bundle_id=BUNDLE_ID,
            allow_sandbox=True,
        )

        transaction = verifier.verify(store.sign(_claims()))

        assert transaction.environment is StoreEnvironment.PRODUCTION


class TestMalformedPayloads:
    """Signed by the right key, but missing what a transaction must carry."""

    @pytest.mark.parametrize(
        "missing", ["productId", "originalTransactionId", "transactionId", "purchaseDate"]
    )
    def test_rejects_a_transaction_missing_a_required_field(
        self, store: FakeAppStore, verifier: AppStoreVerifier, missing: str
    ) -> None:
        claims = _claims()
        del claims[missing]

        with pytest.raises(DomainValidationError):
            verifier.verify(store.sign(claims))

    def test_treats_a_missing_expiry_as_no_expiry(
        self, store: FakeAppStore, verifier: AppStoreVerifier
    ) -> None:
        """Non-renewing products carry no expiry date."""
        claims = _claims()
        del claims["expiresDate"]

        transaction = verifier.verify(store.sign(claims))

        assert transaction.expires_at is None

    def test_reads_a_revocation_date(self, store: FakeAppStore, verifier: AppStoreVerifier) -> None:
        revoked = datetime.now(UTC) - timedelta(hours=2)
        signed = store.sign(_claims(revocationDate=int(revoked.timestamp() * 1000)))

        transaction = verifier.verify(signed)

        assert transaction.revoked_at is not None


class TestUnverifiedDecoding:
    """The diagnostic helper must stay useless as a decision-making tool."""

    def test_reads_claims_without_checking_anything(self, store: FakeAppStore) -> None:
        assert decode_unverified(store.sign(_claims()))["bundleId"] == BUNDLE_ID

    def test_returns_nothing_for_rubbish_rather_than_raising(self) -> None:
        assert decode_unverified("nonsense") == {}
