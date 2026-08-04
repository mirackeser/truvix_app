import SwiftUI

/// The home screen: greeting, hero action, and one row per data section.
struct DashboardView: View {
    @State private var model: DashboardModel
    private let onStartAnalysis: () -> Void
    private let onOpenNotifications: () -> Void

    init(
        api: any TruvixAPI,
        onStartAnalysis: @escaping () -> Void,
        onOpenNotifications: @escaping () -> Void
    ) {
        _model = State(wrappedValue: DashboardModel(api: api))
        self.onStartAnalysis = onStartAnalysis
        self.onOpenNotifications = onOpenNotifications
    }

    var body: some View {
        NavigationStack {
            Group {
                switch model.state {
                case .idle, .loading:
                    LoadingState()
                case let .failed(error):
                    FailureState(error: error) {
                        Task { await model.load() }
                    }
                case let .loaded(dashboard):
                    content(dashboard)
                }
            }
            .screenBackground()
            .navigationBarHidden(true)
        }
        .task { await model.load() }
    }

    private func content(_ dashboard: Dashboard) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                greeting(dashboard)
                heroCard

                if dashboard.isEmpty {
                    firstRunPrompt
                } else {
                    if !dashboard.recentAnalyses.isEmpty {
                        recentAnalyses(dashboard.recentAnalyses)
                    }
                    if !dashboard.priceDrops.isEmpty {
                        priceTracking(dashboard.priceDrops)
                    }
                    if !dashboard.recommendations.isEmpty {
                        recommendations(dashboard.recommendations)
                    }
                    if !dashboard.savedVehicles.isEmpty {
                        savedVehicles(dashboard.savedVehicles)
                    }
                }

                premiumBanner(dashboard.user)
            }
            .padding(.horizontal, Theme.Spacing.md)
            .padding(.top, Theme.Spacing.sm)
            .padding(.bottom, Theme.Spacing.xl)
        }
        .refreshable { await model.refresh() }
    }

    // MARK: - Sections

    private func greeting(_ dashboard: Dashboard) -> some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                Text("Merhaba, \(dashboard.user.firstName) 👋")
                    .font(Theme.Typography.title)
                    .foregroundStyle(Theme.Colours.textPrimary)
                Text("Bugün doğru kararı vermek için Truvix seninle.")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colours.textSecondary)
            }

            Spacer(minLength: Theme.Spacing.sm)

            Button(action: onOpenNotifications) {
                ZStack(alignment: .topTrailing) {
                    Image(systemName: "bell")
                        .font(.system(size: 18, weight: .medium))
                        .foregroundStyle(Theme.Colours.textPrimary)
                        .frame(width: 44, height: 44)
                        .background(Theme.Colours.surface, in: Circle())

                    if dashboard.unreadNotifications > 0 {
                        Text("\(min(dashboard.unreadNotifications, 99))")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundStyle(Theme.Colours.textOnBrand)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(Theme.Colours.brand, in: Capsule())
                            .offset(x: 4, y: -2)
                    }
                }
            }
            .accessibilityLabel("Bildirimler, \(dashboard.unreadNotifications) okunmamış")
        }
    }

    private var heroCard: some View {
        Button(action: onStartAnalysis) {
            HStack(spacing: Theme.Spacing.md) {
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    Text("Yeni Analiz Başlat")
                        .font(Theme.Typography.title)
                        .foregroundStyle(Theme.Colours.textPrimary)
                    Text("AI destekli analiz ile aracı satın almadan önce tüm riskleri keşfet.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colours.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 0)

                Image(systemName: "plus")
                    .font(.system(size: 24, weight: .semibold))
                    .foregroundStyle(Theme.Colours.textOnBrand)
                    .frame(width: 56, height: 56)
                    .background(Theme.Colours.brandGradient, in: Circle())
            }
            .padding(Theme.Spacing.md)
            .background {
                RoundedRectangle(cornerRadius: Theme.Radius.large, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [
                                Theme.Colours.brand.opacity(0.30),
                                Theme.Colours.surface,
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
            }
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.large, style: .continuous)
                    .stroke(Theme.Colours.brand.opacity(0.35), lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.large, style: .continuous))
        }
        .buttonStyle(.plain)
    }

    private var firstRunPrompt: some View {
        EmptyState(
            symbolName: "car.side",
            title: "Garajın henüz boş",
            message: "İlk aracını ekleyip analiz başlat; risk skoru, fiyat takibi "
                + "ve AI önerileri burada görünecek."
        ) {
            Button("İlk Analizi Başlat", action: onStartAnalysis)
                .buttonStyle(PrimaryButtonStyle())
        }
        .padding(.top, Theme.Spacing.md)
    }

    private func recentAnalyses(_ analyses: [AnalysisSummary]) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader("Son Analizlerin")
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: Theme.Spacing.sm) {
                    ForEach(analyses) { analysis in
                        NavigationLink {
                            AnalysisDetailPlaceholder(summary: analysis)
                        } label: {
                            AnalysisCard(analysis: analysis)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 1)
            }
        }
    }

    private func priceTracking(_ drops: [VehicleSummary]) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader("Fiyat Takibi")
            VStack(spacing: Theme.Spacing.xs) {
                ForEach(drops) { summary in
                    PriceDropRow(summary: summary)
                }
            }
        }
    }

    private func recommendations(_ analyses: [AnalysisSummary]) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader("AI Önerileri")
            if let best = analyses.first {
                RecommendationCard(analysis: best, isTopPick: true)
            }
            ForEach(analyses.dropFirst()) { analysis in
                RecommendationCard(analysis: analysis, isTopPick: false)
            }
        }
    }

    private func savedVehicles(_ vehicles: [Vehicle]) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader("Kaydedilen Araçlar")
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: Theme.Spacing.sm) {
                    ForEach(vehicles) { vehicle in
                        SavedVehicleCard(vehicle: vehicle)
                    }
                }
                .padding(.horizontal, 1)
            }
        }
    }

    private func premiumBanner(_ user: DashboardUser) -> some View {
        HStack(spacing: Theme.Spacing.sm) {
            Image(systemName: "crown.fill")
                .foregroundStyle(Theme.Colours.warning)

            VStack(alignment: .leading, spacing: 2) {
                Text("TRUVIX PREMIUM")
                    .font(Theme.Typography.label)
                    .foregroundStyle(Theme.Colours.warning)
                Text(
                    user.isPremium
                        ? "Premium üyesin • Sınırsız analiz hakkın var"
                        : "Sınırsız analiz ve gelişmiş AI raporları"
                )
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colours.textSecondary)
            }

            Spacer(minLength: 0)

            Image(systemName: "chevron.right")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Theme.Colours.textSecondary)
        }
        .padding(Theme.Spacing.md)
        .background(Theme.Colours.warning.opacity(0.10))
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.medium, style: .continuous)
                .stroke(Theme.Colours.warning.opacity(0.25), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.medium, style: .continuous))
    }
}

