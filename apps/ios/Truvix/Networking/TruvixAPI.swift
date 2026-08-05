import Foundation

/// The application's calls, gathered behind one protocol.
///
/// Screens depend on this rather than on `APIClient`, so a view model can be
/// exercised against a stub without a network, and so every endpoint the app
/// uses is visible in one place instead of scattered through views.
protocol TruvixAPI: Sendable {
    func dashboard() async throws(APIError) -> Dashboard

    func garage(
        filter: GarageFilter,
        sort: VehicleSort,
        page: Int,
        pageSize: Int
    ) async throws(APIError) -> Page<VehicleSummary>

    func garageStats() async throws(APIError) -> GarageStats
    func vehicle(id: UUID) async throws(APIError) -> Vehicle
    func setFavourite(_ isFavourite: Bool, vehicleID: UUID) async throws(APIError) -> Vehicle
    func setInComparison(_ isInComparison: Bool, vehicleID: UUID) async throws(APIError) -> Vehicle
    func deleteVehicle(id: UUID) async throws(APIError)

    func createVehicle(_ request: VehicleCreateRequest) async throws(APIError) -> Vehicle

    func analyses(page: Int, pageSize: Int) async throws(APIError) -> Page<AnalysisSummary>
    func analysis(id: UUID) async throws(APIError) -> Analysis
    func createAnalysis(vehicleID: UUID) async throws(APIError) -> Analysis
    func uploadPhoto(
        _ data: Data,
        filename: String,
        contentType: String,
        kind: PhotoKind,
        analysisID: UUID
    ) async throws(APIError) -> AnalysisPhoto
    func startAnalysis(id: UUID) async throws(APIError) -> Analysis

    func notifications(
        category: NotificationCategory?,
        unreadOnly: Bool,
        page: Int,
        pageSize: Int
    ) async throws(APIError) -> Page<AppNotification>
    func notificationSummary() async throws(APIError) -> NotificationSummary
    func markNotificationRead(id: UUID) async throws(APIError) -> AppNotification
    func markAllNotificationsRead(
        category: NotificationCategory?
    ) async throws(APIError) -> MarkAllReadResult
    func notificationPreferences() async throws(APIError) -> NotificationPreferences
    func updateNotificationPreferences(
        _ update: NotificationPreferencesUpdate
    ) async throws(APIError) -> NotificationPreferences

    func priceHistory(vehicleID: UUID, windowDays: Int) async throws(APIError) -> PriceHistory
    func recordPrice(
        _ price: Money,
        vehicleID: UUID
    ) async throws(APIError) -> PriceObservation

    func copilotStatus() async throws(APIError) -> CopilotStatus
    func openConversation(vehicleID: UUID) async throws(APIError) -> CopilotThread
    func conversation(id: UUID) async throws(APIError) -> CopilotThread
    func sendCopilotMessage(
        _ content: String,
        conversationID: UUID
    ) async throws(APIError) -> MessageExchange

    func subscriptionState() async throws(APIError) -> SubscriptionState
    func redeem(signedTransaction: String) async throws(APIError) -> SubscriptionState
}

/// The live implementation, talking to the backend through `APIClient`.
struct LiveTruvixAPI: TruvixAPI {
    private let client: APIClient

    init(client: APIClient) {
        self.client = client
    }

    func dashboard() async throws(APIError) -> Dashboard {
        try await client.send(APIRequest(path: "dashboard"))
    }

    func garage(
        filter: GarageFilter,
        sort: VehicleSort,
        page: Int,
        pageSize: Int
    ) async throws(APIError) -> Page<VehicleSummary> {
        try await client.send(
            APIRequest(
                path: "vehicles",
                query: [
                    "filter": filter.rawValue,
                    "sort": sort.rawValue,
                    "page": String(page),
                    "page_size": String(pageSize),
                ]
            )
        )
    }

    func garageStats() async throws(APIError) -> GarageStats {
        try await client.send(APIRequest(path: "vehicles/stats"))
    }

    func vehicle(id: UUID) async throws(APIError) -> Vehicle {
        try await client.send(APIRequest(path: "vehicles/\(id.uuidString.lowercased())"))
    }

    func setFavourite(_ isFavourite: Bool, vehicleID: UUID) async throws(APIError) -> Vehicle {
        try await patchVehicle(id: vehicleID, body: VehicleFlagUpdate(isFavourite: isFavourite))
    }

    func setInComparison(
        _ isInComparison: Bool,
        vehicleID: UUID
    ) async throws(APIError) -> Vehicle {
        try await patchVehicle(
            id: vehicleID,
            body: VehicleFlagUpdate(isInComparison: isInComparison)
        )
    }

    func deleteVehicle(id: UUID) async throws(APIError) {
        try await client.send(
            APIRequest(method: .delete, path: "vehicles/\(id.uuidString.lowercased())")
        )
    }

    func analyses(page: Int, pageSize: Int) async throws(APIError) -> Page<AnalysisSummary> {
        try await client.send(
            APIRequest(
                path: "analyses",
                query: ["page": String(page), "page_size": String(pageSize)]
            )
        )
    }

    func analysis(id: UUID) async throws(APIError) -> Analysis {
        try await client.send(APIRequest(path: "analyses/\(id.uuidString.lowercased())"))
    }

    func createVehicle(_ request: VehicleCreateRequest) async throws(APIError) -> Vehicle {
        try await client.send(APIRequest(method: .post, path: "vehicles", body: request))
    }

