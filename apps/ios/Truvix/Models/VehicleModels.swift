import Foundation

// MARK: - Enumerations

enum FuelType: String, Codable, CaseIterable, Sendable {
    case petrol, diesel, lpg, hybrid, electric

    var displayName: String {
        switch self {
        case .petrol: "Benzin"
        case .diesel: "Dizel"
        case .lpg: "LPG"
        case .hybrid: "Hibrit"
        case .electric: "Elektrik"
        }
    }
}

enum Transmission: String, Codable, CaseIterable, Sendable {
    case manual, automatic
    case semiAutomatic = "semi_automatic"

    var displayName: String {
        switch self {
        case .manual: "Manuel"
        case .automatic: "Otomatik"
        case .semiAutomatic: "Yarı Otomatik"
        }
    }
}

enum BodyType: String, Codable, CaseIterable, Sendable {
    case sedan, hatchback, suv, coupe, mpv, pickup, convertible
    case stationWagon = "station_wagon"

    var displayName: String {
        switch self {
        case .sedan: "Sedan"
        case .hatchback: "Hatchback"
        case .suv: "SUV"
        case .coupe: "Coupe"
        case .stationWagon: "Station Wagon"
        case .mpv: "MPV"
        case .pickup: "Pickup"
        case .convertible: "Üstü Açık"
        }
    }
}

enum ListingSource: String, Codable, Sendable {
    case manual, sahibinden, arabam, letgo, other
}

enum SellerType: String, Codable, Sendable {
    case owner, dealer

    var displayName: String {
        switch self {
        case .owner: "Sahibinden"
        case .dealer: "Galeriden"
        }
    }
}

enum Currency: String, Codable, Sendable {
    case TRY, USD, EUR

    var symbol: String {
        switch self {
        case .TRY: "₺"
        case .USD: "$"
        case .EUR: "€"
        }
    }
}

/// Which slice of the garage a listing request wants, mirroring the tabs.
enum GarageFilter: String, CaseIterable, Identifiable, Sendable {
    case all
    case favourites
    case comparison
    case priceDropped = "price_dropped"
    case viewedToday = "viewed_today"

    var id: Self { self }

    var title: String {
        switch self {
        case .all: "Tümü"
        case .favourites: "Favoriler"
        case .comparison: "Karşılaştır"
        case .priceDropped: "Fiyatı Düştü"
        case .viewedToday: "Bugün Bakılanlar"
        }
    }
}

enum VehicleSort: String, CaseIterable, Identifiable, Sendable {
    case recentlyAdded = "recently_added"
    case recentlyViewed = "recently_viewed"
    case priceAscending = "price_asc"
    case priceDescending = "price_desc"

    var id: Self { self }

    var title: String {
        switch self {
        case .recentlyAdded: "Son Eklenen"
        case .recentlyViewed: "Son Bakılan"
        case .priceAscending: "Fiyat: Artan"
        case .priceDescending: "Fiyat: Azalan"
        }
    }
}

// MARK: - Vehicle

/// A vehicle saved to the garage.
struct Vehicle: Codable, Identifiable, Equatable, Sendable {
    let id: UUID
    let make: String
    let model: String
    let variant: String?
    let displayName: String
    let modelYear: Int
    let mileageKm: Int

    let fuelType: FuelType
    let transmission: Transmission
    let bodyType: BodyType?
    let colour: String?

    let plate: String?
    let vin: String?

    let listingSource: ListingSource
    let listingURL: String?
    let sellerType: SellerType?
    let city: String?

    let askingPrice: Money
    let currency: Currency

    let isFavourite: Bool
    let isInComparison: Bool
    let notes: String?
    let lastViewedAt: Date?
    let createdAt: Date
    let updatedAt: Date

    private enum CodingKeys: String, CodingKey {
        case id, make, model, variant, colour, plate, vin, city, notes, currency
        case displayName, modelYear, mileageKm, fuelType, transmission, bodyType
        case listingSource, sellerType, askingPrice
        case isFavourite, isInComparison, lastViewedAt, createdAt, updatedAt
        // The API writes "listing_url", which the snake-case strategy turns
        // into "listingUrl" rather than the "listingURL" Swift prefers.
        case listingURL = "listingUrl"
    }

    /// The subtitle every card shows: "2021 • 67.000 km • Benzin".
    var specificationSummary: String {
        let mileage = NumberFormatter.turkishInteger
            .string(from: NSNumber(value: mileageKm)) ?? "\(mileageKm)"
        return "\(modelYear) • \(mileage) km • \(fuelType.displayName)"
    }

    var formattedPrice: String {
        askingPrice.formatted(currency)
    }
}

// MARK: - Price movement

/// How a vehicle's price moved across a window.
struct PriceTrend: Codable, Equatable, Sendable {
    let currentPrice: Money
    let previousPrice: Money?
    let absoluteChange: Money?
    let percentageChange: Percentage?
    let windowDays: Int
    let observationCount: Int

    var hasDropped: Bool {
        absoluteChange?.isNegative == true
    }

    /// The signed change as the cards render it, for example "-25.000 ₺".
    func formattedChange(_ currency: Currency) -> String? {
        absoluteChange?.formattedSigned(currency)
    }
}

/// A garage card: the vehicle plus its price movement.
struct VehicleSummary: Codable, Identifiable, Equatable, Sendable {
    let vehicle: Vehicle
    let priceTrend: PriceTrend?

    var id: UUID { vehicle.id }
}

/// The counts behind the garage's tabs.
struct GarageStats: Codable, Equatable, Sendable {
    let total: Int
    let favourites: Int
    let inComparison: Int
    let priceDropped: Int
    let viewedToday: Int

    static let empty = GarageStats(
        total: 0, favourites: 0, inComparison: 0, priceDropped: 0, viewedToday: 0
    )

    func count(for filter: GarageFilter) -> Int {
        switch filter {
        case .all: total
        case .favourites: favourites
        case .comparison: inComparison
        case .priceDropped: priceDropped
        case .viewedToday: viewedToday
        }
    }
}

// MARK: - Pagination

/// One page of a listing endpoint.
struct Page<Item: Codable & Sendable>: Codable, Sendable {
    let items: [Item]
    let total: Int
    let page: Int
    let pageSize: Int
    let hasNext: Bool
}
