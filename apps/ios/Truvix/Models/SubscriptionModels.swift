import Foundation

/// Where a subscription stands, as the App Store reports it.
enum EntitlementStatus: String, Codable, Sendable {
    case active
    case expired
    case inGracePeriod = "in_grace_period"
    case inBillingRetry = "in_billing_retry"
    case revoked

    /// A short line explaining the state to the person in it.
    var explanation: String? {
        switch self {
        case .active:
            nil
        case .expired:
            "Aboneliğin sona erdi."
        case .inGracePeriod:
            "Ödeme alınamadı. Erişimin şimdilik devam ediyor."
        case .inBillingRetry:
            "Ödeme yeniden deneniyor. Erişimin şimdilik devam ediyor."
        case .revoked:
            "Bu abonelik iade edildi."
        }
    }
}

/// Which App Store issued a transaction.
enum StoreEnvironment: String, Codable, Sendable {
    case sandbox
    case production
}

/// One subscription the account holds.
struct Entitlement: Codable, Sendable, Identifiable, Equatable {
    let id: UUID
    let productId: String
    let status: EntitlementStatus
    let environment: StoreEnvironment
    let purchasedAt: Date
    let expiresAt: Date?
    let isCurrent: Bool
}

/// The account's plan and what stands behind it.
struct SubscriptionState: Codable, Sendable, Equatable {
    let tier: SubscriptionTier
    let isPremium: Bool
    let entitlements: [Entitlement]

    /// The subscription currently granting access, if any.
    var currentEntitlement: Entitlement? {
        entitlements.first { $0.isCurrent }
    }

    /// The state of a brand new account.
    static let free = SubscriptionState(tier: .free, isPremium: false, entitlements: [])
}

/// A signed transaction being sent to the backend for verification.
struct RedeemRequest: Encodable, Sendable {
    let signedTransaction: String
}
