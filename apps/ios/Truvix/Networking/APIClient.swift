import Foundation
import OSLog

/// One HTTP request against the Truvix API.
struct APIRequest: Sendable {
    enum Method: String, Sendable {
        case get = "GET"
        case post = "POST"
        case patch = "PATCH"
        case put = "PUT"
        case delete = "DELETE"
    }

    var method: Method = .get
    var path: String
    var query: [String: String] = [:]
    var body: (any Encodable & Sendable)?
    /// Whether the request must carry the session's access token.
    var requiresAuthentication = true
}

/// Configuration the client needs to reach the backend.
struct APIConfiguration: Sendable {
    let baseURL: URL
    var timeout: TimeInterval = 30

    /// The configuration used by a build running against a local backend.
    ///
    /// The simulator shares the host's network stack, so `localhost` reaches a
    /// backend running on the development machine.
    static let development = APIConfiguration(
        baseURL: URL(string: "http://localhost:8000/api/v1")!
    )
}

/// Sends requests, attaches the session, and renews it when it expires.
///
/// The client owns token refresh rather than leaving it to callers, because
/// every caller would otherwise reimplement the same retry. A single in-flight
/// refresh is shared: ten screens loading at once must not each rotate the
/// refresh token, which the backend reads as token reuse and answers by
/// revoking every session on the account.
actor APIClient {
    private let configuration: APIConfiguration
    private let session: URLSession
    private let tokens: any TokenStoring
    private let logger = Logger(subsystem: "app.truvix.ios", category: "api")

    /// The refresh currently in progress, if any.
    private var refreshTask: Task<TokenPair, any Error>?

    /// Invoked when the session can no longer be renewed, so the app signs out.
    private var onSessionExpired: (@Sendable () -> Void)?

    init(
        configuration: APIConfiguration = .development,
        tokens: any TokenStoring = KeychainTokenStore(),
        session: URLSession? = nil
    ) {
        self.configuration = configuration
        self.tokens = tokens

        if let session {
            self.session = session
        } else {
            let sessionConfiguration = URLSessionConfiguration.default
            sessionConfiguration.timeoutIntervalForRequest = configuration.timeout
            // Responses are never served from cache: prices, scores and unread
            // counts are the whole point of the app and must be current.
            sessionConfiguration.requestCachePolicy = .reloadIgnoringLocalCacheData
            self.session = URLSession(configuration: sessionConfiguration)
        }
    }

    /// Register the callback invoked when the session ends irrecoverably.
    func setSessionExpiredHandler(_ handler: @escaping @Sendable () -> Void) {
        onSessionExpired = handler
    }

    // MARK: - Session

    var hasSession: Bool {
        tokens.load() != nil
    }

    func storeSession(_ pair: TokenPair) throws {
        try tokens.save(pair)
    }

    func clearSession() {
        tokens.clear()
        refreshTask?.cancel()
        refreshTask = nil
    }

    // MARK: - Sending

    /// Send a request and decode its JSON body.
    func send<Response: Decodable & Sendable>(
        _ request: APIRequest,
        as _: Response.Type = Response.self
    ) async throws(APIError) -> Response {
        let data = try await perform(request)
        do {
            return try JSONDecoder.truvix.decode(Response.self, from: data)
        } catch {
            logger.error("Decoding \(String(describing: Response.self)) failed: \(error)")
            throw .malformedResponse
        }
    }

    /// Send a request that returns no body.
    func send(_ request: APIRequest) async throws(APIError) {
        _ = try await perform(request)
    }

    // MARK: - Transport

    /// Perform the request, refreshing the session once if it has expired.
    private func perform(_ request: APIRequest) async throws(APIError) -> Data {
        if request.requiresAuthentication {
            _ = try await validAccessToken()
        }

        let (data, http) = try await execute(request)

        // A 401 here means the token was rejected despite looking unexpired —
        // for instance after the account signed out elsewhere. One refresh and
        // replay distinguishes a stale token from a genuinely ended session.
        if http.statusCode == 401, request.requiresAuthentication {
            _ = try await refreshSession()
            let (retryData, retryHTTP) = try await execute(request)
            try validate(retryHTTP, data: retryData)
            return retryData
        }

        try validate(http, data: data)
        return data
    }

    private func execute(_ request: APIRequest) async throws(APIError) -> (Data, HTTPURLResponse) {
        let urlRequest: URLRequest
        do {
            urlRequest = try buildURLRequest(request)
        } catch {
            throw .unknown("İstek hazırlanamadı: \(error.localizedDescription)")
        }

        do {
            let (data, response) = try await session.data(for: urlRequest)
            guard let http = response as? HTTPURLResponse else {
                throw APIError.malformedResponse
            }
            return (data, http)
        } catch let error as URLError {
            switch error.code {
            case .notConnectedToInternet, .networkConnectionLost, .dataNotAllowed:
                throw .offline
            case .timedOut:
                throw .timedOut
            default:
                throw .unknown(error.localizedDescription)
            }
        } catch let error as APIError {
            throw error
        } catch {
            throw .unknown(error.localizedDescription)
        }
    }

    private func buildURLRequest(_ request: APIRequest) throws -> URLRequest {
        var components = URLComponents(
            url: configuration.baseURL.appending(path: request.path),
            resolvingAgainstBaseURL: false
        )
        if !request.query.isEmpty {
            components?.queryItems = request.query
                .sorted { $0.key < $1.key }
                .map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        guard let url = components?.url else {
            throw APIError.unknown("İstek adresi oluşturulamadı.")
        }

        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = request.method.rawValue
        urlRequest.setValue("application/json", forHTTPHeaderField: "Accept")

        if let body = request.body {
            urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
            urlRequest.httpBody = try JSONEncoder.truvix.encode(body)
        }

        if request.requiresAuthentication, let pair = tokens.load() {
            urlRequest.setValue("Bearer \(pair.accessToken)", forHTTPHeaderField: "Authorization")
        }

        return urlRequest
    }

    private func validate(_ response: HTTPURLResponse, data: Data) throws(APIError) {
        guard !(200..<300).contains(response.statusCode) else { return }

        if response.statusCode == 401 {
            clearSession()
            onSessionExpired?()
            throw .unauthorised
        }

        if let problem = try? JSONDecoder.truvix.decode(ProblemDetail.self, from: data) {
            logger.error("API \(response.statusCode) \(problem.code): \(problem.detail)")
            throw .server(problem)
        }
        throw .unknown("Sunucu \(response.statusCode) yanıtı döndü.")
    }

    // MARK: - Token refresh

    private func validAccessToken() async throws(APIError) -> String {
        guard let pair = tokens.load() else {
            throw .unauthorised
        }
        guard pair.needsRefresh() else {
            return pair.accessToken
        }
        return try await refreshSession().accessToken
    }

    /// Refresh the session, joining any refresh already under way.
    private func refreshSession() async throws(APIError) -> TokenPair {
        if let existing = refreshTask {
            guard let pair = try? await existing.value else {
                throw .unauthorised
            }
            return pair
        }

        guard let current = tokens.load() else {
            throw .unauthorised
        }

        let task = Task<TokenPair, any Error> { [configuration, session, tokens] in
            var request = URLRequest(url: configuration.baseURL.appending(path: "auth/refresh"))
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            request.httpBody = try JSONEncoder.truvix.encode(
                RefreshRequestBody(refreshToken: current.refreshToken)
            )

            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                throw APIError.unauthorised
            }

            let envelope = try JSONDecoder.truvix.decode(AuthenticatedResponse.self, from: data)
            let pair = envelope.tokens.asTokenPair()
            try tokens.save(pair)
            return pair
        }

        refreshTask = task
        defer { refreshTask = nil }

        guard let pair = try? await task.value else {
            clearSession()
            onSessionExpired?()
            throw .unauthorised
        }
        return pair
    }
}

private struct RefreshRequestBody: Encodable, Sendable {
    let refreshToken: String
}
