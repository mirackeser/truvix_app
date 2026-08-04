import Foundation

/// A calendar day with no time of day.
///
/// The price chart's x-axis is days, and the backend sends them as plain
/// `yyyy-MM-dd` strings rather than timestamps. Decoding those through the
/// timestamp parser fails outright, so they need their own type — which also
/// stops a day ever being compared against an instant by accident.
struct CalendarDay: Hashable, Sendable, Comparable {
    /// Midnight at the start of the day, in UTC.
    ///
    /// A fixed zone is used rather than the device's: the value represents a
    /// date the backend chose, and re-interpreting it locally would shift a
    /// chart point across a day boundary for anyone west of UTC.
    let date: Date

    private static let calendar: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar
    }()

    init(date: Date) {
        self.date = Self.calendar.startOfDay(for: date)
    }

    /// Parse a `yyyy-MM-dd` string.
    init?(text: String) {
        let parts = text.split(separator: "-")
        guard parts.count == 3,
              let year = Int(parts[0]),
              let month = Int(parts[1]),
              let day = Int(parts[2]),
              let parsed = Self.calendar.date(
                  from: DateComponents(year: year, month: month, day: day)
              ) else {
            return nil
        }
        date = parsed
    }

    /// Render back to `yyyy-MM-dd`.
    var text: String {
        let components = Self.calendar.dateComponents([.year, .month, .day], from: date)
        return String(
            format: "%04d-%02d-%02d",
            components.year ?? 0,
            components.month ?? 0,
            components.day ?? 0
        )
    }

    /// A short label for the chart's axis and the history list.
    var shortLabel: String {
        date.formatted(
            .dateTime.day().month(.abbreviated).locale(Locale(identifier: "tr_TR"))
        )
    }

    var longLabel: String {
        date.formatted(
            .dateTime.day().month(.abbreviated).year().locale(Locale(identifier: "tr_TR"))
        )
    }

    static func < (lhs: CalendarDay, rhs: CalendarDay) -> Bool {
        lhs.date < rhs.date
    }
}

extension CalendarDay: Codable {
    init(from decoder: any Decoder) throws {
        let container = try decoder.singleValueContainer()
        let text = try container.decode(String.self)
        guard let parsed = CalendarDay(text: text) else {
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Gün okunamadı: \(text)"
            )
        }
        self = parsed
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(text)
    }
}
