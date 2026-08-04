import Charts
import Observation
import SwiftUI

/// Drives the vehicle detail screen: the record, its price series, its reports.
@MainActor
@Observable
final class VehicleDetailModel {
    private(set) var vehicle: LoadState<Vehicle> = .idle
    private(set) var history: PriceHistory?
    private(set) var analyses: [AnalysisSummary] = []

    var window: PriceWindow = .month {
        didSet {
            guard window != oldValue else { return }
            Task { await loadHistory() }
        }
    }

    private let api: any TruvixAPI
    private let vehicleID: UUID

    init(api: any TruvixAPI, vehicleID: UUID) {
        self.api = api
        self.vehicleID = vehicleID
    }

    /// The newest completed report's score, shown beside the vehicle.
    var latestScore: Int? {
        analyses.first { $0.status == .completed }?.trustScore
    }

    func load() async {
        if vehicle.value == nil {
            vehicle = .loading
        }

        do {
            vehicle = .loaded(try await api.vehicle(id: vehicleID))
        } catch {
            if vehicle.value == nil {
                vehicle = .failed(APIError.wrapping(error))
                return
            }
        }

        await loadHistory()
        await loadAnalyses()
    }

    func loadHistory() async {
        history = try? await api.priceHistory(
            vehicleID: vehicleID, windowDays: window.rawValue
        )
    }

    private func loadAnalyses() async {
        guard let page = try? await api.analyses(page: 1, pageSize: 50) else { return }
        analyses = page.items.filter { $0.vehicleId == vehicleID }
    }

    func toggleFavourite() async {
        guard let current = vehicle.value else { return }
        if let updated = try? await api.setFavourite(!current.isFavourite, vehicleID: vehicleID) {
            vehicle = .loaded(updated)
        }
    }
}

/// The vehicle detail screen, with its overview, chart and history tabs.
struct VehicleDetailView: View {
    enum Tab: String, CaseIterable, Identifiable {
        case overview
        case chart
        case history

        var id: Self { self }

        var title: String {
            switch self {
            case .overview: "Genel Bakış"
            case .chart: "Fiyat Grafiği"
            case .history: "Geçmiş"
            }
        }
    }

    @State private var model: VehicleDetailModel
    @State private var tab: Tab = .overview

    private let api: any TruvixAPI

    init(api: any TruvixAPI, vehicleID: UUID) {
        _model = State(wrappedValue: VehicleDetailModel(api: api, vehicleID: vehicleID))
        self.api = api
    }

    var body: some View {
        Group {
            switch model.vehicle {
            case .idle, .loading:
                LoadingState()
            case let .failed(error):
                FailureState(error: error) {
                    Task { await model.load() }
                }
            case let .loaded(vehicle):
                content(vehicle)
            }
        }
        .screenBackground()
        .navigationTitle(model.vehicle.value?.displayName ?? "Araç")
        .navigationBarTitleDisplayMode(.inline)
        .task { await model.load() }
    }

    private func content(_ vehicle: Vehicle) -> some View {
        ScrollView {
            VStack(spacing: Theme.Spacing.md) {
                hero(vehicle)
                tabPicker

                switch tab {
                case .overview:
                    OverviewTab(vehicle: vehicle, model: model, api: api)
                case .chart:
                    ChartTab(model: model, currency: vehicle.currency)
                case .history:
                    HistoryTab(model: model, currency: vehicle.currency)
                }
            }
            .padding(.horizontal, Theme.Spacing.md)
            .padding(.bottom, Theme.Spacing.xl)
        }
        .refreshable { await model.load() }
    }

