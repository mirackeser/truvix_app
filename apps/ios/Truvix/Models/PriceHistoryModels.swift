import Foundation

/// One point on the price chart.
struct PriceHistoryPoint: Codable, Identifiable, Equatable, Sendable {
    let observedOn: CalendarDay
    let price: Money

    /// The day is unique within a series: the backend collapses several
    /// observations on one day to the last of them.
    var id: CalendarDay { observedOn }
}

/// The chart series with its summary figures.
struct PriceHistory: Codable, Equatable, Sendable {
    let vehicleId: UUID
    let currency: Currency
    let windowDays: Int
    let points: [PriceHistoryPoint]
    let trend: PriceTrend?

    /// The average across the window, as the chart header shows it.
    var averagePrice: Money? {
        guard !points.isEmpty else { return nil }
        let total = points.reduce(Decimal.zero) { $0 + $1.price.amount }
        return Money(total / Decimal(points.count))
    }

    var lowestPrice: Money? { points.map(\.price).min() }
    var highestPrice: Money? { points.map(\.price).max() }

    /// Whether there is enough data to draw a line rather than a single dot.
    var isPlottable: Bool { points.count > 1 }
}

/// The windows the chart offers, matching the design's segmented control.
enum PriceWindow: Int, CaseIterable, Identifiable, Sendable {
    case week = 7
    case month = 30
    case quarter = 90
    case year = 365

    var id: Int { rawValue }

    var title: String {
        switch self {
        case .week: "7 Gün"
        case .month: "30 Gün"
        case .quarter: "90 Gün"
        case .year: "1 Yıl"
        }
    }
}

/// A recorded price observation, as the history list shows it.
struct PriceObservation: Codable, Identifiable, Equatable, Sendable {
    let price: Money
    let currency: Currency
    let observedAt: Date
    let source: String

    var id: Date { observedAt }
}

/// The payload for recording a newly seen price.
struct PriceUpdateRequest: Encodable, Sendable {
    let price: Money
    var observedAt: Date?
}
