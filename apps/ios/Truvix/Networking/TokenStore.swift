import Foundation
import Security

/// Where the session's tokens live between launches.
///
/// The Keychain is used rather than `UserDefaults` because tokens are bearer
/// credentials: anything holding them is the user. `UserDefaults` is a plist in
/// the app container, readable from a backup, whereas Keychain items are
/// hardware-encrypted and — with the accessibility set below — never leave the
/// device in a backup at all.
protocol TokenStoring: Sendable {
    func load() -> TokenPair?
    func save(_ pair: TokenPair) throws
    func clear()
}

/// An issued access and refresh token pair.
struct TokenPair: Codable, Equatable, Sendable {
    let accessToken: String
    let refreshToken: String
    /// When the access token stops being accepted.
    let accessTokenExpiry: Date

    /// Whether the access token is close enough to expiry to refresh first.
    ///
    /// Refreshing slightly early avoids a request failing purely because it was
    /// in flight as the token expired.
    func needsRefresh(now: Date = .now, leeway: TimeInterval = 60) -> Bool {
        accessTokenExpiry.timeIntervalSince(now) <= leeway
    }
}

/// Keychain-backed implementation.
struct KeychainTokenStore: TokenStoring {
    private let service: String
    private let account = "session"

    init(service: String = "app.truvix.ios.session") {
        self.service = service
    }

    func load() -> TokenPair? {
        var query = baseQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else {
            return nil
        }
        return try? JSONDecoder.truvix.decode(TokenPair.self, from: data)
    }

    func save(_ pair: TokenPair) throws {
        let data = try JSONEncoder.truvix.encode(pair)

        // Deleting first makes this an upsert; SecItemUpdate would fail when
        // nothing is stored yet, and a duplicate add would fail when it is.
        SecItemDelete(baseQuery() as CFDictionary)

        var query = baseQuery()
        query[kSecValueData as String] = data
        // The token is needed only while the app is in use, and must never be
        // restored onto a different device from a backup.
        query[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly

        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw KeychainError.unhandled(status: status)
        }
    }

    func clear() {
        SecItemDelete(baseQuery() as CFDictionary)
    }

    private func baseQuery() -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }
}

enum KeychainError: LocalizedError {
    case unhandled(status: OSStatus)

    var errorDescription: String? {
        switch self {
        case let .unhandled(status):
            "Oturum bilgisi cihaza kaydedilemedi (kod \(status))."
        }
    }
}
