import Foundation
import Testing

@testable import Truvix

@Suite("Vehicle draft validation")
@MainActor
struct VehicleDraftTests {

    private func completeDraft() -> VehicleDraft {
        let draft = VehicleDraft()
        draft.make = "BMW"
        draft.model = "320i"
        draft.modelYear = "2021"
        draft.mileageKm = "67000"
        draft.price = "1250000"
        return draft
    }

    @Test("A complete draft becomes a request")
    func completeDraftBuildsRequest() throws {
        let request = try #require(completeDraft().makeRequest())

        #expect(request.make == "BMW")
        #expect(request.modelYear == 2021)
        #expect(request.mileageKm == 67_000)
        #expect(request.askingPrice == Money("1250000"))
    }

    @Test("An incomplete draft builds nothing")
    func incompleteDraftBuildsNothing() {
        let draft = VehicleDraft()
        draft.make = "BMW"

        #expect(!draft.isComplete)
        #expect(draft.makeRequest() == nil)
    }

    @Test("Whitespace around names is trimmed")
    func namesAreTrimmed() throws {
        let draft = completeDraft()
        draft.make = "  BMW  "
        draft.model = " 320i "

        let request = try #require(draft.makeRequest())

        #expect(request.make == "BMW")
        #expect(request.model == "320i")
    }

    @Test("Blank optional fields are omitted rather than sent empty")
    func blankOptionalsAreOmitted() throws {
        let draft = completeDraft()
        draft.variant = "   "
        draft.city = ""

        let request = try #require(draft.makeRequest())

        #expect(request.variant == nil)
        #expect(request.city == nil)
    }

    @Test("A year beyond next year is refused")
    func futureYearIsRefused() {
        let draft = completeDraft()
        draft.modelYear = "3000"

        #expect(draft.parsedYear == nil)
        #expect(!draft.isComplete)
    }

    @Test("A year before motoring is refused")
    func ancientYearIsRefused() {
        let draft = completeDraft()
        draft.modelYear = "1800"

        #expect(draft.parsedYear == nil)
    }

    @Test("An implausible mileage is refused")
    func implausibleMileageIsRefused() {
        let draft = completeDraft()
        draft.mileageKm = "9000000"

        #expect(draft.parsedMileage == nil)
    }

    @Test("A zero price is refused")
    func zeroPriceIsRefused() {
        let draft = completeDraft()
        draft.price = "0"

        #expect(draft.parsedPrice == nil)
    }

    @Test("Grouping separators typed into the price are ignored")
    func priceIgnoresSeparators() {
        let draft = completeDraft()
        draft.price = "1.250.000"

        // The digits are what matters; a reader typing the separators they see
        // on screen should not be told their price is invalid.
        #expect(draft.parsedPrice != nil)
    }
}

@Suite("Identifier normalisation")
struct IdentifierNormalisationTests {

    @Test(
        "Turkish plates normalise to their canonical form",
        arguments: [
            ("34 ABC 123", "34ABC123"),
            ("34abc123", "34ABC123"),
            ("06 XY 45", "06XY45"),
        ]
    )
    func platesNormalise(input: String, expected: String) {
        #expect(VehicleDraftValidator.normalisedPlate(input) == expected)
    }

    @Test("Text that is not a plate is refused", arguments: ["ABC", "1234", "34-ABC-123"])
    func nonPlatesAreRefused(input: String) {
        #expect(VehicleDraftValidator.normalisedPlate(input) == nil)
    }

    @Test("A valid VIN is uppercased")
    func vinIsUppercased() {
        #expect(
            VehicleDraftValidator.normalisedVIN("wvwzzz1jzxw000001") == "WVWZZZ1JZXW000001"
        )
    }

    @Test("A VIN of the wrong length is refused")
    func shortVINIsRefused() {
        #expect(VehicleDraftValidator.normalisedVIN("WVWZZZ1JZ") == nil)
    }

    @Test("A VIN containing I, O or Q is refused")
    func vinWithForbiddenLettersIsRefused() {
        // ISO 3779 excludes them so they cannot be confused with 1 and 0.
        #expect(VehicleDraftValidator.normalisedVIN("IOQIOQIOQIOQIOQIO") == nil)
    }

    @Test("A malformed identifier is reported on the draft")
    @MainActor
    func malformedIdentifiersAreFlagged() {
        let draft = VehicleDraft()
        draft.plate = "nonsense"
        draft.vin = "short"

        #expect(draft.plateIsMalformed)
        #expect(draft.vinIsMalformed)
    }

    @Test("An empty optional identifier is not malformed")
    @MainActor
    func emptyIdentifiersAreFine() {
        let draft = VehicleDraft()

        #expect(!draft.plateIsMalformed)
        #expect(!draft.vinIsMalformed)
    }
}

@Suite("Multipart encoding")
struct MultipartFormDataTests {

    @Test("A text field is framed with its name")
    func textFieldIsFramed() throws {
        var form = MultipartFormData()
        form.append("exterior", name: "kind")

        let body = try #require(String(data: form.finalised(), encoding: .utf8))

        #expect(body.contains("Content-Disposition: form-data; name=\"kind\""))
        #expect(body.contains("exterior"))
    }

