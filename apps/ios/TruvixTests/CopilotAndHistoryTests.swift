import Foundation
import Testing

@testable import Truvix

@Suite("Price history")
struct PriceHistoryTests {

    private func history(prices: [String]) throws -> PriceHistory {
        let points = prices.enumerated().map { index, price in
            """
            {"observed_on":"2026-07-\(String(format: "%02d", index + 1))","price":"\(price)"}
            """
        }.joined(separator: ",")

        let json = """
        {
          "vehicle_id": "019FC936-2E85-77AE-B3D1-9239C9BD486B",
          "currency": "TRY",
          "window_days": 30,
          "points": [\(points)],
          "trend": null
        }
        """
        return try JSONDecoder.truvix.decode(PriceHistory.self, from: Data(json.utf8))
    }

    @Test("The average is the mean of the observations")
    func averageIsTheMean() throws {
        let series = try history(prices: ["1000000", "1200000", "1400000"])

        #expect(series.averagePrice == Money("1200000"))
    }

    @Test("The extremes come from the series")
    func extremesAreFound() throws {
        let series = try history(prices: ["1200000", "1000000", "1400000"])

        #expect(series.lowestPrice == Money("1000000"))
        #expect(series.highestPrice == Money("1400000"))
    }

    @Test("A single observation is not enough to plot a line")
    func singlePointIsNotPlottable() throws {
        // One dot is not a trend, and drawing it as one would imply movement
        // the data does not show.
        #expect(try !history(prices: ["1000000"]).isPlottable)
    }

    @Test("Two observations can be plotted")
    func twoPointsArePlottable() throws {
        #expect(try history(prices: ["1000000", "990000"]).isPlottable)
    }

    @Test("An empty series has no average")
    func emptySeriesHasNoAverage() throws {
        let series = try history(prices: [])

        #expect(series.averagePrice == nil)
        #expect(!series.isPlottable)
    }

    @Test("Amounts convert to a plottable value without distortion")
    func plottableAmountIsFaithful() {
        // Charts need a Double axis; the conversion must not shift the value
        // enough to move a point visibly.
        #expect(Money("1250000.00").plottableAmount == 1_250_000)
        #expect(Money("-25000.50").plottableAmount == -25_000.5)
    }

    @Test("A plain calendar date decodes, unlike a timestamp")
    func calendarDayDecodes() throws {
        // The backend sends "2026-08-04" for chart points, which the timestamp
        // parser cannot read; getting this wrong means the chart never loads.
        let day = try JSONDecoder.truvix.decode(
            CalendarDay.self, from: Data("\"2026-08-04\"".utf8)
        )

        #expect(day.text == "2026-08-04")
    }

    @Test("A malformed day is rejected")
    func malformedDayIsRejected() {
        #expect(throws: (any Error).self) {
            try JSONDecoder.truvix.decode(CalendarDay.self, from: Data("\"dün\"".utf8))
        }
    }

    @Test("Days round trip through their text form")
    func calendarDayRoundTrips() throws {
        let original = try #require(CalendarDay(text: "2026-02-29"))

        let encoded = try JSONEncoder.truvix.encode(original)
        let restored = try JSONDecoder.truvix.decode(CalendarDay.self, from: encoded)

        #expect(restored == original)
    }

    @Test("Days order chronologically")
    func daysOrderChronologically() throws {
        let earlier = try #require(CalendarDay(text: "2026-08-01"))
        let later = try #require(CalendarDay(text: "2026-08-04"))

        #expect(earlier < later)
    }

    @Test("Every window offers a readable label")
    func windowsAreLabelled() {
        #expect(PriceWindow.week.title == "7 Gün")
        #expect(PriceWindow.month.rawValue == 30)
        #expect(PriceWindow.year.rawValue == 365)
    }
}

@Suite("Copilot models")
struct CopilotModelTests {