    private func hero(_ vehicle: Vehicle) -> some View {
        Card {
            VStack(spacing: Theme.Spacing.sm) {
                VehicleGlyph()
                    .frame(height: 120)

                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(vehicle.displayName)
                            .font(Theme.Typography.title)
                            .foregroundStyle(Theme.Colours.textPrimary)
                        Text(vehicle.specificationSummary)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colours.textSecondary)
                    }

                    Spacer(minLength: Theme.Spacing.sm)

                    if let score = model.latestScore {
                        ScoreBadge(score: score, size: 52)
                    }
                }

                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Güncel Fiyat")
                            .font(Theme.Typography.label)
                            .foregroundStyle(Theme.Colours.textSecondary)
                        Text(vehicle.formattedPrice)
                            .font(Theme.Typography.title)
                            .foregroundStyle(Theme.Colours.textPrimary)
                    }

                    Spacer()

                    if let trend = model.history?.trend,
                       let change = trend.formattedChange(vehicle.currency) {
                        VStack(alignment: .trailing, spacing: 2) {
                            Text("Değişim (\(trend.windowDays) gün)")
                                .font(Theme.Typography.label)
                                .foregroundStyle(Theme.Colours.textSecondary)
                            HStack(spacing: 3) {
                                Image(systemName: trend.hasDropped ? "arrow.down" : "arrow.up")
                                    .font(.system(size: 11, weight: .bold))
                                Text(change)
                                    .font(Theme.Typography.headline)
                            }
                            .foregroundStyle(
                                trend.hasDropped ? Theme.Colours.brand : Theme.Colours.danger
                            )
                        }
                    }
                }

                HStack(spacing: Theme.Spacing.xs) {
                    Button {
                        Task { await model.toggleFavourite() }
                    } label: {
                        Label(
                            vehicle.isFavourite ? "Favorilerde" : "Favorilere Ekle",
                            systemImage: vehicle.isFavourite ? "heart.fill" : "heart"
                        )
                        .font(Theme.Typography.callout)
                        .foregroundStyle(
                            vehicle.isFavourite
                                ? Theme.Colours.danger
                                : Theme.Colours.textPrimary
                        )
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, Theme.Spacing.xs)
                        .background(Theme.Colours.surfaceElevated, in: Capsule())
                    }
                    .buttonStyle(.plain)

                    NavigationLink {
                        CopilotView(api: api, vehicle: vehicle, latestScore: model.latestScore)
                    } label: {
                        Label("AI Copilot", systemImage: "sparkles")
                            .font(Theme.Typography.callout)
                            .foregroundStyle(Theme.Colours.textOnBrand)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, Theme.Spacing.xs)
                            .background(Theme.Colours.brandGradient, in: Capsule())
                    }
                }
            }
        }
    }

    private var tabPicker: some View {
        HStack(spacing: 0) {
            ForEach(Tab.allCases) { candidate in
                Button {
                    withAnimation(Theme.Motion.quick) { tab = candidate }
                } label: {
                    Text(candidate.title)
                        .font(Theme.Typography.callout)
                        .foregroundStyle(
                            tab == candidate
                                ? Theme.Colours.brand
                                : Theme.Colours.textSecondary
                        )
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, Theme.Spacing.xs)
                        .overlay(alignment: .bottom) {
                            Rectangle()
                                .fill(tab == candidate ? Theme.Colours.brand : .clear)
                                .frame(height: 2)
                        }
                }
                .buttonStyle(.plain)
            }
        }
        .background(Theme.Colours.surface)
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous))
    }
}

// MARK: - Overview

private struct OverviewTab: View {
    let vehicle: Vehicle
    let model: VehicleDetailModel
    let api: any TruvixAPI

    var body: some View {
        VStack(spacing: Theme.Spacing.md) {
            Card {
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    SpecRow(label: "Marka / Model", value: "\(vehicle.make) \(vehicle.model)")
                    if let variant = vehicle.variant {
                        SpecRow(label: "Donanım", value: variant)
                    }
                    SpecRow(label: "Model yılı", value: String(vehicle.modelYear))
                    SpecRow(
                        label: "Kilometre",
                        value: (NumberFormatter.turkishInteger
                            .string(from: NSNumber(value: vehicle.mileageKm))
                            ?? "\(vehicle.mileageKm)") + " km"
                    )
                    SpecRow(label: "Yakıt", value: vehicle.fuelType.displayName)
                    SpecRow(label: "Vites", value: vehicle.transmission.displayName)
                    if let body = vehicle.bodyType {
                        SpecRow(label: "Kasa", value: body.displayName)
                    }
                    if let city = vehicle.city {
                        SpecRow(label: "Şehir", value: city)
                    }
                    if let plate = vehicle.plate {
                        SpecRow(label: "Plaka", value: plate)
                    }
                    SpecRow(label: "Şasi no", value: vehicle.vin == nil ? "Girilmedi" : "Girildi")
                }
            }

            if model.analyses.isEmpty {
                Card {
                    Text("Bu araç için henüz analiz yapılmadı.")
                        .font(Theme.Typography.callout)
                        .foregroundStyle(Theme.Colours.textSecondary)
                }
            } else {
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    SectionHeader("Analizler")
                    ForEach(model.analyses) { analysis in
                        NavigationLink {
                            AnalysisReportView(analysisID: analysis.id, api: api)
                        } label: {
                            AnalysisListRow(analysis: analysis)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }
}

private struct SpecRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colours.textSecondary)
            Spacer(minLength: Theme.Spacing.sm)
            Text(value)
                .font(Theme.Typography.callout)
                .foregroundStyle(Theme.Colours.textPrimary)
        }
    }
}

