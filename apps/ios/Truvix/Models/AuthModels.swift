import Foundation

/// The commercial plan an account is on.
enum SubscriptionTier: String, Codable, Sendable {
    case free
    case premium

    var displayName: String {
        switch self {
        case .free: "Ücretsiz"
        case .premium: "Premium"
        }
    }
}

/// The public view of the signed-in account.
struct UserProfile: Codable, Identifiable, Equatable, Sendable {
    let id: UUID
    let email: String
    let fullName: String
    let phoneNumber: String?
    let subscriptionTier: SubscriptionTier
    let emailVerified: Bool
    let createdAt: Date

    /// The first name, as the home screen's greeting uses it.
    var firstName: String {
        fullName.split(separator: " ").first.map(String.init) ?? fullName
    }

    var isPremium: Bool { subscriptionTier == .premium }
}

/// A freshly issued token pair, as the API returns it.
struct TokenPairResponse: Codable, Sendable {
    let accessToken: String
    let refreshToken: String
    let tokenType: String
    /// The access token's lifetime in seconds.
    let expiresIn: Int

    /// Convert to the stored form, resolving the lifetime into an instant.
    ///
    /// Storing an absolute expiry rather than a duration means the value stays
    /// correct across app launches, where a duration would silently restart.
    func asTokenPair(now: Date = .now) -> TokenPair {
        TokenPair(
            accessToken: accessToken,
            refreshToken: refreshToken,
            accessTokenExpiry: now.addingTimeInterval(TimeInterval(expiresIn))
        )
    }
}

/// The account together with the tokens issued for it.
struct AuthenticatedResponse: Codable, Sendable {
    let user: UserProfile
    let tokens: TokenPairResponse
}

// MARK: - Requests

struct RegistrationRequest: Encodable, Sendable {
    let email: String
    let password: String
    let fullName: String
    var phoneNumber: String?
}

struct LoginRequest: Encodable, Sendable {
    let email: String
    let password: String
}

struct LogoutRequest: Encodable, Sendable {
    let refreshToken: String
}
