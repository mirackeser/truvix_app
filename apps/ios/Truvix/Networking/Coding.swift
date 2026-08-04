import Foundation

/// Parses the timestamps the backend emits.
///
/// Python writes microsecond precision (`2026-08-03T19:59:59.076508Z`), while
/// `ISO8601DateFormatter` only accepts milliseconds and fails outright on six
/// fractional digits. Rather than have every response fail to decode, the
/// fraction is normalised to three digits before parsing, and timestamps
/// without a fraction still parse through the second formatter.
enum TimestampParser {

    // Format styles are value types and therefore safe to share across tasks,
    // unlike ISO8601DateFormatter, which Swift 6 rejects as non-Sendable.
    private static let fractional = Date.ISO8601FormatStyle(includingFractionalSeconds: true)
    private static let plain = Date.ISO8601FormatStyle(includingFractionalSeconds: false)

    /// The number of fractional digits the format style accepts.
    private static let supportedFractionDigits = 3

    static func date(from text: String) -> Date? {
        if let date = try? fractional.parse(normalisingFraction(in: text)) {
            return date
        }
        return try? plain.parse(text)
    }

    static func string(from date: Date) -> String {
        date.formatted(fractional)
    }

    /// Trim or pad the fractional-seconds component to three digits.
    private static func normalisingFraction(in text: String) -> String {
        guard let dotIndex = text.firstIndex(of: ".") else { return text }

        let afterDot = text.index(after: dotIndex)
        guard let fractionEnd = text[afterDot...].firstIndex(where: { !$0.isNumber }) else {
            return text
        }

        let digits = text[afterDot..<fractionEnd]
        guard digits.count != supportedFractionDigits else { return text }

        let normalised = digits.count > supportedFractionDigits
            ? String(digits.prefix(supportedFractionDigits))
            : digits.padding(toLength: supportedFractionDigits, withPad: "0", startingAt: 0)

        return text[..<afterDot] + normalised + text[fractionEnd...]
    }
}

extension JSONDecoder {
    /// The decoder every API response is read with.
    ///
    /// The backend emits snake_case keys, so the conversion is configured once
    /// here; a per-model `CodingKeys` for every field would be the same rule
    /// written a hundred times over.
    static let truvix: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let text = try container.decode(String.self)
            guard let date = TimestampParser.date(from: text) else {
                throw DecodingError.dataCorruptedError(
                    in: container,
                    debugDescription: "Tarih okunamadı: \(text)"
                )
            }
            return date
        }
        return decoder
    }()
}

extension JSONEncoder {
    /// The encoder every API request body is written with.
    static let truvix: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .custom { date, encoder in
            var container = encoder.singleValueContainer()
            try container.encode(TimestampParser.string(from: date))
        }
        return encoder
    }()
}
