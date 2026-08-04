import Foundation

/// The tab the notification centre files an entry under.
enum NotificationCategory: String, Codable, CaseIterable, Identifiable, Sendable {
    case opportunity
    case risk
    case aiSuggestion = "ai_suggestion"
    case system

    var id: Self { self }

    var title: String {
        switch self {
        case .opportunity: "Fırsatlar"
        case .risk: "Riskler"
        case .aiSuggestion: "AI Önerileri"
        case .system: "Genel"
        }
    }

    var symbolName: String {
        switch self {
        case .opportunity: "chart.line.uptrend.xyaxis"
        case .risk: "exclamationmark.triangle.fill"
        case .aiSuggestion: "sparkles"
        case .system: "bell.fill"
        }
    }
}

/// One entry in the notification centre.
struct AppNotification: Codable, Identifiable, Equatable, Sendable {
    let id: UUID
    let category: NotificationCategory
    let eventType: String
    let title: String
    let body: String
    let vehicleId: UUID?
    let read: Bool
    let createdAt: Date
}

/// The counts behind the centre's tabs and the app badge.
struct NotificationSummary: Codable, Equatable, Sendable {
    let total: Int
    let unread: Int
    let opportunities: Int
    let risks: Int
    let aiSuggestions: Int

    static let empty = NotificationSummary(
        total: 0, unread: 0, opportunities: 0, risks: 0, aiSuggestions: 0
    )

    func count(for category: NotificationCategory?) -> Int {
        switch category {
        case .none: total
        case .opportunity: opportunities
        case .risk: risks
        case .aiSuggestion: aiSuggestions
        case .system: max(total - opportunities - risks - aiSuggestions, 0)
        }
    }
}

/// The account's notification switches.
struct NotificationPreferences: Codable, Equatable, Sendable {
    var priceChanges: Bool
    var riskAlerts: Bool
    var aiSuggestions: Bool
    var marketUpdates: Bool

    static let allEnabled = NotificationPreferences(
        priceChanges: true, riskAlerts: true, aiSuggestions: true, marketUpdates: true
    )
}

/// A partial preferences update, so a toggle sends only what changed.
struct NotificationPreferencesUpdate: Encodable, Sendable {
    var priceChanges: Bool?
    var riskAlerts: Bool?
    var aiSuggestions: Bool?
    var marketUpdates: Bool?
}

/// The result of a bulk mark-as-read.
struct MarkAllReadResult: Codable, Sendable {
    let marked: Int
}
