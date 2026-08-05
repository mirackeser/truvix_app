# Truvix iOS

A native SwiftUI app for Truvix, built against the backend in `apps/backend`.

## Requirements

- Xcode 26.6 or later, iOS 26.5 SDK
- Swift 6.3, complete strict concurrency
- A running backend on `http://127.0.0.1:8000` for anything beyond the sign-in
  screen

## Running

```bash
open Truvix.xcodeproj
```

The app signs into the local backend. Start it first:

```bash
cd ../backend && uv run uvicorn truvix.main:app --reload
```

## Testing

```bash
xcodebuild -project Truvix.xcodeproj -scheme Truvix -destination 'platform=iOS Simulator,name=iPhone 17 Pro' test
```

Most of the suite runs against stubs and needs nothing else. `LiveBackendTests`
talks to a real backend and needs it started with rate limiting off, or the
suite exhausts its own budget and reads the `429` as a test failure:

```bash
TRUVIX_RATELIMIT_ENABLED=false uv run uvicorn truvix.main:app
```

## Debug launch overrides

Compiled out of release builds. They exist so any screen can be reached without
tapping through the app, which is what makes a screenshot worth taking:

```bash
xcrun simctl launch booted app.truvix.ios \
  -truvixSignInEmail you@example.com \
  -truvixSignInPassword your-passphrase \
  -truvixInitialTab profile \
  -truvixOpenPaywall YES
```

`truvixSkipOnboarding`, `truvixOpenNewAnalysis` and `truvixOpenVehicle` work the
same way.

## Subscriptions

Premium is sold through StoreKit 2. The app never decides what an account is
entitled to: it sends the signed transaction to the backend, which verifies it
against Apple's certificate chain, and only the backend's answer changes the
tier. See `docs/00_decisions/0001-in-app-purchase-for-subscriptions.md`.

A transaction is finished only after the backend has recorded it. An unfinished
transaction is redelivered on the next launch, which is what stops a purchase
being lost if the app dies mid-flow; finishing it early would throw away a
purchase somebody paid for.

### One manual step before purchases work locally

Products come from the store, so the simulator needs a StoreKit configuration
file. It has to be created through Xcode's editor — the format is undocumented
and a hand-written file is silently ignored:

1. **File → New → File → StoreKit Configuration File**, named `Truvix`, saved
   into `Truvix/Resources/`.
2. Add an auto-renewable subscription group with two subscriptions whose product
   ids match `SubscriptionProduct` in
   `Truvix/Features/Subscription/SubscriptionModel.swift`:
   - `app.truvix.premium.yearly`, one year
   - `app.truvix.premium.monthly`, one month
3. **Product → Scheme → Edit Scheme → Run → Options → StoreKit Configuration**,
   and select it.

Until that exists the paywall lists no plans and says so; it does not pretend to
have loaded. The ids are strings on both sides, so a typo shows up as an empty
paywall rather than as a build error — worth checking first if the plans do not
appear.
