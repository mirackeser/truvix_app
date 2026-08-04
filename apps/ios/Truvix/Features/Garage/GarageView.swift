import SwiftUI

/// The garage: every saved vehicle, filtered by tab and sorted on demand.
struct GarageView: View {
    @State private var model: GarageModel
    private let onStartAnalysis: () -> Void

    init(api: any TruvixAPI, onStartAnalysis: @escaping () -> Void) {
        _model = State(wrappedValue: GarageModel(api: api))
        self.onStartAnalysis = onStartAnalysis
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                header
                filterTabs

                Group {
                    switch model.state {
                    case .idle, .loading:
                        LoadingState()
                    case let .failed(error):
                        FailureState(error: error) {
                            Task { await model.load() }
                        }
                    case let .loaded(vehicles):
                        if vehicles.isEmpty {
                            emptyState
                        } else {
                            list(vehicles)
                        }
                    }
                }
            }
            .screenBackground()
            .navigationBarHidden(true)
        }
        .task { await model.load() }
    }

    // MARK: - Sections

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Garajım")
                    .font(Theme.Typography.display)
                    .foregroundStyle(Theme.Colours.textPrimary)
                Text("\(model.stats.total) araç")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colours.textSecondary)
            }

            Spacer()

            Menu {
                Picker("Sıralama", selection: sortBinding) {
                    ForEach(VehicleSort.allCases) { option in
                        Text(option.title).tag(option)
                    }
                }
            } label: {
                Image(systemName: "line.3.horizontal.decrease")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundStyle(Theme.Colours.textPrimary)
                    .frame(width: 44, height: 44)
                    .background(Theme.Colours.surface, in: Circle())
            }
            .accessibilityLabel("Sıralama seçenekleri")
        }
        .padding(.horizontal, Theme.Spacing.md)
        .padding(.bottom, Theme.Spacing.sm)
    }

    private var filterTabs: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: Theme.Spacing.xs) {
                ForEach(GarageFilter.allCases) { candidate in
                    FilterChip(
                        title: candidate.title,
                        count: model.stats.count(for: candidate),
                        isSelected: model.filter == candidate
                    ) {
                        model.filter = candidate
                    }
                }
            }
            .padding(.horizontal, Theme.Spacing.md)
        }
        .padding(.bottom, Theme.Spacing.sm)
    }

    private func list(_ vehicles: [VehicleSummary]) -> some View {
        ScrollView {
            LazyVStack(spacing: Theme.Spacing.sm) {
                ForEach(vehicles) { summary in
                    VehicleCard(summary: summary) {
                        Task { await model.toggleFavourite(summary) }
                    }
                    .task { await model.loadMoreIfNeeded(currentItem: summary) }
                }

                if model.isLoadingMore {
                    ProgressView()
                        .tint(Theme.Colours.brand)
                        .padding(Theme.Spacing.md)
                }
            }
            .padding(.horizontal, Theme.Spacing.md)
            .padding(.bottom, Theme.Spacing.xl)
        }
        .refreshable { await model.load() }
    }

    private var emptyState: some View {
        ScrollView {
            EmptyState(
                symbolName: emptySymbol,
                title: emptyTitle,
                message: emptyMessage
            ) {
                if model.filter == .all {
                    Button("Araç Ekle", action: onStartAnalysis)
                        .buttonStyle(PrimaryButtonStyle())
                }
            }
            .padding(.top, Theme.Spacing.xxl)
        }
        .refreshable { await model.load() }
    }

    private var sortBinding: Binding<VehicleSort> {
        Binding(get: { model.sort }, set: { model.sort = $0 })
    }

    private var emptySymbol: String {
        switch model.filter {
        case .all: "car.side"
        case .favourites: "heart"
        case .comparison: "square.on.square"
        case .priceDropped: "arrow.down.right"
        case .viewedToday: "clock"
        }
    }

    private var emptyTitle: String {
        switch model.filter {
        case .all: "Garajın boş"
        case .favourites: "Favori araç yok"
        case .comparison: "Karşılaştırma listesi boş"
        case .priceDropped: "Fiyatı düşen araç yok"
        case .viewedToday: "Bugün araç bakmadın"
        }
    }

    private var emptyMessage: String {
        switch model.filter {
        case .all:
            "İncelediğin araçları buraya ekle; fiyat değişimlerini ve risk "
                + "skorlarını tek yerden takip et."
        case .favourites:
            "Beğendiğin araçları favorilere ekleyerek hızlıca ulaşabilirsin."
        case .comparison:
            "Karşılaştırmak istediğin araçları işaretle."
        case .priceDropped:
            "Takip ettiğin araçların fiyatı düştüğünde burada görünecek."
        case .viewedToday:
            "Bugün incelediğin araçlar burada listelenir."
        }
    }
}

