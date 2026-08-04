import Foundation

/// An amount of money, kept exact.
///
/// The backend sends amounts as decimal strings rather than JSON numbers,
/// because a binary float cannot hold 1250000.00 exactly and a price that
/// drifts by a kuruş between two screens undermines every other figure the app
/// shows. Decoding through this type preserves that exactness, and giving
/// money its own type makes it impossible to add a price to a percentage by
/// accident.
struct Money: Equatable, Hashable, Sendable, Comparable {
    let amount: Decimal

    init(_ amount: Decimal) {
        self.amount = amount
    }

    static func < (lhs: Money, rhs: Money) -> Bool {
        lhs.amount < rhs.amount
    }

    var isNegative: Bool { amount < 0 }

    var magnitude: Money { Money(abs(amount)) }

    /// The amount as a `Double`, for charting only.
    ///
    /// Charts need a floating-point axis, and losing precision below a kuruş
    /// is invisible at a chart's resolution. Every figure the reader actually
    /// reads still comes from the exact `Decimal`.
    var plottableAmount: Double {
        (amount as NSDecimalNumber).doubleValue
    }

    /// Render as the app displays money: "1.250.000 ₺".
    ///
    /// Kuruş are dropped: no vehicle is priced to the kuruş, and the extra
    /// digits only make the figure harder to read at a glance.
    func formatted(_ currency: Currency) -> String {
        let text = NumberFormatter.turkishInteger.string(from: amount as NSDecimalNumber)
            ?? "\(amount)"
        return "\(text) \(currency.symbol)"
    }

    /// Render with an explicit sign, as price-change labels do: "-25.000 ₺".
    func formattedSigned(_ currency: Currency) -> String {
        (isNegative ? "-" : "+") + magnitude.formatted(currency)
    }
}

extension Money: Codable {
    init(from decoder: any Decoder) throws {
        let container = try decoder.singleValueContainer()

        // Strings are what the backend sends. Numbers are accepted too, so a
        // hand-written fixture or a future endpoint does not silently fail.
        if let text = try? container.decode(String.self) {
            guard let value = Decimal(string: text, locale: Locale(identifier: "en_US_POSIX")) else {
                throw DecodingError.dataCorruptedError(
                    in: container,
                    debugDescription: "Tutar okunamadı: \(text)"
                )
            }
            amount = value
            return
        }

        amount = try container.decode(Decimal.self)
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.singleValueContainer()
        // Written back as a string so the value the backend receives is
        // exactly the one it sent.
        try container.encode("\(amount)")
    }
}

extension Money: ExpressibleByStringLiteral {
    /// Allows fixtures and previews to be written as `"1250000.00"`.
    init(stringLiteral value: StringLiteralType) {
        amount = Decimal(string: value, locale: Locale(identifier: "en_US_POSIX")) ?? 0
    }
}

/// A percentage, sent by the backend the same way and for the same reason.
struct Percentage: Equatable, Hashable, Sendable {
    let value: Decimal

    init(_ value: Decimal) {
        self.value = value
    }

    var isNegative: Bool { value < 0 }

    /// Render as the price chart's header does: "-1,96%".
    var formatted: String {
        let text = NumberFormatter.turkishDecimal.string(from: value as NSDecimalNumber)
            ?? "\(value)"
        return (isNegative ? "" : "+") + text + "%"
    }
}

extension Percentage: Codable {
    init(from decoder: any Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let text = try? container.decode(String.self) {
            guard let parsed = Decimal(string: text, locale: Locale(identifier: "en_US_POSIX")) else {
                throw DecodingError.dataCorruptedError(
                    in: container,
                    debugDescription: "Yüzde okunamadı: \(text)"
                )
            }
            value = parsed
            return
        }
        value = try container.decode(Decimal.self)
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode("\(value)")
    }
}

extension NumberFormatter {
    /// Whole numbers with Turkish grouping: 67000 becomes "67.000".
    static let turkishInteger: NumberFormatter = {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.locale = Locale(identifier: "tr_TR")
        formatter.maximumFractionDigits = 0
        return formatter
    }()

    /// Two decimal places with Turkish separators: "-1,96".
    static let turkishDecimal: NumberFormatter = {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.locale = Locale(identifier: "tr_TR")
        formatter.minimumFractionDigits = 2
        formatter.maximumFractionDigits = 2
        return formatter
    }()
}
