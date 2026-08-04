import Foundation

/// The greeting line and the premium banner's state.
struct DashboardUser: Codable, Equatable, Sendable {
    let fullName: String
    let subscriptionTier: SubscriptionTier
    let isPremium: Bool

    /// The first name, as the greeting uses it.
    var firstName: String {
        fullName.split(separator: " ").first.map(String.init) ?? fullName
    }
}

/// Everything the home screen renders, in one payload.
///
/// Fetched as a single call so the sections agree with each other: split
/// across five requests, a vehicle could appear under "saved" and be missing
/// from "price drops" in the same view.
struct Dashboard: Codable, Equatable, Sendable {
    let user: DashboardUser
    let garage: GarageStats
    let unreadNotifications: Int
    let recentAnalyses: [AnalysisSummary]
    let priceDrops: [VehicleSummary]
    let savedVehicles: [Vehicle]
    let recommendations: [AnalysisSummary]

    /// Whether the account has nothing yet, so the screen can invite a first
    /// analysis instead of showing a column of empty sections.
    var isEmpty: Bool {
        garage.total == 0 && recentAnalyses.isEmpty
    }
}