    func createAnalysis(vehicleID: UUID) async throws(APIError) -> Analysis {
        // The endpoint takes a form field rather than JSON, because the same
        // router also accepts multipart uploads for the evidence step.
        var form = MultipartFormData()
        form.append(vehicleID.uuidString.lowercased(), name: "vehicle_id")
        return try await client.send(APIRequest.multipart(path: "analyses", form: form))
    }

    func uploadPhoto(
        _ data: Data,
        filename: String,
        contentType: String,
        kind: PhotoKind,
        analysisID: UUID
    ) async throws(APIError) -> AnalysisPhoto {
        var form = MultipartFormData()
        form.append(kind.rawValue, name: "kind")
        form.append(data, name: "file", filename: filename, contentType: contentType)
        return try await client.send(
            APIRequest.multipart(
                path: "analyses/\(analysisID.uuidString.lowercased())/photos",
                form: form
            )
        )
    }

    func startAnalysis(id: UUID) async throws(APIError) -> Analysis {
        try await client.send(
            APIRequest(method: .post, path: "analyses/\(id.uuidString.lowercased())/start")
        )
    }

    // MARK: - Notifications

    func notifications(
        category: NotificationCategory?,
        unreadOnly: Bool,
        page: Int,
        pageSize: Int
    ) async throws(APIError) -> Page<AppNotification> {
        var query = [
            "page": String(page),
            "page_size": String(pageSize),
        ]
        if let category {
            query["category"] = category.rawValue
        }
        if unreadOnly {
            query["unread_only"] = "true"
        }
        return try await client.send(APIRequest(path: "notifications", query: query))
    }

    func notificationSummary() async throws(APIError) -> NotificationSummary {
        try await client.send(APIRequest(path: "notifications/summary"))
    }

    func markNotificationRead(id: UUID) async throws(APIError) -> AppNotification {
        try await client.send(
            APIRequest(
                method: .post,
                path: "notifications/\(id.uuidString.lowercased())/read"
            )
        )
    }

    func markAllNotificationsRead(
        category: NotificationCategory?
    ) async throws(APIError) -> MarkAllReadResult {
        var query: [String: String] = [:]
        if let category {
            query["category"] = category.rawValue
        }
        return try await client.send(
            APIRequest(method: .post, path: "notifications/read-all", query: query)
        )
    }

    func notificationPreferences() async throws(APIError) -> NotificationPreferences {
        try await client.send(APIRequest(path: "notifications/preferences"))
    }

    func updateNotificationPreferences(
        _ update: NotificationPreferencesUpdate
    ) async throws(APIError) -> NotificationPreferences {
        try await client.send(
            APIRequest(method: .patch, path: "notifications/preferences", body: update)
        )
    }

    // MARK: - Price history

    func priceHistory(vehicleID: UUID, windowDays: Int) async throws(APIError) -> PriceHistory {
        try await client.send(
            APIRequest(
                path: "vehicles/\(vehicleID.uuidString.lowercased())/prices",
                query: ["window_days": String(windowDays)]
            )
        )
    }

    func recordPrice(
        _ price: Money,
        vehicleID: UUID
    ) async throws(APIError) -> PriceObservation {
        try await client.send(
            APIRequest(
                method: .post,
                path: "vehicles/\(vehicleID.uuidString.lowercased())/prices",
                body: PriceUpdateRequest(price: price)
            )
        )
    }

    // MARK: - Copilot

    func copilotStatus() async throws(APIError) -> CopilotStatus {
        try await client.send(APIRequest(path: "copilot/status"))
    }

    func openConversation(vehicleID: UUID) async throws(APIError) -> CopilotThread {
        try await client.send(
            APIRequest(
                method: .post,
                path: "copilot/conversations",
                body: ConversationOpenRequest(vehicleId: vehicleID)
            )
        )
    }

    func conversation(id: UUID) async throws(APIError) -> CopilotThread {
        try await client.send(
            APIRequest(path: "copilot/conversations/\(id.uuidString.lowercased())")
        )
    }

    func sendCopilotMessage(
        _ content: String,
        conversationID: UUID
    ) async throws(APIError) -> MessageExchange {
        try await client.send(
            APIRequest(
                method: .post,
                path: "copilot/conversations/\(conversationID.uuidString.lowercased())/messages",
                body: MessageSendRequest(content: content)
            )
        )
    }

    func subscriptionState() async throws(APIError) -> SubscriptionState {
        try await client.send(APIRequest(path: "subscriptions"))
    }

    func redeem(signedTransaction: String) async throws(APIError) -> SubscriptionState {
        try await client.send(
            APIRequest(
                method: .post,
                path: "subscriptions/redeem",
                body: RedeemRequest(signedTransaction: signedTransaction)
            )
        )
    }

    private func patchVehicle(
        id: UUID,
        body: VehicleFlagUpdate
    ) async throws(APIError) -> Vehicle {
        try await client.send(
            APIRequest(
                method: .patch,
                path: "vehicles/\(id.uuidString.lowercased())",
                body: body
            )
        )
    }
}

/// A partial vehicle update carrying only the flags the garage toggles.
///
/// Sending just the changed field means a toggle cannot clobber a concurrent
/// edit to the price or the notes.
private struct VehicleFlagUpdate: Encodable, Sendable {
    var isFavourite: Bool?
    var isInComparison: Bool?
}
