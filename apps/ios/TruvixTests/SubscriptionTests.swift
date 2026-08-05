import Foundation
import Testing

@testable import Truvix

// MARK: - Doubles

/// A store that hands back whatever the test tells it to.
private final class StubStore: StoreClient, @unchecked Sendable {
    var products: [StoreProduct] = [
        StoreProduct(
            id: SubscriptionProduct.yearly,
            displayName: "Yıllık",
            description: "12 ay",
            displayPrice: "₺1.999,00",
            periodDescription: "yıl"
        ),
        StoreProduct(
            id: SubscriptionProduct.monthly,
            displayName: "Aylık",
            description: "1 ay",
            displayPrice: "₺249,00",
            periodDescription: "ay"
        )
    ]
    var productsError: StoreError?
    var purchaseOutcome: PurchaseOutcome = .purchased(
        SignedPurchase(signedTransaction: "signed-jws", transactionID: 42)
    )
    var purchaseError: StoreError?
    var restorablePurchases: [SignedPurchase] = []

    private(set) var finishedTransactionIDs: [UInt64] = []

    private let continuationLock = NSLock()
    private var continuation: AsyncStream<SignedPurchase>.Continuation?

    func products(for identifiers: [String]) async throws(StoreError) -> [StoreProduct] {
        if let productsError { throw productsError }
        return products
    }

    func purchase(productID: String) async throws(StoreError) -> PurchaseOutcome {
        if let purchaseError { throw purchaseError }
        return purchaseOutcome
    }

    func currentPurchases() async -> [SignedPurchase] { restorablePurchases }

    /// Whether the model has attached to the update stream.
    var isListening: Bool { continuationLock.withLock { continuation != nil } }

    func updates() -> AsyncStream<SignedPurchase> {
        AsyncStream { continuation in
            continuationLock.withLock { self.continuation = continuation }
        }
    }

    func finish(transactionID: UInt64) async {
        finishedTransactionIDs.append(transactionID)
    }

    /// Push a transaction as though the store reported it on its own.
    func emit(_ purchase: SignedPurchase) {
        continuationLock.withLock { continuation }?.yield(purchase)
    }
}

/// A backend that records what it was asked to verify.
private final class StubAPI: SubscriptionAPIStub, @unchecked Sendable {
    var stateToReturn: SubscriptionState = .free
    var redeemResult: Result<SubscriptionState, APIError> = .success(
        SubscriptionState(tier: .premium, isPremium: true, entitlements: [])
    )
    private(set) var redeemedPayloads: [String] = []

    override func subscriptionState() async throws(APIError) -> SubscriptionState {
        stateToReturn
    }

    override func redeem(signedTransaction: String) async throws(APIError) -> SubscriptionState {
        redeemedPayloads.append(signedTransaction)
        switch redeemResult {
        case let .success(state): return state
        case let .failure(error): throw error
        }
    }
}

/// Wait for something to become true, or give up.
///
/// Used instead of a fixed sleep: a sleep long enough to be reliable makes the
/// suite slow, and a short one makes it flaky depending on what else the machine
/// is doing.
private func eventually(
    timeout: Duration = .seconds(2),
    _ condition: @Sendable () async -> Bool
) async -> Bool {
    let deadline = ContinuousClock.now.advanced(by: timeout)
    while ContinuousClock.now < deadline {
        if await condition() { return true }
        try? await Task.sleep(for: .milliseconds(10))
    }
    return await condition()
}

private func entitlement(
    status: EntitlementStatus = .active,
    isCurrent: Bool = true
) -> Entitlement {
    Entitlement(
        id: UUID(),
        productId: SubscriptionProduct.monthly,
        status: status,
        environment: .production,
        purchasedAt: .now,
        expiresAt: Date(timeIntervalSinceNow: 60 * 60 * 24 * 30),
        isCurrent: isCurrent
    )
}

// MARK: - Tests

@Suite("Subscription purchase flow")
@MainActor
struct SubscriptionModelTests {

    private func make(
        api: StubAPI = StubAPI(),
        store: StubStore = StubStore()
    ) -> SubscriptionModel {
        SubscriptionModel(api: api, store: store)
    }