private struct AnalysisListRow: View {
    let analysis: AnalysisSummary

    var body: some View {
        Card(padding: Theme.Spacing.sm) {
            HStack(spacing: Theme.Spacing.sm) {
                if let score = analysis.trustScore {
                    ScoreBadge(score: score, size: 40)
                } else {
                    StatusChip(status: analysis.status)
                }

                VStack(alignment: .leading, spacing: 2) {
                    Text(analysis.riskLevel?.displayName ?? analysis.status.displayName)
                        .font(Theme.Typography.callout)
                        .foregroundStyle(Theme.Colours.textPrimary)
                    Text(
                        analysis.createdAt
                            .formatted(.dateTime.day().month(.abbreviated).year().hour().minute())
                    )
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colours.textSecondary)
                }

                Spacer(minLength: 0)

                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.Colours.textSecondary)
            }
        }
    }
}

// MARK: - Chart

private struct ChartTab: View {
    let model: VehicleDetailModel
    let currency: Currency

    var body: some View {
        VStack(spacing: Theme.Spacing.md) {
            windowPicker

            if let history = model.history, history.isPlottable {
                Card {
                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        summaryRow(history)
                        chart(history)
                    }
                }
            } else {
                Card {
                    VStack(spacing: Theme.Spacing.xs) {
                        Image(systemName: "chart.xyaxis.line")
                            .font(.system(size: 30, weight: .light))
                            .foregroundStyle(Theme.Colours.textSecondary)
                        Text("Grafik için en az iki fiyat kaydı gerekiyor.")
                            .font(Theme.Typography.callout)
                            .foregroundStyle(Theme.Colours.textSecondary)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, Theme.Spacing.lg)
                }
            }
        }
    }

    private var windowPicker: some View {
        HStack(spacing: Theme.Spacing.xs) {
            ForEach(PriceWindow.allCases) { candidate in
                Button {
                    model.window = candidate
                } label: {
                    Text(candidate.title)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(
                            model.window == candidate
                                ? Theme.Colours.textOnBrand
                                : Theme.Colours.textSecondary
                        )
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, Theme.Spacing.xs)
                        .background {
                            if model.window == candidate {
                                Capsule().fill(Theme.Colours.brandGradient)
                            }
                        }
                }
                .buttonStyle(.plain)
            }
        }
        .padding(Theme.Spacing.xxs)
        .background(Theme.Colours.surface, in: Capsule())
    }

    private func summaryRow(_ history: PriceHistory) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("Ortalama Fiyat")
                    .font(Theme.Typography.label)
                    .foregroundStyle(Theme.Colours.textSecondary)
                Text(history.averagePrice?.formatted(currency) ?? "—")
                    .font(Theme.Typography.headline)
                    .foregroundStyle(Theme.Colours.textPrimary)
            }

            Spacer()

            if let trend = history.trend, let change = trend.formattedChange(currency) {
                VStack(alignment: .trailing, spacing: 2) {
                    Text("Değişim")
                        .font(Theme.Typography.label)
                        .foregroundStyle(Theme.Colours.textSecondary)
                    HStack(spacing: 3) {
                        Text(change)
                        if let percentage = trend.percentageChange {
                            Text("(\(percentage.formatted))")
                                .opacity(0.85)
                        }
                    }
                    .font(Theme.Typography.callout)
                    .foregroundStyle(
                        trend.hasDropped ? Theme.Colours.brand : Theme.Colours.danger
                    )
                }
            }
        }
    }

    private func chart(_ history: PriceHistory) -> some View {
        Chart(history.points) { point in
            AreaMark(
                x: .value("Tarih", point.observedOn.date),
                y: .value("Fiyat", point.price.plottableAmount)
            )
            .foregroundStyle(
                LinearGradient(
                    colors: [Theme.Colours.brand.opacity(0.35), .clear],
                    startPoint: .top,
                    endPoint: .bottom
                )
            )
            .interpolationMethod(.monotone)

            LineMark(
                x: .value("Tarih", point.observedOn.date),
                y: .value("Fiyat", point.price.plottableAmount)
            )
            .foregroundStyle(Theme.Colours.brand)
            .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round))
            .interpolationMethod(.monotone)
        }
        // The axis starts at the series' own range rather than at zero: a car
        // priced near a million with a 25.000 move would otherwise draw as a
        // flat line and hide exactly what the chart exists to show.
        .chartYScale(domain: verticalDomain(history))
        .chartYAxis {
            AxisMarks(position: .leading) { value in
                AxisGridLine().foregroundStyle(Theme.Colours.border)
                AxisValueLabel {
                    if let amount = value.as(Double.self) {
                        Text(Money(Decimal(amount)).formatted(currency))
                            .font(.system(size: 10))
                            .foregroundStyle(Theme.Colours.textSecondary)
                    }
                }
            }
        }
        .chartXAxis {
            AxisMarks { value in
                AxisGridLine().foregroundStyle(Theme.Colours.border.opacity(0.5))
                AxisValueLabel(format: .dateTime.day().month(.abbreviated))
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.Colours.textSecondary)
            }
        }
        .frame(height: 200)
        .accessibilityLabel("Fiyat grafiği, son \(history.windowDays) gün")
    }

    /// Pad the series' range slightly so the line never touches the frame.
    private func verticalDomain(_ history: PriceHistory) -> ClosedRange<Double> {
        let values = history.points.map(\.price.plottableAmount)
        guard let lowest = values.min(), let highest = values.max() else {
            return 0...1
        }
        guard highest > lowest else {
            let padding = max(highest * 0.05, 1)
            return (lowest - padding)...(highest + padding)
        }
        let padding = (highest - lowest) * 0.15
        return (lowest - padding)...(highest + padding)
    }
}

