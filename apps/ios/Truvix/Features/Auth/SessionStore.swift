import Foundation
import OSLog
import Observation

/// Where the app is in its sign-in lifecycle.
///
/// `restoring` exists so the first frame after launch is a splash rather than
/// the sign-in screen: showing sign-in and then replacing it with the home
/// screen half a second later reads as a bug to the person holding the phone.
enum SessionPhase: Equatable, Sendable {
    case restoring
    case signedOut
    case signedIn(UserProfile)

    var user: UserProfile? {
        if case let .signedIn(user) = self { return user }
        return nil
    }
}

/// The single source of truth for who is signed in.
///
/// Views observe this; nothing else in the app decides whether a session
/// exists, so there is exactly one place that can be wrong.
@MainActor
@Observable
final class SessionStore {
    private(set) var phase: SessionPhase = .restoring

    private let auth: any AuthServicing
    private let client: APIClient
    private let logger = Logger(subsystem: "app.truvix.ios", category: "session")

    init(client: APIClient, auth: any AuthServicing) {
        self.client = client
        self.auth = auth
    }

    /// Restore a stored session, or fall back to signed out.
    ///
    /// A stored token is not trusted on its own: it is verified against the
    /// backend, because it may have been revoked while the app was closed.
    func restore() async {
        await client.setSessionExpiredHandler { [weak self] in
            Task { @MainActor in self?.handleExpiry() }
        }

        if let credentials = LaunchOverrides.automaticSignIn {
            do {
                phase = .signedIn(
                    try await auth.signIn(
                        email: credentials.email,
                        password: credentials.password
                    )
                )
                logger.info("Automatic sign-in succeeded for \(credentials.email, privacy: .public)")
                return
            } catch {
                // Logged rather than swallowed: a silent failure here looks
                // identical to the override not being read at all, which is
                // exactly the confusion that wastes an afternoon.
                logger.error("Automatic sign-in failed: \(error.localizedDescription)")
            }
        }

        guard await auth.hasStoredSession else {
            phase = .signedOut
            return
        }

        do {
            phase = .signedIn(try await auth.currentUser())
        } catch {
            await auth.signOut()
            phase = .signedOut
        }
    }

    func signedIn(as user: UserProfile) {
        phase = .signedIn(user)
    }

    func signOut() async {
        await auth.signOut()
        phase = .signedOut
    }

    /// React to the client discovering the session is no longer valid.
    private func handleExpiry() {
        guard phase != .signedOut else { return }
        phase = .signedOut
    }
}
