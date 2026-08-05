import Foundation
import Observation

/// The steps of the new-analysis flow, in the order the design numbers them.
enum AnalysisStep: Int, CaseIterable, Identifiable, Sendable {
    case vehicleDetails = 1
    case evidence
    case review
    case running

    var id: Int { rawValue }

    var title: String {
        switch self {
        case .vehicleDetails: "Araç Bilgileri"
        case .evidence: "Fotoğraflar"
        case .review: "Onay"
        case .running: "AI Analiz"
        }
    }
}

/// One file the user has chosen but not yet uploaded.
struct PendingUpload: Identifiable, Equatable, Sendable {
    let id = UUID()
    let data: Data
    let filename: String
    let contentType: String
    var kind: PhotoKind
}

/// Everything the user has typed, before it becomes a request.
///
/// Kept as text rather than parsed values so a half-typed number is a normal
/// state rather than something the model has to defend against.
@MainActor
@Observable
final class VehicleDraft {
    var make = ""
    var model = ""
    var variant = ""
    var modelYear = ""
    var mileageKm = ""
    var price = ""
    var city = ""
    var plate = ""
    var vin = ""
    var fuelType: FuelType = .petrol
    var transmission: Transmission = .automatic
    var bodyType: BodyType?

    var trimmedMake: String { make.trimmingCharacters(in: .whitespaces) }
    var trimmedModel: String { model.trimmingCharacters(in: .whitespaces) }

    var parsedYear: Int? {
        Int(modelYear).flatMap { VehicleDraftValidator.modelYearIsValid($0) ? $0 : nil }
    }

    var parsedMileage: Int? {
        Int(mileageKm.filter(\.isNumber))
            .flatMap { VehicleDraftValidator.mileageIsValid($0) ? $0 : nil }
    }

    var parsedPrice: Money? {
        let digits = price.filter { $0.isNumber || $0 == "." }
        guard let value = Decimal(string: digits, locale: Locale(identifier: "en_US_POSIX")) else {
            return nil
        }
        let money = Money(value)
        return VehicleDraftValidator.priceIsValid(money) ? money : nil
    }

    /// The plate normalised, or nil when the field is empty or malformed.
    var normalisedPlate: String? {
        plate.isEmpty ? nil : VehicleDraftValidator.normalisedPlate(plate)
    }

    var normalisedVIN: String? {
        vin.isEmpty ? nil : VehicleDraftValidator.normalisedVIN(vin)
    }

    /// Whether an optional identifier was typed but does not parse.
    var plateIsMalformed: Bool { !plate.isEmpty && normalisedPlate == nil }
    var vinIsMalformed: Bool { !vin.isEmpty && normalisedVIN == nil }

    var isComplete: Bool {
        !trimmedMake.isEmpty
            && !trimmedModel.isEmpty
            && parsedYear != nil
            && parsedMileage != nil
            && parsedPrice != nil
            && !plateIsMalformed
            && !vinIsMalformed
    }

    /// Build the request, or nil when the draft is not yet complete.
    func makeRequest() -> VehicleCreateRequest? {
        guard isComplete,
              let year = parsedYear,
              let mileage = parsedMileage,
              let askingPrice = parsedPrice else {
            return nil
        }

        let trimmedVariant = variant.trimmingCharacters(in: .whitespaces)
        let trimmedCity = city.trimmingCharacters(in: .whitespaces)

        return VehicleCreateRequest(
            make: trimmedMake,
            model: trimmedModel,
            variant: trimmedVariant.isEmpty ? nil : trimmedVariant,
            modelYear: year,
            mileageKm: mileage,
            fuelType: fuelType,
            transmission: transmission,
            bodyType: bodyType,
            plate: normalisedPlate,
            vin: normalisedVIN,
            city: trimmedCity.isEmpty ? nil : trimmedCity,
            askingPrice: askingPrice
        )
    }
}

/// Drives the new-analysis flow from an empty form to a finished report.
@MainActor
@Observable
final class NewAnalysisModel {
    private(set) var step: AnalysisStep = .vehicleDetails
    private(set) var isSubmitting = false
    private(set) var errorMessage: String?
    private(set) var progressCaption = ""
    private(set) var finishedAnalysis: Analysis?
    private(set) var hasExhaustedQuota = false

    let draft = VehicleDraft()
    var uploads: [PendingUpload] = []

    private let api: any TruvixAPI

    /// Matches the backend's per-analysis file limit, so the picker stops the
    /// user before an upload is rejected.
    static let maximumUploads = 12

    init(api: any TruvixAPI) {
        self.api = api
    }

    var canAddMoreUploads: Bool { uploads.count < Self.maximumUploads }

    func advance() {
        guard let next = AnalysisStep(rawValue: step.rawValue + 1) else { return }
        errorMessage = nil
        step = next
    }

    func goBack() {
        guard let previous = AnalysisStep(rawValue: step.rawValue - 1) else { return }
        errorMessage = nil
        step = previous
    }

    func add(_ upload: PendingUpload) {
        guard canAddMoreUploads else { return }
        uploads.append(upload)
    }

    func remove(_ upload: PendingUpload) {
        uploads.removeAll { $0.id == upload.id }
    }

    /// Save the vehicle, attach the evidence, and run the analysis.
    ///
    /// A failed photo does not abandon the run: the analysis is still worth
    /// producing from what did upload, and stopping would lose the vehicle the
    /// user just entered. What failed is reported afterwards.
    func submit() async {
        guard !isSubmitting, let request = draft.makeRequest() else { return }

        isSubmitting = true
        errorMessage = nil
        step = .running
        defer { isSubmitting = false }

        do {
            progressCaption = "Araç kaydediliyor…"
            let vehicle = try await api.createVehicle(request)

            progressCaption = "Analiz hazırlanıyor…"
            let analysis = try await api.createAnalysis(vehicleID: vehicle.id)

            var failedUploads = 0
            for (index, upload) in uploads.enumerated() {
                progressCaption = "Dosyalar yükleniyor (\(index + 1)/\(uploads.count))…"
                do {
                    _ = try await api.uploadPhoto(
                        upload.data,
                        filename: upload.filename,
                        contentType: upload.contentType,
                        kind: upload.kind,
                        analysisID: analysis.id
                    )
                } catch {
                    failedUploads += 1
                }
            }

            progressCaption = "Truvix AI aracı değerlendiriyor…"
            let finished = try await api.startAnalysis(id: analysis.id)
            finishedAnalysis = finished

            if failedUploads > 0 {
                errorMessage = "\(failedUploads) dosya yüklenemedi; analiz "
                    + "diğer bilgilerle tamamlandı."
            }
        } catch {
            let failure = APIError.wrapping(error)
            errorMessage = failure.localizedDescription
            // A spent allowance is worth naming: the backend's message already
            // explains it, and returning to the review step lets the user try
            // again tomorrow without re-entering everything.
            hasExhaustedQuota = failure.isQuotaExhausted
            step = .review
        }
    }
}