// MARK: - History

private struct HistoryTab: View {
    let model: VehicleDetailModel
    let currency: Currency

    var body: some View {
        Card {
            if let points = model.history?.points, !points.isEmpty {
                VStack(spacing: Theme.Spacing.sm) {
                    ForEach(Array(points.reversed().enumerated()), id: \.element.id) { index, point in
                        HStack {
                            Text(point.observedOn.longLabel)
                                .font(Theme.Typography.callout)
                                .foregroundStyle(Theme.Colours.textPrimary)

                            Spacer()

                            Text(point.price.formatted(currency))
                                .font(Theme.Typography.callout)
                                .foregroundStyle(Theme.Colours.textPrimary)

                            if let change = change(at: index, in: Array(points.reversed())) {
                                Text(change.formattedSigned(currency))
                                    .font(Theme.Typography.caption)
                                    .foregroundStyle(
                                        change.isNegative
                                            ? Theme.Colours.brand
                                            : Theme.Colours.danger
                                    )
                            }
                        }
                        if index < points.count - 1 {
                            Divider().overlay(Theme.Colours.border)
                        }
                    }
                }
            } else {
                Text("Henüz fiyat kaydı yok.")
                    .font(Theme.Typography.callout)
                    .foregroundStyle(Theme.Colours.textSecondary)
            }
        }
    }

    /// The move from the previous observation, which is the next entry in a
    /// newest-first list.
    private func change(at index: Int, in points: [PriceHistoryPoint]) -> Money? {
        guard index + 1 < points.count else { return nil }
        return Money(points[index].price.amount - points[index + 1].price.amount)
    }
}
