import Foundation
import Testing

@testable import Truvix

/// An auth service the test drives.
private final class StubAuth: AuthServicing, @unchecked Sendable {
    var user = UserProfile(
        id: UUID(),
        email: "somebody@truvix.app",
        fullName: "Somebody",
        phoneNumber: nil,
        subscriptionTier: .free,
        emailVerified: false,
        createdAt: .now
    )
    var sendError: APIError?
    private(set) var sendCount = 0

    func register(_ request: RegistrationRequest) async throws(APIError) -> UserProfile { user }
    func signIn(email: String, password: String) async throws(APIError) -> UserProfile { user }
    func currentUser() async throws(APIError) -> UserProfile { user }
    func signOut() async {}
    var hasStoredSession: Bool { get async { true } }

    func sendVerificationEmail() async throws(APIError) {
        sendCount += 1
        if let sendError { throw sendError }
    }

    var deleteError: APIError?
    private(set) var deletedWithPassword: [String] = []

    func deleteAccount(password: String) async throws(APIError) {
        deletedWithPassword.append(password)
        if let deleteError { throw deleteError }
    }
}

@Suite("Email verification")
@MainActor
struct EmailVerificationTests {

    private func store(_ auth: StubAuth) -> SessionStore {
        let client = APIClient(
            configuration: APIConfiguration(baseURL: URL(string: "http://localhost")!),
            tokens: InMemoryTokenStore()
        )
        let session = SessionStore(client: client, auth: auth)
        session.signedIn(as: auth.user)
        return session
    }

    @Test("Asking for a link reports that it was sent")
    func successIsReported() async {
        let auth = StubAuth()
        let subject = store(auth)

        let message = await subject.resendVerificationEmail()

        #expect(auth.sendCount == 1)
        #expect(message.contains("gönderildi"))
    }

    @Test("A failure explains itself instead of vanishing")
    func failureIsExplained() async {
        // Silence would leave somebody tapping a button that appears to do
        // nothing, which is worse than the error.
        let auth = StubAuth()
        auth.sendError = .offline
        let subject = store(auth)

        let message = await subject.resendVerificationEmail()

        #expect(message == APIError.offline.localizedDescription)
    }

    @Test("An already verified address surfaces the backend's own words")
    func conflictIsSurfaced() async {
        let auth = StubAuth()
        auth.sendError = .server(
            ProblemDetail(
                title: "Conflict",
                status: 409,
                detail: "Bu e-posta adresi zaten doğrulanmış.",
                code: "conflict",
                requestID: nil
            )
        )
        let subject = store(auth)

        let message = await subject.resendVerificationEmail()

        #expect(message == "Bu e-posta adresi zaten doğrulanmış.")
    }

    @Test("A signed-out session refuses to refresh a profile it does not have")
    func refreshNeedsASession() async {
        let auth = StubAuth()
        let client = APIClient(
            configuration: APIConfiguration(baseURL: URL(string: "http://localhost")!),
            tokens: InMemoryTokenStore()
        )
        let subject = SessionStore(client: client, auth: auth)

        await subject.refreshProfile()

        #expect(subject.phase.user == nil)
    }
}


@Suite("Account deletion")
@MainActor
struct AccountDeletionTests {

    private func store(_ auth: StubAuth) -> SessionStore {
        let client = APIClient(
            configuration: APIConfiguration(baseURL: URL(string: "http://localhost")!),
            tokens: InMemoryTokenStore()
        )
        let session = SessionStore(client: client, auth: auth)
        session.signedIn(as: auth.user)
        return session
    }

    @Test("Deleting sends the password the person typed")
    func passwordIsSent() async {
        let auth = StubAuth()
        let subject = store(auth)

        let failure = await subject.deleteAccount(password: "hunter2")

        #expect(failure == nil)
        #expect(auth.deletedWithPassword == ["hunter2"])
    }

    @Test("A deleted account ends the session immediately")
    func sessionEndsOnSuccess() async {
        // The tokens now name an account that does not exist; waiting for the
        // next request to fail would leave the app showing a dead session.
        let auth = StubAuth()
        let subject = store(auth)

        _ = await subject.deleteAccount(password: "hunter2")

        #expect(subject.phase == .signedOut)
    }

    @Test("A refused deletion keeps the person signed in")
    func sessionSurvivesFailure() async {
        let auth = StubAuth()
        auth.deleteError = .unauthorised
        let subject = store(auth)

        let failure = await subject.deleteAccount(password: "wrong")

        #expect(failure != nil)
        #expect(subject.phase.user != nil)
    }

    @Test("A wrong password surfaces the backend's own words")
    func wrongPasswordIsExplained() async {
        let auth = StubAuth()
        auth.deleteError = .server(
            ProblemDetail(
                title: "Unauthorized",
                status: 401,
                detail: "Şifre doğrulanamadı. Hesap silinmedi.",
                code: "authentication_failed",
                requestID: nil
            )
        )
        let subject = store(auth)

        let failure = await subject.deleteAccount(password: "wrong")

        #expect(failure == "Şifre doğrulanamadı. Hesap silinmedi.")
    }
}
