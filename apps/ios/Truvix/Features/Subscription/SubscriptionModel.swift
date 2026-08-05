import Foundation
import OSLog
import Observation

/// The subscriptions this app sells, in the order the paywall lists them.
enum SubscriptionProduct {
    static let monthly = "app.truvix.premium.monthly"
    static let yearly = "app.truvix.premium.yearly"

    static let all = [yearly, monthly]
}

/// Drives the paywall: loads what is on sale, buys it, and has the backend
/// verify what the store handed back.
///
/// The store's word is never taken for what an account is entitled to. A
/// purchase is only premium once the backend has checked the receipt against
/// Apple's certificate chain and said so, which is also what stops a receipt
/// from one account being replayed on another.
@Observable
@MainActor
final class SubscriptionModel {
    /// Where the paywall is in its work.
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded([StoreProduct])
        case failed(String)
    }

    private(set) var state: LoadState = .idle
    private(set) var subscription: SubscriptionState = .free
    /// Set while a purchase or restore is in flight, to disable the buttons.
    private(set) var isWorking = false
    /// A message worth showing the customer, cleared once seen.
    var alert: String?
    /// Set when a purchase succeeded, so the paywall can dismiss itself.
    private(set) var didBecomePremium = false

    private let api: any TruvixAPI
    private let store: any StoreClient
    private let logger = Logger(subsystem: "app.truvix.ios", category: "subscription")
    // Not UI state, so kept out of observation. Cancelled from `deinit`, which
    // Swift runs outside the main actor; the value is only ever written on the
    // main actor and read once at teardown, so nothing races over it.
    @ObservationIgnored private nonisolated(unsafe) var updatesTask: Task<Void, Never>?

    init(api: any TruvixAPI, store: any StoreClient = LiveStoreClient()) {
        self.api = api
        self.store = store
    }

    deinit {
        updatesTask?.cancel()
    }

    /// Load the plans on sale and the account's current standing.
    func load() async {
        state = .loading
        await refreshSubscription()

        do {
            let products = try await store.products(for: SubscriptionProduct.all)
            guard !products.isEmpty else {
                state = .failed(StoreError.productsUnavailable.localizedDescription)
                return
            }
            state = .loaded(products)
        } catch {
            logger.error("Ürünler yüklenemedi: \(error.localizedDescription, privacy: .public)")
            state = .failed(error.localizedDescription)
        }
    }

    /// Begin watching for transactions the store reports on its own.
    ///
    /// Renewals, purchases made on another device and approvals granted after
    /// the fact all arrive this way rather than from a call this app made, so
    /// the listener runs for as long as the app does.
    func startListeningForStoreUpdates() {
        guard updatesTask == nil else { return }
        updatesTask = Task { [weak self, store] in
            for await purchase in store.updates() {
                guard let self else { return }
                await redeem(purchase, initiatedByCustomer: false)
            }
        }
    }

    /// Buy a plan.
    func purchase(_ product: StoreProduct) async {
        guard !isWorking else { return }
        isWorking = true
        defer { isWorking = false }

        do {
            switch try await store.purchase(productID: product.id) {
            case let .purchased(purchase):
                await redeem(purchase, initiatedByCustomer: true)
            case .cancelled:
                // Deliberate; saying anything about it would be noise.
                break
            case .pending:
                alert = "Satın alma onay bekliyor. Onaylandığında aboneliğin açılacak."
            }
        } catch {
            logger.error("Satın alma hatası: \(error.localizedDescription, privacy: .public)")
            alert = error.localizedDescription
        }
    }

    /// Restore a subscription bought earlier or on another device.
    func restore() async {
        guard !isWorking else { return }
        isWorking = true
        defer { isWorking = false }

        let purchases = await store.currentPurchases()
        guard !purchases.isEmpty else {
            await refreshSubscription()
            alert = subscription.isPremium
                ? nil
                : "Bu Apple hesabında geri yüklenecek bir abonelik bulunamadı."
            return
        }

        for purchase in purchases {
            await redeem(purchase, initiatedByCustomer: true)
        }
    }

    /// Re-read the account's plan from the backend.
    func refreshSubscription() async {
        do {
            subscription = try await api.subscriptionState()
        } catch {
            // The plan is worth showing stale rather than not at all; a failure
            // here must not stop the paywall from listing what is on sale.
            logger.error("Abonelik durumu okunamadı: \(error.localizedDescription, privacy: .public)")
        }
    }

    // MARK: - Verification

    /// Send a receipt to the backend and act on what it says.
    ///
    /// - Parameters:
    ///   - purchase: The signed transaction from the store.
    ///   - initiatedByCustomer: Whether somebody is watching. Failures during a
    ///     purchase they started deserve an explanation; the same failure on a
    ///     background renewal does not, and would arrive without context.
    private func redeem(_ purchase: SignedPurchase, initiatedByCustomer: Bool) async {
        do {
            subscription = try await api.redeem(signedTransaction: purchase.signedTransaction)

            // Only now: an unfinished transaction is redelivered next launch,
            // which is exactly what should happen if the backend never learned
            // about this purchase.
            await store.finish(transactionID: purchase.transactionID)

            if subscription.isPremium {
                didBecomePremium = true
            }
        } catch {
            handle(error, initiatedByCustomer: initiatedByCustomer)
        }
    }

    /// Explain a rejected verification, without discarding the purchase.
    ///
    /// The transaction is deliberately left unfinished whatever went wrong. The
    /// store then redelivers it on the next launch, which is what should happen
    /// in every case that can reach here: a dropped connection resolves itself,
    /// and a subscription already tied to another account resolves when its
    /// owner signs in. Finishing it to stop the retries would throw away a
    /// purchase somebody paid for.
    private func handle(_ error: APIError, initiatedByCustomer: Bool) {
        logger.error("Doğrulama reddedildi: \(error.localizedDescription, privacy: .public)")
        guard initiatedByCustomer else { return }
        alert = error.localizedDescription
    }
}