    @Test("A thread decodes from the shape the API sends")
    func threadDecodes() throws {
        let json = """
        {
          "conversation": {
            "id": "019FC936-2E85-77AE-B3D1-9239C9BD486B",
            "vehicle_id": "019FC936-2E85-77AE-B3D1-9239C9BD486C",
            "vehicle_display_name": "BMW 320i M Sport",
            "created_at": "2026-08-03T19:59:59.076508Z"
          },
          "messages": [
            {
              "id": "019FC936-2E85-77AE-B3D1-9239C9BD486D",
              "role": "user",
              "content": "Bu araç alınır mı?",
              "created_at": "2026-08-03T19:59:59.076508Z"
            },
            {
              "id": "019FC936-2E85-77AE-B3D1-9239C9BD486E",
              "role": "assistant",
              "content": "Bu araç mevcut verilere göre satın alınabilir.",
              "created_at": "2026-08-03T20:00:01.076508Z"
            }
          ]
        }
        """

        let thread = try JSONDecoder.truvix.decode(CopilotThread.self, from: Data(json.utf8))

        #expect(thread.conversation.vehicleDisplayName == "BMW 320i M Sport")
        #expect(thread.messages.count == 2)
        #expect(thread.messages.first?.role == .user)
        #expect(thread.messages.last?.role == .assistant)
    }

    @Test("An exchange decodes both halves")
    func exchangeDecodes() throws {
        let json = """
        {
          "user_message": {
            "id": "019FC936-2E85-77AE-B3D1-9239C9BD486D",
            "role": "user",
            "content": "Merhaba",
            "created_at": "2026-08-03T19:59:59.076508Z"
          },
          "assistant_message": {
            "id": "019FC936-2E85-77AE-B3D1-9239C9BD486E",
            "role": "assistant",
            "content": "Merhaba, nasıl yardımcı olabilirim?",
            "created_at": "2026-08-03T20:00:01.076508Z"
          }
        }
        """

        let exchange = try JSONDecoder.truvix.decode(MessageExchange.self, from: Data(json.utf8))

        #expect(exchange.userMessage.content == "Merhaba")
        #expect(exchange.assistantMessage.role == .assistant)
    }

    @Test("Every suggested question carries text and an icon")
    func promptsAreComplete() {
        for prompt in CopilotPrompt.allCases {
            #expect(!prompt.text.isEmpty)
            #expect(!prompt.symbolName.isEmpty)
        }
    }
}

@Suite("Copilot composer")
@MainActor
struct CopilotComposerTests {

    /// A stub that records what it was asked and answers predictably.
    private final class StubAPI: TruvixAPI, @unchecked Sendable {
        var isAvailable = true
        var failsToSend = false
        private(set) var sentMessages: [String] = []

        private let conversationID = UUID()
        private let vehicleID = UUID()

        func copilotStatus() async throws(APIError) -> CopilotStatus {
            CopilotStatus(available: isAvailable)
        }

        func openConversation(vehicleID: UUID) async throws(APIError) -> CopilotThread {
            CopilotThread(
                conversation: CopilotConversation(
                    id: conversationID,
                    vehicleId: vehicleID,
                    vehicleDisplayName: "BMW 320i",
                    createdAt: .now
                ),
                messages: []
            )
        }

        func sendCopilotMessage(
            _ content: String,
            conversationID: UUID
        ) async throws(APIError) -> MessageExchange {
            if failsToSend { throw .offline }
            sentMessages.append(content)
            return MessageExchange(
                userMessage: CopilotMessage(
                    id: UUID(), role: .user, content: content, createdAt: .now
                ),
                assistantMessage: CopilotMessage(
                    id: UUID(), role: .assistant, content: "Cevap", createdAt: .now
                )
            )
        }

