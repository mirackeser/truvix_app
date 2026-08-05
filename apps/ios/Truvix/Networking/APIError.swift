import Foundation

/// The RFC 9457 problem document the backend returns for every failure.
struct ProblemDetail: Decodable, Sendable {
    let title: String
    let status: Int
    let detail: String
    let code: String
    let requestID: String?

    private enum CodingKeys: String, CodingKey {
        case title, status, detail, code
        case requestID = "requestId"
    }
}

/// Anything that can go wrong between tapping a button and having data.
///
/// The cases are distinguished by what the person should do about them, not by
/// where they arose: a decoding failure and a 500 are both "our fault, retry",
/// while `unauthorised` is the only one that means "sign in again".
enum APIError: LocalizedError, Sendable {
    /// The device has no usable connection.
    case offline
    /// The request took too long.
    case timedOut
    /// The server rejected the request with a problem document.
    case server(ProblemDetail)
    /// The credentials or session are no longer valid.
    case unauthorised
    /// The response could not be understood.
    case malformedResponse
    /// Anything the other cases do not cover.
    case unknown(String)

    var errorDescription: String? {
        switch self {
        case .offline:
            "İnternet bağlantısı yok. Bağlantınızı kontrol edip tekrar deneyin."
        case .timedOut:
            "Sunucu zamanında yanıt vermedi. Lütfen tekrar deneyin."
        case let .server(problem):
            problem.detail
        case .unauthorised:
            "Oturumunuzun süresi doldu. Lütfen tekrar giriş yapın."
        case .malformedResponse:
            "Sunucudan beklenmeyen bir yanıt geldi."
        case let .unknown(message):
            message
        }
    }

    /// Narrow an arbitrary error back to this type.
    ///
    /// Needed where typed throws cannot be preserved — `async let` and calls
    /// through an existential both erase the thrown type to `any Error` — so
    /// that screens still receive a case they can render rather than an opaque
    /// error with an English system message.
    static func wrapping(_ error: any Error) -> APIError {
        error as? APIError ?? .unknown(error.localizedDescription)
    }

    /// Whether the account has spent an allowance rather than hit a speed limit.
    ///
    /// Both arrive as 429, but they mean different things to the reader: one
    /// says "wait a moment", the other says "that is all you get today" and is
    /// the moment to mention the plan.
    var isQuotaExhausted: Bool {
        guard case let .server(problem) = self else { return false }
        return problem.code == "quota_exceeded"
    }

    /// Whether trying the same request again could plausibly succeed.
    var isRetryable: Bool {
        switch self {
        case .offline, .timedOut, .malformedResponse:
            true
        case let .server(problem):
            // A spent allowance is not retryable in any useful sense: the same
            // request will be refused until the day turns over.
            problem.status >= 500
        case .unauthorised, .unknown:
            false
        }
    }
}
