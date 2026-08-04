import Foundation
import Testing

@testable import Truvix

@Suite("Money")
struct MoneyTests {

    @Test("Decodes the decimal strings the backend sends")
    func decodesFromString() throws {
        // The API sends amounts as strings precisely so they stay exact; a
        // JSON number would arrive as a binary float and lose the value.
        let decoded = try JSONDecoder.truvix.decode(Money.self, from: Data("\"1250000.00\"".utf8))

        #expect(decoded.amount == Decimal(string: "1250000.00"))
    }

    @Test("Decodes a bare number too")
    func decodesFromNumber() throws {
        let decoded = try JSONDecoder.truvix.decode(Money.self, from: Data("1250000".utf8))

        #expect(decoded.amount == 1_250_000)
    }

    @Test("A large amount survives the round trip exactly")
    func roundTripsExactly() throws {
        let original = Money("1250000.00")

        let encoded = try JSONEncoder.truvix.encode(original)
        let restored = try JSONDecoder.truvix.decode(Money.self, from: encoded)

        #expect(restored == original)
    }

    @Test("Rejects text that is not a number")
    func rejectsGarbage() {
        #expect(throws: (any Error).self) {
            try JSONDecoder.truvix.decode(Money.self, from: Data("\"pahalı\"".utf8))
        }
    }

    @Test("Formats with Turkish grouping and the lira sign")
    func formatsForTurkishReaders() {
        // "1,250,000" reads as one-and-a-bit to a Turkish speaker.
        #expect(Money("1250000.00").formatted(.TRY) == "1.250.000 ₺")
        #expect(Money("25000").formatted(.TRY) == "25.000 ₺")
        #expect(Money("999").formatted(.TRY) == "999 ₺")
    }

    @Test("A signed amount always carries its sign")
    func formatsSignedAmounts() {
        #expect(Money("-25000").formattedSigned(.TRY) == "-25.000 ₺")
        #expect(Money("25000").formattedSigned(.TRY) == "+25.000 ₺")
    }

    @Test("Amounts order by value")
    func comparesByValue() {
        #expect(Money("900000") < Money("1250000"))
        #expect(Money("-1") < Money("0"))
    }
}

@Suite("Percentage")
struct PercentageTests {

    @Test("Decodes from the backend's string form")
    func decodesFromString() throws {
        let decoded = try JSONDecoder.truvix.decode(
            Percentage.self, from: Data("\"-1.96\"".utf8)
        )

        #expect(decoded.value == Decimal(string: "-1.96"))
    }

    @Test("Formats with a Turkish decimal comma")
    func formatsForTurkishReaders() {
        #expect(Percentage(Decimal(string: "-1.96")!).formatted == "-1,96%")
        #expect(Percentage(Decimal(string: "2.00")!).formatted == "+2,00%")
    }
}

@Suite("Vehicle presentation")
struct VehiclePresentationTests {

    @Test("The specification line matches the card in the design")
    func specificationSummaryMatchesDesign() throws {
        let vehicle = try VehicleFixture.bmw()

        #expect(vehicle.specificationSummary == "2021 • 67.000 km • Benzin")
    }

    @Test("The price is grouped for Turkish readers")
    func priceIsFormatted() throws {
        let vehicle = try VehicleFixture.bmw()

        #expect(vehicle.formattedPrice == "1.250.000 ₺")
    }

    @Test("Toggling favourite leaves every other field alone")
    func favouriteToggleIsSurgical() throws {
        let vehicle = try VehicleFixture.bmw()

        let updated = vehicle.settingFavourite(true)

        #expect(updated.isFavourite)
        #expect(updated.id == vehicle.id)
        #expect(updated.askingPrice == vehicle.askingPrice)
        #expect(updated.displayName == vehicle.displayName)
        #expect(updated.isInComparison == vehicle.isInComparison)
    }
}

@Suite("Price trend")
struct PriceTrendTests {

    private func trend(change: String?) throws -> PriceTrend {
        let json = """
        {
          "current_price": "1225000.00",
          "previous_price": "1250000.00",
          "absolute_change": \(change.map { "\"\($0)\"" } ?? "null"),
          "percentage_change": "-2.00",
          "window_days": 30,
          "observation_count": 2
        }
        """
        return try JSONDecoder.truvix.decode(PriceTrend.self, from: Data(json.utf8))
    }

    @Test("A fall is reported as a drop")
    func fallIsADrop() throws {
        let movement = try trend(change: "-25000.00")

        #expect(movement.hasDropped)
        #expect(movement.formattedChange(.TRY) == "-25.000 ₺")
    }

    @Test("A rise is not a drop")
    func riseIsNotADrop() throws {
        let movement = try trend(change: "25000.00")

        #expect(!movement.hasDropped)
        #expect(movement.formattedChange(.TRY) == "+25.000 ₺")
    }

    @Test("A single observation reports no movement at all")
    func singleObservationHasNoChange() throws {
        // The backend deliberately sends null rather than zero here: one
        // observation cannot describe a movement, and zero would read as
        // "the price held", which is a different claim.
        let movement = try trend(change: nil)

        #expect(!movement.hasDropped)
        #expect(movement.formattedChange(.TRY) == nil)
    }
}

@Suite("Garage counts")
struct GarageStatsTests {

    @Test("Each tab reads its own count")
    func countsMapToTabs() {
        let stats = GarageStats(
            total: 12, favourites: 5, inComparison: 3, priceDropped: 3, viewedToday: 4
        )

        #expect(stats.count(for: .all) == 12)
        #expect(stats.count(for: .favourites) == 5)
        #expect(stats.count(for: .comparison) == 3)
        #expect(stats.count(for: .priceDropped) == 3)
        #expect(stats.count(for: .viewedToday) == 4)
    }
}

// MARK: - Fixtures

enum VehicleFixture {
    /// The BMW card from the design, decoded from the shape the API sends.
    static func bmw() throws -> Vehicle {
        let json = """
        {
          "id": "019FC936-2E85-77AE-B3D1-9239C9BD486B",
          "make": "BMW",
          "model": "320i",
          "variant": "M Sport",
          "display_name": "BMW 320i M Sport",
          "model_year": 2021,
          "mileage_km": 67000,
          "fuel_type": "petrol",
          "transmission": "automatic",
          "body_type": "sedan",
          "colour": null,
          "plate": "34ABC123",
          "vin": null,
          "listing_source": "manual",
          "listing_url": null,
          "seller_type": null,
          "city": "Istanbul",
          "asking_price": "1250000.00",
          "currency": "TRY",
          "is_favourite": false,
          "is_in_comparison": false,
          "notes": null,
          "last_viewed_at": null,
          "created_at": "2026-08-03T19:59:59.076508Z",
          "updated_at": "2026-08-03T19:59:59.076508Z"
        }
        """
        return try JSONDecoder.truvix.decode(Vehicle.self, from: Data(json.utf8))
    }
}