    @Test("Plans load in the order the paywall lists them")
    func loadsPlansInOrder() async {
        let store = StubStore()
        let subject = make(store: store)

        await subject.load()

        guard case let .loaded(products) = subject.state else {
            Issue.record("Beklenen yüklenmiş durum, gelen: \(subject.state)")
            return
        }
        #expect(products.map(\.id) == [SubscriptionProduct.yearly, SubscriptionProduct.monthly])
    }

    @Test("A store that cannot list products leaves an explained failure")
    func failedLoadIsExplained() async {
        let store = StubStore()
        store.productsError = .productsUnavailable
        let subject = make(store: store)

        await subject.load()

        guard case let .failed(message) = subject.state else {
            Issue.record("Beklenen hata durumu, gelen: \(subject.state)")
            return
        }
        #expect(!message.isEmpty)
    }

    @Test("A purchase is sent to the backend rather than trusted locally")
    func purchaseIsVerifiedServerSide() async {
        let api = StubAPI()
        let store = StubStore()
        let subject = make(api: api, store: store)
        await subject.load()

        await subject.purchase(store.products[0])

        #expect(api.redeemedPayloads == ["signed-jws"])
        #expect(subject.subscription.isPremium)
        #expect(subject.didBecomePremium)
    }

    @Test("The transaction is only finished once the backend has accepted it")
    func transactionFinishedAfterVerification() async {
        let api = StubAPI()
        let store = StubStore()
        let subject = make(api: api, store: store)
        await subject.load()

        await subject.purchase(store.products[0])

        #expect(store.finishedTransactionIDs == [42])
    }

    @Test("A rejected purchase is left unfinished so the store redelivers it")
    func rejectedPurchaseIsNotFinished() async {
        // The customer has paid. Finishing here would throw the purchase away.
        let api = StubAPI()
        api.redeemResult = .failure(.offline)
        let store = StubStore()
        let subject = make(api: api, store: store)
        await subject.load()

        await subject.purchase(store.products[0])

        #expect(store.finishedTransactionIDs.isEmpty)
        #expect(subject.alert != nil)
        #expect(!subject.didBecomePremium)
    }

    @Test("A subscription owned by another account explains itself")
    func conflictIsExplained() async {
        let api = StubAPI()
        api.redeemResult = .failure(
            .server(
                ProblemDetail(
                    title: "Conflict",
                    status: 409,
                    detail: "Bu abonelik başka bir hesaba tanımlı.",
                    code: "conflict",
                    requestID: nil
                )
            )
        )
        let store = StubStore()
        let subject = make(api: api, store: store)
        await subject.load()

        await subject.purchase(store.products[0])

        #expect(subject.alert == "Bu abonelik başka bir hesaba tanımlı.")
        #expect(store.finishedTransactionIDs.isEmpty)
    }

    @Test("Cancelling says nothing, because it was deliberate")
    func cancellingIsSilent() async {
        let store = StubStore()
        store.purchaseOutcome = .cancelled
        let api = StubAPI()
        let subject = make(api: api, store: store)
        await subject.load()

        await subject.purchase(store.products[0])

        #expect(subject.alert == nil)
        #expect(api.redeemedPayloads.isEmpty)
        #expect(!subject.didBecomePremium)
    }

    @Test("A purchase awaiting approval says so rather than failing")
    func pendingPurchaseIsExplained() async {
        let store = StubStore()
        store.purchaseOutcome = .pending
        let subject = make(store: store)
        await subject.load()

        await subject.purchase(store.products[0])

        #expect(subject.alert != nil)
        #expect(!subject.didBecomePremium)
    }

    @Test("Restoring sends every receipt the store still holds")
    func restoreSendsEveryReceipt() async {
        let api = StubAPI()
        let store = StubStore()
        store.restorablePurchases = [
            SignedPurchase(signedTransaction: "first", transactionID: 1),
            SignedPurchase(signedTransaction: "second", transactionID: 2)
        ]
        let subject = make(api: api, store: store)

        await subject.restore()

        #expect(api.redeemedPayloads == ["first", "second"])
    }

