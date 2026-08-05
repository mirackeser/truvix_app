import Foundation
import OSLog
import StoreKit

/// A product offered for sale, reduced to what the paywall needs to draw it.
struct StoreProduct: Sendable, Identifiable, Equatable {
    let id: String
    let displayName: String
    let description: String
    /// Already formatted in the store's currency and the device's locale.
    let displayPrice: String
    /// "ay" or "yıl" for a subscription, `nil` for anything else.
    let periodDescription: String?

    /// The price with its period, as it should read on a button.
    var priceSummary: String {
        guard let periodDescription else { return displayPrice }
        return "\(displayPrice) / \(periodDescription)"
    }
}

/// A purchase that completed, carrying the receipt the backend must verify.
struct SignedPurchase: Sendable, Equatable {
    /// The JWS StoreKit issued. Meaningless until the backend verifies it.
    let signedTransaction: String
    /// Identifies the transaction to finish once the backend has accepted it.
    let transactionID: UInt64
}

/// What came of asking to buy something.
enum PurchaseOutcome: Sendable, Equatable {
    case purchased(SignedPurchase)
    /// The customer changed their mind; not an error.
    case cancelled
    /// Awaiting approval, typically a parent's. The result arrives later
    /// through the update stream rather than from the call that started it.
    case pending
}

/// Things that can go wrong talking to the App Store.
enum StoreError: LocalizedError, Sendable, Equatable {
    case productsUnavailable
    case unknownProduct(String)
    case notVerified
    case failed(String)

    var errorDescription: String? {
        switch self {
        case .productsUnavailable:
            "Abonelik seçenekleri şu anda yüklenemedi."
        case .unknownProduct:
            "Bu abonelik seçeneği artık sunulmuyor."
        case .notVerified:
            "Satın alma doğrulanamadı."
        case let .failed(reason):
            reason
        }
    }
}

/// The App Store, as this app uses it.
///
/// Kept behind a protocol so the purchase flow can be tested without a store:
/// StoreKit's own test support needs a running app, and the parts worth testing
/// here are what the app does with a receipt rather than how one is minted.
protocol StoreClient: Sendable {
    /// Load the products on sale, in the order given.
    func products(for identifiers: [String]) async throws(StoreError) -> [StoreProduct]

    /// Ask to buy a product.
    func purchase(productID: String) async throws(StoreError) -> PurchaseOutcome

    /// Every transaction the store has for this customer, verified receipts only.
    ///
    /// Used to restore purchases: the account may be signed in on a new device,
    /// or have reinstalled the app.
    func currentPurchases() async -> [SignedPurchase]

    /// Transactions the store reports outside a purchase this app started:
    /// renewals, approvals granted later, purchases made on another device.
    func updates() -> AsyncStream<SignedPurchase>

    /// Tell the store a transaction has been dealt with.
    ///
    /// Must not be called before the backend has recorded the purchase. An
    /// unfinished transaction is redelivered on the next launch, which is what
    /// stops a purchase being lost if the app dies mid-flow; finishing it early
    /// throws away that safety net and the customer pays for nothing.
    func finish(transactionID: UInt64) async
}

/// The live client, talking to StoreKit.
struct LiveStoreClient: StoreClient {
    private let logger = Logger(subsystem: "app.truvix.ios", category: "store")

    func products(for identifiers: [String]) async throws(StoreError) -> [StoreProduct] {
        let loaded: [Product]
        do {
            loaded = try await Product.products(for: identifiers)
        } catch {
            logger.error("Ürünler yüklenemedi: \(error.localizedDescription, privacy: .public)")
            throw StoreError.productsUnavailable
        }

        // Preserve the order asked for: the paywall lists plans deliberately,
        // and the store returns them in no particular order.
        let byID = Dictionary(uniqueKeysWithValues: loaded.map { ($0.id, $0) })
        return identifiers.compactMap { byID[$0].map(Self.describe) }
    }

    func purchase(productID: String) async throws(StoreError) -> PurchaseOutcome {
        let products: [Product]
        do {
            products = try await Product.products(for: [productID])
        } catch {
            throw StoreError.productsUnavailable
        }
        guard let product = products.first else {
            throw StoreError.unknownProduct(productID)
        }

        let result: Product.PurchaseResult
        do {
            result = try await product.purchase()
        } catch {
            logger.error("Satın alma başarısız: \(error.localizedDescription, privacy: .public)")
            throw StoreError.failed(error.localizedDescription)
        }

        switch result {
        case let .success(verification):
            guard let purchase = Self.signedPurchase(from: verification) else {
                throw StoreError.notVerified
            }
            return .purchased(purchase)
        case .userCancelled:
            return .cancelled
        case .pending:
            return .pending
        @unknown default:
            // A result this build does not understand is not a purchase to act
            // on; treating it as pending waits for the store to say more.
            return .pending
        }
    }

    func currentPurchases() async -> [SignedPurchase] {
        var purchases: [SignedPurchase] = []
        for await verification in Transaction.currentEntitlements {
            if let purchase = Self.signedPurchase(from: verification) {
                purchases.append(purchase)
            }
        }
        return purchases
    }

    func updates() -> AsyncStream<SignedPurchase> {
        AsyncStream { continuation in
            let task = Task {
                for await verification in Transaction.updates {
                    if let purchase = Self.signedPurchase(from: verification) {
                        continuation.yield(purchase)
                    }
                }
                continuation.finish()
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    func finish(transactionID: UInt64) async {
        for await verification in Transaction.unfinished {
            guard case let .verified(transaction) = verification,
                  transaction.id == transactionID
            else { continue }
            await transaction.finish()
            return
        }
    }

    // MARK: - Translation

    private static func signedPurchase(
        from result: VerificationResult<Transaction>
    ) -> SignedPurchase? {
        // StoreKit's own check is not what the app relies on — the backend
        // verifies the same receipt against Apple's certificate chain, and only
        // its answer decides anything. Discarding a locally unverified receipt
        // here just avoids a pointless round trip.
        guard case let .verified(transaction) = result else { return nil }
        return SignedPurchase(
            signedTransaction: result.jwsRepresentation,
            transactionID: transaction.id
        )
    }

    private static func describe(_ product: Product) -> StoreProduct {
        StoreProduct(
            id: product.id,
            displayName: product.displayName,
            description: product.description,
            displayPrice: product.displayPrice,
            periodDescription: product.subscription.map { subscription in
                Self.describe(subscription.subscriptionPeriod)
            }
        )
    }

    private static func describe(_ period: Product.SubscriptionPeriod) -> String {
        let unit: String
        switch period.unit {
        case .day: unit = "gün"
        case .week: unit = "hafta"
        case .month: unit = "ay"
        case .year: unit = "yıl"
        @unknown default: unit = "dönem"
        }
        return period.value == 1 ? unit : "\(period.value) \(unit)"
    }
}
