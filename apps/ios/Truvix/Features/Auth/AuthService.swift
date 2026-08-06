import Foundation

/// The authentication calls the app makes, expressed as a protocol so that
/// screens can be exercised in tests without a network or a Keychain.
protocol AuthServicing: Sendable {
    func register(_ request: RegistrationRequest) async throws(APIError) -> UserProfile
    func signIn(email: String, password: String) async throws(APIError) -> UserProfile
    func currentUser() async throws(APIError) -> UserProfile
    func signOut() async
    var hasStoredSession: Bool { get async }

    /// Ask the backend to mail a fresh verification link.
    func sendVerificationEmail() async throws(APIError)

    /// Permanently delete the signed-in account.
    ///
    /// - Parameter password: Confirmation that the account holder means it.
    func deleteAccount(password: String) async throws(APIError)
}

/// Talks to the backend's `/auth` endpoints.
struct AuthService: AuthServicing {
    private let client: APIClient

    init(client: APIClient) {
        self.client = client
    }

    func register(_ request: RegistrationRequest) async throws(APIError) -> UserProfile {
        let response: AuthenticatedResponse = try await client.send(
            APIRequest(
                method: .post,
                path: "auth/register",
                body: request,
                requiresAuthentication: false
            )
        )
        try await persist(response)
        return response.user
    }

    func signIn(email: String, password: String) async throws(APIError) -> UserProfile {
        let response: AuthenticatedResponse = try await client.send(
            APIRequest(
                method: .post,
                path: "auth/login",
                body: LoginRequest(email: email, password: password),
                requiresAuthentication: false
            )
        )
        try await persist(response)
        return response.user
    }

    func currentUser() async throws(APIError) -> UserProfile {
        try await client.send(APIRequest(path: "auth/me"))
    }

    func sendVerificationEmail() async throws(APIError) {
        try await client.send(APIRequest(method: .post, path: "auth/email/verification"))
    }

    func deleteAccount(password: String) async throws(APIError) {
        try await client.send(
            APIRequest(
                method: .delete,
                path: "auth/me",
                body: DeleteAccountRequest(password: password)
            )
        )
    }

    /// End the session, locally regardless of what the server says.
    ///
    /// If the network call fails the tokens are still discarded: a user who
    /// taps sign out must not stay signed in because the server was briefly
    /// unreachable.
    func signOut() async {
        await client.clearSession()
    }

    var hasStoredSession: Bool {
        get async { await client.hasSession }
    }

    private func persist(_ response: AuthenticatedResponse) async throws(APIError) {
        do {
            try await client.storeSession(response.tokens.asTokenPair())
        } catch {
            throw .unknown(error.localizedDescription)
        }
    }
}