    @Test("Restoring nothing says so instead of failing silently")
    func restoreWithNothingToRestore() async {
        let api = StubAPI()
        let store = StubStore()
        let subject = make(api: api, store: store)

        await subject.restore()

        #expect(subject.alert != nil)
    }

    @Test("A renewal reported by the store is verified without anybody asking")
    func storeUpdateIsRedeemed() async {
        let api = StubAPI()
        let store = StubStore()
        let subject = make(api: api, store: store)
        subject.startListeningForStoreUpdates()

        #expect(await eventually { store.isListening })
        store.emit(SignedPurchase(signedTransaction: "renewal", transactionID: 7))

        #expect(await eventually { await api.redeemedPayloads == ["renewal"] })
        #expect(store.finishedTransactionIDs == [7])
    }

    @Test("A background renewal that fails does not interrupt with an alert")
    func backgroundFailureIsSilent() async {
        let api = StubAPI()
        api.redeemResult = .failure(.offline)
        let store = StubStore()
        let subject = make(api: api, store: store)
        subject.startListeningForStoreUpdates()

        #expect(await eventually { store.isListening })
        store.emit(SignedPurchase(signedTransaction: "renewal", transactionID: 7))

        #expect(await eventually { await api.redeemedPayloads == ["renewal"] })
        #expect(subject.alert == nil)
        #expect(store.finishedTransactionIDs.isEmpty)
    }

    @Test("The account's existing plan is read when the paywall opens")
    func existingPlanIsShown() async {
        let api = StubAPI()
        api.stateToReturn = SubscriptionState(
            tier: .premium,
            isPremium: true,
            entitlements: [entitlement()]
        )
        let subject = make(api: api)

        await subject.load()

        #expect(subject.subscription.isPremium)
        #expect(subject.subscription.currentEntitlement != nil)
    }
}

@Suite("Subscription decoding")
struct SubscriptionDecodingTests {

    @Test("The backend's subscription state decodes")
    func decodesState() throws {
        let json = """
        {
          "tier": "premium",
          "is_premium": true,
          "entitlements": [
            {
              "id": "019FC936-2E85-77AE-B3D1-9239C9BD486B",
              "product_id": "app.truvix.premium.monthly",
              "status": "in_billing_retry",
              "environment": "production",
              "purchased_at": "2026-08-01T10:00:00.123456Z",
              "expires_at": "2026-09-01T10:00:00Z",
              "is_current": true
            }
          ]
        }
        """

        let state = try JSONDecoder.truvix.decode(
            SubscriptionState.self,
            from: Data(json.utf8)
        )

        #expect(state.isPremium)
        #expect(state.currentEntitlement?.status == .inBillingRetry)
        #expect(state.currentEntitlement?.productId == "app.truvix.premium.monthly")
    }

    @Test("A subscription with no expiry decodes as one that does not lapse")
    func decodesWithoutExpiry() throws {
        let json = """
        {
          "tier": "free",
          "is_premium": false,
          "entitlements": [
            {
              "id": "019FC936-2E85-77AE-B3D1-9239C9BD486B",
              "product_id": "app.truvix.premium.monthly",
              "status": "expired",
              "environment": "sandbox",
              "purchased_at": "2026-08-01T10:00:00Z",
              "expires_at": null,
              "is_current": false
            }
          ]
        }
        """

        let state = try JSONDecoder.truvix.decode(
            SubscriptionState.self,
            from: Data(json.utf8)
        )

        #expect(!state.isPremium)
        #expect(state.currentEntitlement == nil)
        #expect(state.entitlements.first?.expiresAt == nil)
    }

    @Test("Each status carries an explanation where one is owed")
    func statusExplanations() {
        #expect(EntitlementStatus.active.explanation == nil)
        #expect(EntitlementStatus.inGracePeriod.explanation != nil)
        #expect(EntitlementStatus.inBillingRetry.explanation != nil)
        #expect(EntitlementStatus.revoked.explanation != nil)
    }
}
