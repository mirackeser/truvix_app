import Foundation

@testable import Truvix

/// A backend that refuses everything, meant to be subclassed.
///
/// `TruvixAPI` is a wide protocol, and a test about one corner of it should not
/// have to spell out the other twenty-five methods. Subclasses override only
/// what they exercise; anything else reports the app as offline, which is a
/// failure the screens already know how to render.
class SubscriptionAPIStub: TruvixAPI, @unchecked Sendable {
    func subscriptionState() async throws(APIError) -> SubscriptionState { throw .offline }
    func redeem(signedTransaction: String) async throws(APIError) -> SubscriptionState {
        throw .offline
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
    func markNotificationRead(id: UUID) async throws(APIError) -> AppNotification { throw .offline }
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
    func copilotStatus() async throws(APIError) -> CopilotStatus { throw .offline }
    func openConversation(vehicleID: UUID) async throws(APIError) -> CopilotThread {
        throw .offline
    }
    func conversation(id: UUID) async throws(APIError) -> CopilotThread { throw .offline }
    func sendCopilotMessage(
        _ content: String, conversationID: UUID
    ) async throws(APIError) -> MessageExchange { throw .offline }
}