// MARK: - Cards

/// A recent-analysis card from the home screen's first carousel.
private struct AnalysisCard: View {
    let analysis: AnalysisSummary

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            HStack {
                Text(analysis.vehicleDisplayName.prefix(1))
                    .font(Theme.Typography.headline)
                    .foregroundStyle(Theme.Colours.textPrimary)
                    .frame(width: 32, height: 32)
                    .background(Theme.Colours.surfaceElevated, in: Circle())

                Spacer()

                if let score = analysis.trustScore {
                    ScoreBadge(score: score, size: 38)
                } else {
                    StatusChip(status: analysis.status)
                }
            }

            VehicleGlyph()
                .frame(height: 56)

            Text(analysis.vehicleDisplayName)
                .font(Theme.Typography.headline)
                .foregroundStyle(Theme.Colours.textPrimary)
                .lineLimit(1)

            Text(analysis.createdAt.formatted(.dateTime.day().month(.abbreviated).year()))
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colours.textSecondary)

            HStack(spacing: Theme.Spacing.xxs) {
                Text("Raporu Gör")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colours.brand)
                Image(systemName: "arrow.right")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.Colours.brand)
            }
            .padding(.top, Theme.Spacing.xxs)
        }
        .padding(Theme.Spacing.sm)
        .frame(width: 168, alignment: .leading)
        .background(Theme.Colours.surface)
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.large, style: .continuous)
                .stroke(Theme.Colours.border, lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.large, style: .continuous))
    }
}

/// A price-tracking row.
private struct PriceDropRow: View {
    let summary: VehicleSummary

    var body: some View {
        Card(padding: Theme.Spacing.sm) {
            HStack(spacing: Theme.Spacing.sm) {
                VehicleGlyph()
                    .frame(width: 56, height: 40)

                VStack(alignment: .leading, spacing: 2) {
                    Text(summary.vehicle.displayName)
                        .font(Theme.Typography.callout)
                        .foregroundStyle(Theme.Colours.textPrimary)
                        .lineLimit(1)
                    Text(summary.vehicle.specificationSummary)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colours.textSecondary)
                        .lineLimit(1)
                }

                Spacer(minLength: Theme.Spacing.xs)

                if let trend = summary.priceTrend,
                   let change = trend.formattedChange(summary.vehicle.currency) {
                    VStack(alignment: .trailing, spacing: 2) {
                        HStack(spacing: 2) {
                            Image(systemName: trend.hasDropped ? "arrow.down" : "arrow.up")
                                .font(.system(size: 10, weight: .bold))
                            Text(change)
                                .font(Theme.Typography.callout)
                        }
                        .foregroundStyle(
                            trend.hasDropped ? Theme.Colours.brand : Theme.Colours.danger
                        )

                        Text("Son \(trend.windowDays) günde")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colours.textSecondary)
                    }
                }
            }
        }
    }
}

