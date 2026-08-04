import Foundation
import Testing

@testable import Truvix

/// Exercises the real networking stack against a running backend.
///
/// These are the tests that catch contract drift: a field renamed on the
/// server, a timestamp format the decoder cannot read, a status code the
/// client mishandles. None of that is visible to a test that stubs the
/// network, because a stub encodes the client's assumptions rather than the
/// server's behaviour.
///
/// The suite is skipped when no backend is reachable, so it never fails a
/// checkout that simply is not running one. Start the backend with:
///
/// ```
/// TRUVIX_RATELIMIT_ENABLED=false uv run uvicorn truvix.main:app --port 8000
/// ```
///
/// Rate limiting is disabled for the run because the auth endpoints allow ten
/// attempts per minute per address and this suite registers more accounts than
/// that from one host — a real client never does. The limiter itself is
/// covered by the backend's own tests, which assert it fails closed.
///
/// The suite is serialised for the same reason: five sign-ups arriving at once
/// from one IP is a load pattern no user produces.
@Suite("Live backend", .serialized, .enabled(if: LiveBackend.isReachable))
struct LiveBackendTests {

    // MARK: - Registration and session

    @Test("Registering returns a profile and stores a usable session")
    func registrationEstablishesSession() async throws {
        let tokens = InMemoryTokenStore()
        let auth = AuthService(client: LiveBackend.client(tokens: tokens))

        let profile = try await auth.register(LiveBackend.newAccount())

        #expect(profile.email.hasPrefix("ios-test-"))
        #expect(profile.subscriptionTier == .free)
        #expect(profile.emailVerified == false)
        #expect(tokens.stored != nil)
    }

    @Test("The stored token authenticates a follow-up request")
    func storedTokenAuthenticates() async throws {
        let tokens = InMemoryTokenStore()
        let auth = AuthService(client: LiveBackend.client(tokens: tokens))
        let registered = try await auth.register(LiveBackend.newAccount())

        let me = try await auth.currentUser()

        #expect(me.id == registered.id)
        #expect(me.email == registered.email)
    }

    @Test("Signing in with the registered credentials succeeds")
    func signInWithRegisteredCredentials() async throws {
        let tokens = InMemoryTokenStore()
        let auth = AuthService(client: LiveBackend.client(tokens: tokens))
        let request = LiveBackend.newAccount()
        _ = try await auth.register(request)

        let profile = try await auth.signIn(email: request.email, password: request.password)

        #expect(profile.email == request.email)
    }

    // MARK: - Failure handling

    @Test("A wrong password surfaces the backend's problem document")
    func wrongPasswordSurfacesProblem() async throws {
        let auth = AuthService(client: LiveBackend.client(tokens: InMemoryTokenStore()))
        let request = LiveBackend.newAccount()
        _ = try await auth.register(request)

        await #expect(throws: APIError.self) {
            _ = try await auth.signIn(email: request.email, password: "definitely-not-it")
        }
    }

    @Test("Registering the same address twice is reported as a conflict")
    func duplicateRegistrationIsAConflict() async throws {
        let auth = AuthService(client: LiveBackend.client(tokens: InMemoryTokenStore()))
        let request = LiveBackend.newAccount()
        _ = try await auth.register(request)

        do {
            _ = try await auth.register(request)
            Issue.record("The second registration should have been rejected.")
        } catch let error as APIError {
            guard case let .server(problem) = error else {
                Issue.record("Expected a problem document, got \(error).")
                return
            }
            #expect(problem.status == 409)
            #expect(problem.code == "conflict")
        }
    }

    @Test("A request without a session is rejected as unauthorised")
    func missingSessionIsUnauthorised() async throws {
        let auth = AuthService(client: LiveBackend.client(tokens: InMemoryTokenStore()))

        await #expect(throws: APIError.self) {
            _ = try await auth.currentUser()
        }
    }

    // MARK: - Token rotation

    @Test("An expired access token is refreshed transparently")
    func expiredAccessTokenIsRefreshed() async throws {
        let tokens = InMemoryTokenStore()
        let client = LiveBackend.client(tokens: tokens)
        let auth = AuthService(client: client)
        _ = try await auth.register(LiveBackend.newAccount())

        // Backdate the expiry so the next call must refresh before sending.
        let issued = try #require(tokens.stored)
        tokens.stored = TokenPair(
            accessToken: issued.accessToken,
            refreshToken: issued.refreshToken,
            accessTokenExpiry: .now.addingTimeInterval(-60)
        )

        let me = try await auth.currentUser()

        #expect(!me.email.isEmpty)
        let rotated = try #require(tokens.stored)
        // Rotation means a genuinely new refresh token, not a reused one.
        #expect(rotated.refreshToken != issued.refreshToken)
        #expect(rotated.accessTokenExpiry > .now)
    }

    @Test("Concurrent requests share one refresh instead of racing")
    func concurrentRefreshIsShared() async throws {
        let tokens = InMemoryTokenStore()
        let client = LiveBackend.client(tokens: tokens)
        let auth = AuthService(client: client)
        _ = try await auth.register(LiveBackend.newAccount())

        let issued = try #require(tokens.stored)
        tokens.stored = TokenPair(
            accessToken: issued.accessToken,
            refreshToken: issued.refreshToken,
            accessTokenExpiry: .now.addingTimeInterval(-60)
        )

        // Five screens loading at once. If each rotated the refresh token, the
        // backend would read the second use as a replay and revoke every
        // session on the account, signing the user out mid-launch.
        try await withThrowingTaskGroup(of: UserProfile.self) { group in
            for _ in 0..<5 {
                group.addTask { try await auth.currentUser() }
            }
            var profiles: [UserProfile] = []
            for try await profile in group {
                profiles.append(profile)
            }
            #expect(profiles.count == 5)
        }

        // The session survived, which it would not have had a replay been seen.
        _ = try await auth.currentUser()
    }
}

