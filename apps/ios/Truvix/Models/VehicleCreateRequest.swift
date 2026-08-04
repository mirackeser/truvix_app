import Foundation

/// The payload for saving a vehicle to the garage.
///
/// Optional fields are omitted rather than sent as null, so the request says
/// only what the user actually supplied.
struct VehicleCreateRequest: Encodable, Sendable {
    let make: String
    let model: String
    var variant: String?
    let modelYear: Int
    let mileageKm: Int
    let fuelType: FuelType
    let transmission: Transmission
    var bodyType: BodyType?
    var plate: String?
    var vin: String?
    var city: String?
    let askingPrice: Money
    var currency: Currency = .TRY
    var notes: String?
}

/// Validation that mirrors the backend's rules.
///
/// Checking here turns a round trip and a rejection into immediate guidance,
/// but the backend still validates: a client is never the authority on what is
/// acceptable, because a client can be replaced.
enum VehicleDraftValidator {
    /// The oldest model year worth accepting from a used listing.
    static let earliestModelYear = 1950
    /// Manufacturers sell next year's models late in the current year.
    static let modelYearLookahead = 1
    /// No road vehicle credibly exceeds this.
    static let maximumMileage = 3_000_000

    static var latestModelYear: Int {
        Calendar(identifier: .gregorian).component(.year, from: .now) + modelYearLookahead
    }

    static func modelYearIsValid(_ year: Int) -> Bool {
        (earliestModelYear...latestModelYear).contains(year)
    }

    static func mileageIsValid(_ kilometres: Int) -> Bool {
        (0...maximumMileage).contains(kilometres)
    }

    static func priceIsValid(_ price: Money) -> Bool {
        price.amount > 0
    }

    /// Turkish plates: two-digit province, one to three letters, two to five digits.
    static func normalisedPlate(_ text: String) -> String? {
        let candidate = text.uppercased().filter { !$0.isWhitespace }
        guard candidate.wholeMatch(of: /\d{2}[A-Z]{1,3}\d{2,5}/) != nil else { return nil }
        return candidate
    }

    /// ISO 3779 fixes the VIN at seventeen characters and excludes I, O and Q.
    static func normalisedVIN(_ text: String) -> String? {
        let candidate = text.uppercased().filter { !$0.isWhitespace }
        guard candidate.wholeMatch(of: /[A-HJ-NPR-Z0-9]{17}/) != nil else { return nil }
        return candidate
    }
}
