import Foundation
import Testing

@testable import Truvix

// MARK: - Timestamp parsing

@Suite("Timestamp parsing")
struct TimestampParserTests {

    @Test("Parses the microsecond precision the backend emits")
    func parsesMicroseconds() throws {
        // Python writes six fractional digits; the parser must not choke on
        // them, or every response with a timestamp fails to decode.
        let date = try #require(TimestampParser.date(from: "2026-08-03T19:59:59.076508Z"))

        let components = Calendar(identifier: .gregorian).dateComponents(
            in: TimeZone(identifier: "UTC")!,
            from: date
        )
        #expect(components.year == 2026)
        #expect(components.month == 8)
        #expect(components.day == 3)
        #expect(components.hour == 19)
        #expect(components.minute == 59)
        #expect(components.second == 59)
    }

    @Test("Parses millisecond precision unchanged")
    func parsesMilliseconds() {
        #expect(TimestampParser.date(from: "2026-08-03T19:59:59.076Z") != nil)
    }

    @Test("Parses timestamps with no fractional part")
    func parsesWholeSeconds() {
        #expect(TimestampParser.date(from: "2026-08-03T19:59:59Z") != nil)
    }

    @Test("Rejects text that is not a timestamp")
    func rejectsGarbage() {
        #expect(TimestampParser.date(from: "yesterday") == nil)
    }

    @Test("A written timestamp reads back to the same instant")
    func roundTrips() throws {
        let original = Date(timeIntervalSince1970: 1_785_787_199)

        let restored = try #require(
            TimestampParser.date(from: TimestampParser.string(from: original))
        )

        #expect(abs(restored.timeIntervalSince(original)) < 0.001)
    }
}

// MARK: - Decoding

@Suite("Response decoding")
struct DecodingTests {

    @Test("Decodes the register response the backend actually sends")
    func decodesAuthenticatedResponse() throws {
        let json = """
        {
          "user": {
            "id": "019FC936-2E85-77AE-B3D1-9239C9BD486B",
            "email": "demo@truvix.app",
            "full_name": "Kerem Yilmaz",
            "phone_number": null,
            "subscription_tier": "free",
            "email_verified": false,
            "created_at": "2026-08-03T19:59:59.076508Z"
          },
          "tokens": {
            "access_token": "header.payload.signature",
            "refresh_token": "header.payload.signature",
            "token_type": "bearer",
            "expires_in": 1800
          }
        }
        """

        let response = try JSONDecoder.truvix.decode(
            AuthenticatedResponse.self,
            from: Data(json.utf8)
        )

        #expect(response.user.email == "demo@truvix.app")
        #expect(response.user.firstName == "Kerem")
        #expect(response.user.subscriptionTier == .free)
        #expect(response.user.isPremium == false)
        #expect(response.tokens.expiresIn == 1800)
    }

    @Test("Decodes a problem document")
    func decodesProblemDetail() throws {
        let json = """
        {
          "type": "https://docs.truvix.app/errors/authentication_failed",
          "title": "Authentication Failed",
          "status": 401,
          "detail": "Email address or password is incorrect.",
          "instance": "/api/v1/auth/login",
          "code": "authentication_failed",
          "requestId": "019fc931-5482-731b-a0ab-b0f5655980cf"
        }
        """

        let problem = try JSONDecoder.truvix.decode(ProblemDetail.self, from: Data(json.utf8))

        #expect(problem.status == 401)
        #expect(problem.code == "authentication_failed")
        #expect(problem.requestID != nil)
    }

    @Test("Encodes request bodies in the snake case the backend expects")
    func encodesSnakeCase() throws {
        let request = RegistrationRequest(
            email: "kerem@truvix.app",
            password: "cok-guvenli-parola",
            fullName: "Kerem Yilmaz",
            phoneNumber: "+905551112233"
        )

        let encoded = try JSONEncoder.truvix.encode(request)
        let text = try #require(String(data: encoded, encoding: .utf8))

        #expect(text.contains("\"full_name\""))
        #expect(text.contains("\"phone_number\""))
        #expect(!text.contains("\"fullName\""))
    }
}

// MARK: - Token lifetime