// MARK: - Components

/// A garage tab with its count, as the design shows them.
private struct FilterChip: View {
    let title: String
    let count: Int
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: Theme.Spacing.xxs) {
                Text(title)
                    .font(Theme.Typography.callout)
                if count > 0 {
                    Text("\(count)")
                        .font(.system(size: 12, weight: .bold))
                        .monospacedDigit()
                        .opacity(0.8)
                }
            }
            .foregroundStyle(
                isSelected ? Theme.Colours.textOnBrand : Theme.Colours.textSecondary
            )
            .padding(.horizontal, Theme.Spacing.md)
            .padding(.vertical, Theme.Spacing.xs)
            .background {
                if isSelected {
                    Capsule().fill(Theme.Colours.brandGradient)
                } else {
                    Capsule().fill(Theme.Colours.surface)
                }
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(title), \(count) araç")
        .accessibilityAddTraits(isSelected ? [.isSelected] : [])
    }
}

/// One vehicle row in the garage.
private struct VehicleCard: View {
    let summary: VehicleSummary
    let onToggleFavourite: () -> Void

    private var vehicle: Vehicle { summary.vehicle }

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                    VehicleGlyph()
                        .frame(width: 84, height: 60)

                    VStack(alignment: .leading, spacing: 2) {
                        Text(vehicle.displayName)
                            .font(Theme.Typography.headline)
                            .foregroundStyle(Theme.Colours.textPrimary)
                            .lineLimit(1)

                        Text(vehicle.specificationSummary)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colours.textSecondary)
                            .lineLimit(1)

                        Text(vehicle.formattedPrice)
                            .font(Theme.Typography.headline)
                            .foregroundStyle(Theme.Colours.textPrimary)
                            .padding(.top, Theme.Spacing.xxs)
                    }

                    Spacer(minLength: 0)

                    Button(action: onToggleFavourite) {
                        Image(systemName: vehicle.isFavourite ? "heart.fill" : "heart")
                            .font(.system(size: 17))
                            .foregroundStyle(
                                vehicle.isFavourite
                                    ? Theme.Colours.danger
                                    : Theme.Colours.textSecondary
                            )
                            .frame(width: 36, height: 36)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(
                        vehicle.isFavourite ? "Favorilerden çıkar" : "Favorilere ekle"
                    )
                }

                if let trend = summary.priceTrend,
                   let change = trend.formattedChange(vehicle.currency) {
                    HStack(spacing: Theme.Spacing.xxs) {
                        Image(systemName: trend.hasDropped ? "arrow.down" : "arrow.up")
                            .font(.system(size: 10, weight: .bold))
                        Text(change)
                            .font(Theme.Typography.caption)
                        if let percentage = trend.percentageChange {
                            Text("(\(percentage.formatted))")
                                .font(Theme.Typography.caption)
                                .opacity(0.85)
                        }
                        Text("• son \(trend.windowDays) gün")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colours.textSecondary)
                    }
                    .foregroundStyle(
                        trend.hasDropped ? Theme.Colours.brand : Theme.Colours.danger
                    )
                }

                if vehicle.isInComparison {
                    Label("Karşılaştırma listesinde", systemImage: "square.on.square")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colours.textSecondary)
                }
            }
        }
    }
}