        // The rest of the surface is unused by these tests.
        func conversation(id: UUID) async throws(APIError) -> CopilotThread {
            try await openConversation(vehicleID: vehicleID)
        }
        func dashboard() async throws(APIError) -> Dashboard { throw .offline }
        func garage(
            filter: GarageFilter, sort: VehicleSort, page: Int, pageSize: Int
        ) async throws(APIError) -> Page<VehicleSummary> { throw .offline }
        func garageStats() async throws(APIError) -> GarageStats { throw .offline }
        func vehicle(id: UUID) async throws(APIError) -> Vehicle { throw .offline }
        func setFavourite(
            _ isFavourite: Bool, vehicleID: UUID
        ) async throws(APIError) -> Vehicle { throw .offline }
        func setInComparison(
            _ isInComparison: Bool, vehicleID: UUID
        ) async throws(APIError) -> Vehicle { throw .offline }
        func deleteVehicle(id: UUID) async throws(APIError) { throw .offline }
        func createVehicle(
            _ request: VehicleCreateRequest
        ) async throws(APIError) -> Vehicle { throw .offline }
        func analyses(
            page: Int, pageSize: Int
        ) async throws(APIError) -> Page<AnalysisSummary> { throw .offline }
        func analysis(id: UUID) async throws(APIError) -> Analysis { throw .offline }
        func createAnalysis(vehicleID: UUID) async throws(APIError) -> Analysis { throw .offline }
        func uploadPhoto(
            _ data: Data, filename: String, contentType: String,
            kind: PhotoKind, analysisID: UUID
        ) async throws(APIError) -> AnalysisPhoto { throw .offline }
        func startAnalysis(id: UUID) async throws(APIError) -> Analysis { throw .offline }
        func notifications(
            category: NotificationCategory?, unreadOnly: Bool, page: Int, pageSize: Int
        ) async throws(APIError) -> Page<AppNotification> { throw .offline }
        func notificationSummary() async throws(APIError) -> NotificationSummary { throw .offline }
        func markNotificationRead(id: UUID) async throws(APIError) -> AppNotification {
            throw .offline
        }
        func markAllNotificationsRead(
            category: NotificationCategory?
        ) async throws(APIError) -> MarkAllReadResult { throw .offline }
        func notificationPreferences() async throws(APIError) -> NotificationPreferences {
            throw .offline
        }
        func updateNotificationPreferences(
            _ update: NotificationPreferencesUpdate
        ) async throws(APIError) -> NotificationPreferences { throw .offline }
        func priceHistory(
            vehicleID: UUID, windowDays: Int
        ) async throws(APIError) -> PriceHistory { throw .offline }
        func recordPrice(
            _ price: Money, vehicleID: UUID
        ) async throws(APIError) -> PriceObservation { throw .offline }
        func subscriptionState() async throws(APIError) -> SubscriptionState { throw .offline }
        func redeem(signedTransaction: String) async throws(APIError) -> SubscriptionState {
            throw .offline
        }
    }

    private func model(_ api: StubAPI) -> CopilotModel {
        CopilotModel(api: api, vehicleID: UUID())
    }

    @Test("An empty draft cannot be sent")
    func emptyDraftCannotSend() async {
        let subject = model(StubAPI())
        await subject.load()

        subject.draft = "   "

        #expect(!subject.canSend)
    }

    @Test("A message beyond the backend's cap cannot be sent")
    func overlongDraftCannotSend() async {
        let subject = model(StubAPI())
        await subject.load()

        subject.draft = String(repeating: "a", count: CopilotModel.maximumMessageLength + 1)

        #expect(!subject.canSend)
    }

    @Test("Nothing can be sent when the copilot is unavailable")
    func unavailableCopilotCannotSend() async {
        let api = StubAPI()
        api.isAvailable = false
        let subject = model(api)
        await subject.load()

        subject.draft = "Bu araç alınır mı?"

        #expect(!subject.isAvailable)
        #expect(!subject.canSend)
    }

    @Test("A sent message appends both halves of the exchange")
    func sendingAppendsTheExchange() async {
        let subject = model(StubAPI())
        await subject.load()
        subject.draft = "Bu araç alınır mı?"

        await subject.send()

        #expect(subject.state.value?.messages.count == 2)
        #expect(subject.draft.isEmpty)
    }

    @Test("A failed send keeps the question in the box")
    func failedSendPreservesTheDraft() async {
        // Losing what someone typed because the network blinked is the worst
        // possible response to a failure.
        let api = StubAPI()
        api.failsToSend = true
        let subject = model(api)
        await subject.load()
        subject.draft = "Kaybolmamalı"

        await subject.send()

        #expect(subject.draft == "Kaybolmamalı")
        #expect(subject.sendError != nil)
        #expect(subject.state.value?.messages.isEmpty == true)
    }

    @Test("A suggested question is sent verbatim")
    func promptIsSentVerbatim() async {
        let api = StubAPI()
        let subject = model(api)
        await subject.load()

        await subject.ask(.whyRisky)

        #expect(api.sentMessages == [CopilotPrompt.whyRisky.text])
    }

    @Test("Suggestions are offered only while the thread is empty")
    func promptsDisappearAfterTheFirstMessage() async {
        let subject = model(StubAPI())
        await subject.load()
        #expect(subject.showsPrompts)

        await subject.ask(.worthBuying)

        #expect(!subject.showsPrompts)
    }
}