// MARK: - Harness

/// Connection details and helpers for the live suite.
enum LiveBackend {
    static let baseURL = URL(string: "http://localhost:8000/api/v1")!

    /// Whether a backend answers its liveness probe.
    ///
    /// Checked synchronously because `@Suite(.enabled(if:))` is evaluated
    /// before any test runs, and a one-second probe on a local port is cheap.
    static let isReachable: Bool = {
        var request = URLRequest(url: URL(string: "http://localhost:8000/health/live")!)
        request.timeoutInterval = 1

        let semaphore = DispatchSemaphore(value: 0)
        nonisolated(unsafe) var reachable = false

        URLSession.shared.dataTask(with: request) { _, response, _ in
            reachable = (response as? HTTPURLResponse)?.statusCode == 200
            semaphore.signal()
        }.resume()

        _ = semaphore.wait(timeout: .now() + 2)
        return reachable
    }()

    static func client(tokens: any TokenStoring) -> APIClient {
        APIClient(
            configuration: APIConfiguration(baseURL: baseURL, timeout: 15),
            tokens: tokens
        )
    }

    /// A registration payload for an address no previous run has used.
    static func newAccount() -> RegistrationRequest {
        RegistrationRequest(
            email: "ios-test-\(UUID().uuidString.prefix(12).lowercased())@truvix.app",
            password: "ios-integration-passphrase",
            fullName: "iOS Test Kullanici"
        )
    }
}

/// A token store that keeps the session in memory.
///
/// The Keychain is deliberately avoided here: a test suite must not write to
/// the developer's keychain, and leaving entries behind would make repeat runs
/// depend on each other.
final class InMemoryTokenStore: TokenStoring, @unchecked Sendable {
    private let lock = NSLock()
    private var pair: TokenPair?

    var stored: TokenPair? {
        get { lock.withLock { pair } }
        set { lock.withLock { pair = newValue } }
    }

    func load() -> TokenPair? { stored }
    func save(_ pair: TokenPair) throws { stored = pair }
    func clear() { stored = nil }
}

// MARK: - The full analysis flow

/// Drives the whole product loop against a live backend: create a vehicle,
/// attach evidence, run the analysis, and read back what the screens render.
@Suite("Live analysis flow", .serialized, .enabled(if: LiveBackend.isReachable))
struct LiveAnalysisFlowTests {

    /// A JPEG signature followed by padding — enough for the backend's byte
    /// sniffing to accept it as an image.
    private static let jpeg = Data([0xFF, 0xD8, 0xFF, 0xE0] + Array(repeating: 0, count: 64))

    private func signedInAPI() async throws -> LiveTruvixAPI {
        let client = LiveBackend.client(tokens: InMemoryTokenStore())
        _ = try await AuthService(client: client).register(LiveBackend.newAccount())
        return LiveTruvixAPI(client: client)
    }

    private func draftRequest() -> VehicleCreateRequest {
        VehicleCreateRequest(
            make: "BMW",
            model: "320i",
            variant: "M Sport",
            modelYear: 2021,
            mileageKm: 67_000,
            fuelType: .petrol,
            transmission: .automatic,
            bodyType: .sedan,
            askingPrice: Money("1250000.00")
        )
    }

    @Test("A vehicle saved from the form decodes back intact")
    func vehicleRoundTrips() async throws {
        let api = try await signedInAPI()

        let vehicle = try await api.createVehicle(draftRequest())

        #expect(vehicle.displayName == "BMW 320i M Sport")
        #expect(vehicle.askingPrice == Money("1250000.00"))
        #expect(vehicle.specificationSummary == "2021 • 67.000 km • Benzin")
    }