@Suite("Token lifetime")
struct TokenPairTests {

    private func pair(expiringIn seconds: TimeInterval) -> TokenPair {
        TokenPair(
            accessToken: "access",
            refreshToken: "refresh",
            accessTokenExpiry: Date.now.addingTimeInterval(seconds)
        )
    }

    @Test("A fresh token does not need refreshing")
    func freshTokenIsUsable() {
        #expect(pair(expiringIn: 1800).needsRefresh() == false)
    }

    @Test("A token inside the leeway window is refreshed early")
    func nearExpiryRefreshesEarly() {
        // Refreshing slightly early stops a request failing purely because it
        // was in flight as the token expired.
        #expect(pair(expiringIn: 30).needsRefresh() == true)
    }

    @Test("An expired token needs refreshing")
    func expiredTokenNeedsRefresh() {
        #expect(pair(expiringIn: -10).needsRefresh() == true)
    }

    @Test("A lifetime in seconds becomes an absolute expiry")
    func lifetimeResolvesToInstant() {
        // Storing a duration would silently restart the clock on every launch.
        let now = Date(timeIntervalSince1970: 1_000_000)
        let response = TokenPairResponse(
            accessToken: "a",
            refreshToken: "r",
            tokenType: "bearer",
            expiresIn: 1800
        )

        let stored = response.asTokenPair(now: now)

        #expect(stored.accessTokenExpiry == now.addingTimeInterval(1800))
    }
}

// MARK: - Errors

@Suite("API errors")
struct APIErrorTests {

    @Test("Every case explains itself to the reader")
    func casesCarryMessages() {
        let cases: [APIError] = [
            .offline,
            .timedOut,
            .unauthorised,
            .malformedResponse,
            .unknown("bir sorun oluştu"),
        ]

        for error in cases {
            #expect(error.errorDescription?.isEmpty == false)
        }
    }

    @Test("A server error surfaces the backend's own message")
    func serverErrorUsesProblemDetail() {
        let problem = ProblemDetail(
            title: "Conflict",
            status: 409,
            detail: "An account with this email address already exists.",
            code: "conflict",
            requestID: nil
        )

        #expect(APIError.server(problem).errorDescription == problem.detail)
    }

    @Test("Only transient failures are worth retrying")
    func retryabilityMatchesCause() {
        #expect(APIError.offline.isRetryable)
        #expect(APIError.timedOut.isRetryable)
        #expect(!APIError.unauthorised.isRetryable)

        let serverFault = ProblemDetail(
            title: "Internal Server Error", status: 500,
            detail: "…", code: "internal_error", requestID: nil
        )
        let clientFault = ProblemDetail(
            title: "Conflict", status: 409,
            detail: "…", code: "conflict", requestID: nil
        )
        #expect(APIError.server(serverFault).isRetryable)
        #expect(!APIError.server(clientFault).isRetryable)
    }
}

@Suite("Quota refusals")
struct QuotaErrorTests {

    private func serverError(code: String, status: Int) -> APIError {
        .server(
            ProblemDetail(
                title: "Quota Exceeded",
                status: status,
                detail: "Günlük analiz hakkını kullandın.",
                code: code,
                requestID: nil
            )
        )
    }

    @Test("A spent allowance is recognised")
    func exhaustedQuotaIsRecognised() {
        #expect(serverError(code: "quota_exceeded", status: 429).isQuotaExhausted)
    }

    @Test("A speed limit is not a spent allowance")
    func rateLimitIsNotQuota() {
        // Both are 429; treating them alike would tell somebody to upgrade
        // when they only needed to wait a moment.
        #expect(!serverError(code: "rate_limit_exceeded", status: 429).isQuotaExhausted)
    }

    @Test("Retrying a spent allowance is pointless")
    func exhaustedQuotaIsNotRetryable() {
        #expect(!serverError(code: "quota_exceeded", status: 429).isRetryable)
    }

    @Test("Transport failures are not quota failures")
    func transportFailuresAreNotQuota() {
        #expect(!APIError.offline.isQuotaExhausted)
        #expect(!APIError.unauthorised.isQuotaExhausted)
    }
}
