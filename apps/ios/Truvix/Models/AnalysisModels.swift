import Foundation

/// Where an analysis run has got to.
enum AnalysisStatus: String, Codable, Sendable {
    case pending, processing, completed, failed

    var displayName: String {
        switch self {
        case .pending: "Bekliyor"
        case .processing: "Analiz ediliyor"
        case .completed: "Tamamlandı"
        case .failed: "Başarısız"
        }
    }

    var isTerminal: Bool { self == .completed || self == .failed }
}

/// The banded reading of a trust score, as the report presents it.
enum RiskLevel: String, Codable, Sendable {
    case low, medium, high

    var displayName: String {
        switch self {
        case .low: "Düşük Risk"
        case .medium: "Orta Risk"
        case .high: "Yüksek Risk"
        }
    }
}

/// What a finding concerns.
enum FindingCategory: String, Codable, Sendable {
    case mileage, age, damage, maintenance, price, documentation, general

    var symbolName: String {
        switch self {
        case .mileage: "speedometer"
        case .age: "calendar"
        case .damage: "exclamationmark.triangle"
        case .maintenance: "wrench.and.screwdriver"
        case .price: "turkishlirasign.circle"
        case .documentation: "doc.text"
        case .general: "info.circle"
        }
    }
}

/// How much weight a finding carries, mirroring the +/- markers on the report.
enum FindingSeverity: String, Codable, Sendable {
    case positive, info, warning, critical

    var symbolName: String {
        switch self {
        case .positive: "plus.circle.fill"
        case .info: "info.circle.fill"
        case .warning: "exclamationmark.triangle.fill"
        case .critical: "exclamationmark.octagon.fill"
        }
    }
}

/// What an uploaded file depicts.
enum PhotoKind: String, Codable, CaseIterable, Sendable {
    case exterior, interior, engine, dashboard, damage, document, other

    var displayName: String {
        switch self {
        case .exterior: "Dış Görünüm"
        case .interior: "İç Mekan"
        case .engine: "Motor"
        case .dashboard: "Gösterge"
        case .damage: "Hasar"
        case .document: "Belge"
        case .other: "Diğer"
        }
    }
}

/// One line of the report's risk factor list.
struct RiskFinding: Codable, Identifiable, Equatable, Sendable {
    let category: FindingCategory
    let severity: FindingSeverity
    let title: String
    let detail: String

    /// Findings carry no server identifier; the title is unique within a
    /// report because the engine drops duplicates by title.
    var id: String { title }
}

/// A file attached to an analysis.
struct AnalysisPhoto: Codable, Identifiable, Equatable, Sendable {
    let id: UUID
    let kind: PhotoKind
    let contentType: String
    let sizeBytes: Int
    let originalFilename: String?
    let createdAt: Date
}

/// One analysis run with its report, when it has one.
struct Analysis: Codable, Identifiable, Equatable, Sendable {
    let id: UUID
    let vehicleId: UUID
    let status: AnalysisStatus
    let trustScore: Int?
    let riskLevel: RiskLevel?
    let summary: String?
    let failureReason: String?
    let photos: [AnalysisPhoto]
    let findings: [RiskFinding]
    let createdAt: Date
    let startedAt: Date?
    let completedAt: Date?

    /// The findings that count against the vehicle, most severe first.
    var risks: [RiskFinding] {
        findings.filter { $0.severity == .warning || $0.severity == .critical }
    }

    /// The findings that count in the vehicle's favour.
    var strengths: [RiskFinding] {
        findings.filter { $0.severity == .positive }
    }
}

/// The compact view used by lists and the home screen's cards.
struct AnalysisSummary: Codable, Identifiable, Equatable, Sendable {
    let id: UUID
    let vehicleId: UUID
    let vehicleDisplayName: String
    let status: AnalysisStatus
    let trustScore: Int?
    let riskLevel: RiskLevel?
    let createdAt: Date
    let completedAt: Date?
}