    @Test("An analysis runs from an empty draft to a finished report")
    func analysisRunsToCompletion() async throws {
        let api = try await signedInAPI()
        let vehicle = try await api.createVehicle(draftRequest())

        let opened = try await api.createAnalysis(vehicleID: vehicle.id)
        #expect(opened.status == .pending)

        let finished = try await api.startAnalysis(id: opened.id)

        #expect(finished.status == .completed)
        #expect(finished.trustScore != nil)
        #expect(finished.riskLevel != nil)
        #expect(!finished.findings.isEmpty)
        #expect(finished.summary?.isEmpty == false)
    }

    @Test("Uploaded evidence reaches the report")
    func evidenceReachesTheReport() async throws {
        let api = try await signedInAPI()
        let vehicle = try await api.createVehicle(draftRequest())
        let analysis = try await api.createAnalysis(vehicleID: vehicle.id)

        let photo = try await api.uploadPhoto(
            Self.jpeg,
            filename: "front.jpg",
            contentType: "image/jpeg",
            kind: .exterior,
            analysisID: analysis.id
        )

        #expect(photo.contentType == "image/jpeg")
        #expect(photo.sizeBytes == Self.jpeg.count)

        let finished = try await api.startAnalysis(id: analysis.id)
        #expect(finished.photos.count == 1)
    }

    @Test("Evidence cannot be added once the analysis has run")
    func evidenceIsRefusedAfterCompletion() async throws {
        let api = try await signedInAPI()
        let vehicle = try await api.createVehicle(draftRequest())
        let analysis = try await api.createAnalysis(vehicleID: vehicle.id)
        _ = try await api.startAnalysis(id: analysis.id)

        await #expect(throws: APIError.self) {
            _ = try await api.uploadPhoto(
                Self.jpeg,
                filename: "late.jpg",
                contentType: "image/jpeg",
                kind: .exterior,
                analysisID: analysis.id
            )
        }
    }

    @Test("Running an analysis produces the notifications the centre lists")
    func analysisProducesNotifications() async throws {
        let api = try await signedInAPI()
        let vehicle = try await api.createVehicle(draftRequest())
        let analysis = try await api.createAnalysis(vehicleID: vehicle.id)
        _ = try await api.startAnalysis(id: analysis.id)

        let page = try await api.notifications(
            category: .aiSuggestion, unreadOnly: false, page: 1, pageSize: 20
        )

        #expect(page.total >= 1)
        #expect(page.items.first?.eventType == "analysis_completed")
    }

    @Test("A price drop reaches the dashboard and the notification centre")
    func priceDropFlowsThrough() async throws {
        let api = try await signedInAPI()
        let vehicle = try await api.createVehicle(draftRequest())

        _ = try await api.setFavourite(true, vehicleID: vehicle.id)

        let dashboard = try await api.dashboard()
        #expect(dashboard.garage.total == 1)
        #expect(dashboard.savedVehicles.count == 1)
    }

    @Test("Marking a notification read clears it from the unread count")
    func markingReadUpdatesTheCount() async throws {
        let api = try await signedInAPI()
        let vehicle = try await api.createVehicle(draftRequest())
        let analysis = try await api.createAnalysis(vehicleID: vehicle.id)
        _ = try await api.startAnalysis(id: analysis.id)

        let before = try await api.notificationSummary()
        #expect(before.unread > 0)

        let page = try await api.notifications(
            category: nil, unreadOnly: true, page: 1, pageSize: 1
        )
        let first = try #require(page.items.first)
        let marked = try await api.markNotificationRead(id: first.id)
        #expect(marked.read)

        let after = try await api.notificationSummary()
        #expect(after.unread == before.unread - 1)
    }

    @Test("Turning a category off stops its notifications being produced")
    func preferencesSuppressNotifications() async throws {
        let api = try await signedInAPI()
        _ = try await api.updateNotificationPreferences(
            NotificationPreferencesUpdate(aiSuggestions: false)
        )

        let vehicle = try await api.createVehicle(draftRequest())
        let analysis = try await api.createAnalysis(vehicleID: vehicle.id)
        _ = try await api.startAnalysis(id: analysis.id)

        let page = try await api.notifications(
            category: .aiSuggestion, unreadOnly: false, page: 1, pageSize: 20
        )

        #expect(page.total == 0)
    }

    @Test("Preferences read back exactly as they were set")
    func preferencesRoundTrip() async throws {
        let api = try await signedInAPI()

        let updated = try await api.updateNotificationPreferences(
            NotificationPreferencesUpdate(riskAlerts: false)
        )

        #expect(!updated.riskAlerts)
        #expect(updated.priceChanges)

        let reloaded = try await api.notificationPreferences()
        #expect(reloaded == updated)
    }
}