/// An AI recommendation card. The top pick gets the highlighted treatment the
/// design gives it.
private struct RecommendationCard: View {
    let analysis: AnalysisSummary
    let isTopPick: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            if isTopPick {
                Text("🔥 SENİN İÇİN EN İYİSİ")
                    .font(Theme.Typography.label)
                    .foregroundStyle(Theme.Colours.brand)
            }

            HStack(spacing: Theme.Spacing.sm) {
                VehicleGlyph()
                    .frame(width: 72, height: 48)

                VStack(alignment: .leading, spacing: 2) {
                    Text(analysis.vehicleDisplayName)
                        .font(Theme.Typography.headline)
                        .foregroundStyle(Theme.Colours.textPrimary)
                        .lineLimit(1)
                    if let level = analysis.riskLevel {
                        Text(level.displayName)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colours.textSecondary)
                    }
                }

                Spacer(minLength: 0)

                if let score = analysis.trustScore {
                    VStack(spacing: 2) {
                        ScoreBadge(score: score, size: 46)
                        Text("Güven Skoru")
                            .font(.system(size: 10))
                            .foregroundStyle(Theme.Colours.textSecondary)
                    }
                }
            }
        }
        .padding(Theme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background {
            if isTopPick {
                RoundedRectangle(cornerRadius: Theme.Radius.large, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [Theme.Colours.brand.opacity(0.22), Theme.Colours.surface],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
            } else {
                RoundedRectangle(cornerRadius: Theme.Radius.large, style: .continuous)
                    .fill(Theme.Colours.surface)
            }
        }
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.large, style: .continuous)
                .stroke(
                    isTopPick ? Theme.Colours.brand.opacity(0.35) : Theme.Colours.border,
                    lineWidth: 1
                )
        )
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.large, style: .continuous))
    }
}

/// A compact saved-vehicle tile.
private struct SavedVehicleCard: View {
    let vehicle: Vehicle

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            ZStack(alignment: .topTrailing) {
                VehicleGlyph()
                    .frame(height: 64)
                Image(systemName: "bookmark.fill")
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.Colours.brand)
                    .padding(6)
            }

            Text(vehicle.displayName)
                .font(Theme.Typography.callout)
                .foregroundStyle(Theme.Colours.textPrimary)
                .lineLimit(1)

            Text(vehicle.specificationSummary)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colours.textSecondary)
                .lineLimit(1)
        }
        .padding(Theme.Spacing.sm)
        .frame(width: 150, alignment: .leading)
        .background(Theme.Colours.surface)
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.medium, style: .continuous)
                .stroke(Theme.Colours.border, lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.medium, style: .continuous))
    }
}

/// A stand-in for a vehicle photograph.
///
/// The app has no photographs of its own and inventing them would misrepresent
/// a real listing, so the tile is deliberately a graphic rather than a
/// placeholder pretending to be a picture.
struct VehicleGlyph: View {
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            Theme.Colours.surfaceElevated,
                            Theme.Colours.brand.opacity(0.14),
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
            Image(systemName: "car.side.fill")
                .font(.system(size: 22, weight: .regular))
                .foregroundStyle(Theme.Colours.brand.opacity(0.75))
        }
        .frame(maxWidth: .infinity)
        .accessibilityHidden(true)
    }
}

/// A chip showing where an unfinished analysis has got to.
struct StatusChip: View {
    let status: AnalysisStatus

    var body: some View {
        Text(status.displayName)
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(tint)
            .padding(.horizontal, Theme.Spacing.xs)
            .padding(.vertical, 3)
            .background(tint.opacity(0.14), in: Capsule())
    }

    private var tint: Color {
        switch status {
        case .completed: Theme.Colours.brand
        case .failed: Theme.Colours.danger
        case .pending, .processing: Theme.Colours.warning
        }
    }
}

/// Interim destination for a tapped analysis card.
///
/// The full report screen arrives with the analysis slice; this shows what is
/// already known so the card is not a dead link in the meantime.
struct AnalysisDetailPlaceholder: View {
    let summary: AnalysisSummary

    var body: some View {
        VStack(spacing: Theme.Spacing.lg) {
            if let score = summary.trustScore {
                ScoreBadge(score: score, size: 96)
            }
            Text(summary.vehicleDisplayName)
                .font(Theme.Typography.title)
                .foregroundStyle(Theme.Colours.textPrimary)
            if let level = summary.riskLevel {
                Text(level.displayName)
                    .font(Theme.Typography.callout)
                    .foregroundStyle(Theme.Colours.brand)
            }
            Text("Ayrıntılı rapor ekranı yakında bu bölümde açılacak.")
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colours.textSecondary)
                .multilineTextAlignment(.center)
            Spacer()
        }
        .padding(Theme.Spacing.lg)
        .screenBackground()
        .navigationTitle("Analiz")
        .navigationBarTitleDisplayMode(.inline)
    }
}
