# 1. Premium is sold through In-App Purchase

- **Status:** Accepted
- **Date:** 2026-08-05

## Context

Truvix sells a premium tier that raises the daily analysis quota, the garage
size and the copilot allowance. An earlier working assumption was that this
would be billed through a Turkish payment provider — iyzico was the candidate —
because the fees are lower and the money arrives directly.

Apple's App Store Review Guideline 3.1.1 requires In-App Purchase for digital
content or services consumed inside the app. Everything premium unlocks is
consumed inside the app. Billing it another way is grounds for rejection, so the
lower fee is not a trade-off that was ours to make: it is a choice between
shipping and not shipping.

## Decision

Subscriptions are sold through StoreKit 2, and every purchase is verified on the
server before it entitles anything.

The client cannot be trusted to report what it bought — an app that could assert
"I am premium" would make the paywall decorative — so the signed transaction is
sent to `POST /api/v1/subscriptions/redeem`, where three things are checked:

1. the certificate chain terminates at an Apple root, compared by SHA-256
   fingerprint rather than by subject, because a subject line can be copied into
   any self-signed certificate;
2. the signature covers the payload, so it was not edited after signing;
3. the payload names our bundle, so a genuine Apple transaction issued for
   another application cannot be redeemed here.

Two further rules follow from what a transaction is rather than from
cryptography:

- Sandbox transactions are refused unless explicitly configured, and production
  configuration rejects that flag at startup. A sandbox purchase is free but
  carries the same Apple signature as a real one, so the environment claim is
  the only thing separating a paying customer from anybody with a free test
  account.
- Apple's original transaction id is unique in the database, so one purchase
  cannot entitle two accounts.

The account's tier is recomputed from its entitlements rather than toggled, and
refunds arrive through the App Store server notification webhook, since the app
may not be running when they happen.

## Consequences

- Apple takes its commission, and pricing has to be set in App Store Connect
  rather than in our own code.
- Purchases cannot be tested end to end without an App Store Connect
  configuration; the app's own logic is tested against a stubbed store instead,
  and the verifier is tested against certificate hierarchies minted in the test.
- A web or Android client later will need its own billing path, and the
  entitlement model will have to grow a notion of where a subscription came
  from. The `Entitlement` record already stores the store environment, which is
  the seam that would widen.
- Selling anything that is *not* consumed in the app — a physical inspection, a
  report posted to somebody — falls outside 3.1.1 and could be billed directly.
  That is a different product decision, not a revision of this one.
