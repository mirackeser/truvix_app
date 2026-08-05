import SwiftUI

/// The finished report: score, verdict and the findings that explain both.
///
/// The findings are shown in full rather than summarised, because the score's
/// credibility rests on being able to see exactly what produced it.
struct AnalysisReportContent: View {
    let analysis: Analysis

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.md) {
            scoreCard

            if let summary = analysis.summary {
                Card {
                    VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                        Label("AI Değerlendirmesi", systemImage: "sparkles")
                            .font(Theme.Typography.label)
                            .foregroundStyle(Theme.Colours.brand)
                        Text(summary)
                            .font(Theme.Typography.body)
                            .foregroundStyle(Theme.Colours.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }

            if let reason = analysis.failureReason {
                ErrorBanner(message: reason)
            }

            if !analysis.risks.isEmpty {
                findingSection(
                    title: "Risk Faktörleri",
                    findings: analysis.risks,
                    tint: Theme.Colours.warning
                )
            }

            if !analysis.strengths.isEmpty {
                findingSection(
                    title: "Güçlü Yönler",
                    findings: analysis.strengths,
                    tint: Theme.Colours.brand
                )
            }

            let informational = analysis.findings.filter { $0.severity == .info }
            if !informational.isEmpty {
                findingSection(
                    title: "Bilgi Notları",
                    findings: informational,
                    tint: Theme.Colours.textSecondary
                )
            }

            if !analysis.photos.isEmpty {
                Card {
                    HStack {
                        Image(systemName: "photo.stack")
                            .foregroundStyle(Theme.Colours.textSecondary)
                        Text("\(analysis.photos.count) dosya değerlendirmeye dahil edildi")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colours.textSecondary)
                        Spacer()
                    }
                }
            }
        }
    }

    private var scoreCard: some View {
        Card(padding: Theme.Spacing.lg) {
            VStack(spacing: Theme.Spacing.sm) {
                if let score = analysis.trustScore {
                    ScoreBadge(score: score, size: 116)

                    Text("\(score)/100")
                        .font(Theme.Typography.score)
                        .foregroundStyle(Theme.Colours.textPrimary)
                } else {
                    StatusChip(status: analysis.status)
                }

                if let level = analysis.riskLevel {
                    Text(level.displayName)
                        .font(Theme.Typography.headline)
                        .foregroundStyle(tint(for: level))
                }

                Text("Güven Skoru")
                    .font(Theme.Typography.label)
                    .foregroundStyle(Theme.Colours.textSecondary)
            }
            .frame(maxWidth: .infinity)
        }
    }

    private func findingSection(
        title: String,
        findings: [RiskFinding],
        tint: Color
    ) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            SectionHeader(title)
            Card(padding: Theme.Spacing.sm) {
                VStack(spacing: Theme.Spacing.sm) {
                    ForEach(Array(findings.enumerated()), id: \.element.id) { index, finding in
                        FindingRow(finding: finding, tint: tint)
                        if index < findings.count - 1 {
                            Divider().overlay(Theme.Colours.border)
                        }
                    }
                }
            }
        }
    }

    private func tint(for level: RiskLevel) -> Color {
        switch level {
        case .low: Theme.Colours.brand
        case .medium: Theme.Colours.warning
        case .high: Theme.Colours.danger
        }
    }
}

private struct FindingRow: View {
    let finding: RiskFinding
    let tint: Color

    var body: some View {
        HStack(alignment: .top, spacing: Theme.Spacing.sm) {
            Image(systemName: finding.severity.symbolName)
                .font(Theme.Typography.body)
                .foregroundStyle(tint)
                .frame(width: 22)

            VStack(alignment: .leading, spacing: 2) {
                Text(finding.title)
                    .font(Theme.Typography.callout)
                    .foregroundStyle(Theme.Colours.textPrimary)
                Text(finding.detail)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colours.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .combine)
    }
}

/// The report as its own screen, reached from an analysis card.
struct AnalysisReportView: View {
    let analysisID: UUID
    let api: any TruvixAPI

    @State private var state: LoadState<Analysis> = .idle

    var body: some View {
        Group {
            switch state {
            case .idle, .loading:
                LoadingState(message: "Rapor yükleniyor…")
            case let .failed(error):
                FailureState(error: error) {
                    Task { await load() }
                }
            case let .loaded(analysis):
                ScrollView {
                    AnalysisReportContent(analysis: analysis)
                        .padding(.horizontal, Theme.Spacing.md)
                        .padding(.bottom, Theme.Spacing.xl)
                }
                .refreshable { await load() }
            }
        }
        .screenBackground()
        .navigationTitle("Analiz Raporu")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func load() async {
        if state.value == nil {
            state = .loading
        }
        do {
            state = .loaded(try await api.analysis(id: analysisID))
        } catch {
            if state.value == nil {
                state = .failed(APIError.wrapping(error))
            }
        }
    }
}