    @Test("A file carries its filename and declared type")
    func fileCarriesMetadata() throws {
        var form = MultipartFormData()
        form.append(
            Data([0xFF, 0xD8, 0xFF]),
            name: "file",
            filename: "front.jpg",
            contentType: "image/jpeg"
        )

        let body = try #require(String(data: form.finalised(), encoding: .isoLatin1))

        #expect(body.contains("name=\"file\"; filename=\"front.jpg\""))
        #expect(body.contains("Content-Type: image/jpeg"))
    }

    @Test("The body is closed with the terminating boundary")
    func bodyIsTerminated() throws {
        var form = MultipartFormData()
        form.append("value", name: "field")

        let body = try #require(String(data: form.finalised(), encoding: .utf8))
        let boundary = form.contentType.replacingOccurrences(
            of: "multipart/form-data; boundary=", with: ""
        )

        #expect(body.hasSuffix("--\(boundary)--\r\n"))
    }

    @Test("Binary content survives encoding byte for byte")
    func binaryIsPreserved() {
        // A photo is not text; any transformation here corrupts the upload.
        let payload = Data((0...255).map { UInt8($0) })
        var form = MultipartFormData()
        form.append(payload, name: "file", filename: "a.bin", contentType: "application/octet-stream")

        let encoded = form.finalised()

        #expect(encoded.range(of: payload) != nil)
    }

    @Test("Each form gets its own boundary")
    func boundariesAreUnique() {
        // A shared boundary would let one request's content terminate another's.
        #expect(MultipartFormData().contentType != MultipartFormData().contentType)
    }
}

@Suite("Analysis report presentation")
struct AnalysisPresentationTests {

    private func analysis(findings: [(FindingSeverity, String)]) throws -> Analysis {
        let encoded = findings.map { severity, title in
            """
            {"category":"general","severity":"\(severity.rawValue)",
             "title":"\(title)","detail":"detay"}
            """
        }.joined(separator: ",")

        let json = """
        {
          "id": "019FC936-2E85-77AE-B3D1-9239C9BD486B",
          "vehicle_id": "019FC936-2E85-77AE-B3D1-9239C9BD486C",
          "status": "completed",
          "trust_score": 84,
          "risk_level": "low",
          "summary": "Araç düşük riskli görünüyor.",
          "failure_reason": null,
          "photos": [],
          "findings": [\(encoded)],
          "created_at": "2026-08-03T19:59:59.076508Z",
          "started_at": "2026-08-03T19:59:59.076508Z",
          "completed_at": "2026-08-03T20:00:01.076508Z"
        }
        """
        return try JSONDecoder.truvix.decode(Analysis.self, from: Data(json.utf8))
    }

    @Test("Risks are the warnings and the critical findings")
    func risksAreTheSeriousFindings() throws {
        let report = try analysis(findings: [
            (.warning, "Kilometre yüksek"),
            (.critical, "Ağır hasar"),
            (.positive, "Bakımlı"),
            (.info, "VIN yok"),
        ])

        #expect(report.risks.count == 2)
        #expect(report.strengths.count == 1)
    }

    @Test("A report with no risks reports none")
    func cleanReportHasNoRisks() throws {
        let report = try analysis(findings: [(.positive, "Bakımlı")])

        #expect(report.risks.isEmpty)
        #expect(report.strengths.count == 1)
    }

    @Test("A completed report decodes its score and verdict")
    func completedReportDecodes() throws {
        let report = try analysis(findings: [])

        #expect(report.status == .completed)
        #expect(report.trustScore == 84)
        #expect(report.riskLevel == .low)
        #expect(report.completedAt != nil)
    }
}

@Suite("Notification presentation")
struct NotificationPresentationTests {

    @Test("Tab counts read from the summary")
    func tabCountsMapCorrectly() {
        let summary = NotificationSummary(
            total: 23, unread: 7, opportunities: 8, risks: 5, aiSuggestions: 7
        )

        #expect(summary.count(for: nil) == 23)
        #expect(summary.count(for: .opportunity) == 8)
        #expect(summary.count(for: .risk) == 5)
        #expect(summary.count(for: .aiSuggestion) == 7)
        #expect(summary.count(for: .system) == 3)
    }

    @Test("A system count never goes negative")
    func systemCountIsClamped() {
        // The backend counts categories independently, so arithmetic on them
        // must not produce a nonsense figure if they ever exceed the total.
        let summary = NotificationSummary(
            total: 5, unread: 0, opportunities: 4, risks: 4, aiSuggestions: 4
        )

        #expect(summary.count(for: .system) == 0)
    }

    @Test("A notification decodes from the shape the API sends")
    func notificationDecodes() throws {
        let json = """
        {
          "id": "019FC936-2E85-77AE-B3D1-9239C9BD486B",
          "category": "opportunity",
          "event_type": "price_drop",
          "title": "Fiyat düştü!",
          "body": "İzlediğiniz BMW 320i M Sport 25.000 TL düştü.",
          "vehicle_id": "019FC936-2E85-77AE-B3D1-9239C9BD486C",
          "read": false,
          "created_at": "2026-08-03T19:59:59.076508Z"
        }
        """

        let notification = try JSONDecoder.truvix.decode(
            AppNotification.self, from: Data(json.utf8)
        )

        #expect(notification.category == .opportunity)
        #expect(notification.eventType == "price_drop")
        #expect(!notification.read)
        #expect(notification.vehicleId != nil)
    }
}
