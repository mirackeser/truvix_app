import SwiftUI

/// What premium unlocks, in the order it matters to somebody deciding.
private struct PremiumBenefit: Identifiable {
    let id = UUID()
    let symbol: String
    let title: String
    let detail: String
}

private let benefits: [PremiumBenefit] = [
    PremiumBenefit(
        symbol: "sparkles",
        title: "Günde 100 analiz",
        detail: "Ücretsiz planda 5 analiz hakkın var."
    ),
    PremiumBenefit(
        symbol: "car.2.fill",
        title: "500 araçlık garaj",
        detail: "Karşılaştırmak istediğin her ilanı sakla."
    ),
    PremiumBenefit(
        symbol: "bubble.left.and.text.bubble.right.fill",
        title: "Sınırsız Copilot",
        detail: "İlanla ilgili aklına takılan her şeyi sor."
    ),
    PremiumBenefit(
        symbol: "chart.line.uptrend.xyaxis",
        title: "Fiyat takibi",
        detail: "Takip ettiğin araç ucuzladığında haber ver."
    )
]

/// The paywall: what premium costs and what it gives.
struct PaywallView: View {
    @State private var model: SubscriptionModel
    @Environment(\.dismiss) private var dismiss
    @State private var selectedProductID: String?

    init(api: any TruvixAPI, store: any StoreClient = LiveStoreClient()) {
        _model = State(wrappedValue: SubscriptionModel(api: api, store: store))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                    banner

                    VStack(alignment: .leading, spacing: Theme.Spacing.md) {
                        ForEach(benefits) { benefit in
                            benefitRow(benefit)
                        }
                    }

                    plans

                    footnote
                }
                .padding(Theme.Spacing.md)
            }
            .screenBackground()
            .navigationTitle("Truvix Premium")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Kapat") { dismiss() }
                }
                ToolbarItem(placement: .primaryAction) {
                    Button("Geri Yükle") {
                        Task { await model.restore() }
                    }
                    .disabled(model.isWorking)
                }
            }
        }
        .task {
            await model.load()
        }
        .onChange(of: model.didBecomePremium) { _, becamePremium in
            if becamePremium { dismiss() }
        }
        .alert(
            "Abonelik",
            isPresented: Binding(
                get: { model.alert != nil },
                set: { if !$0 { model.alert = nil } }
            )
        ) {
            Button("Tamam", role: .cancel) { model.alert = nil }
        } message: {
            Text(model.alert ?? "")
        }
    }

    // MARK: - Sections

    private var banner: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            if let entitlement = model.subscription.currentEntitlement {
                Text("Aboneliğin aktif")
                    .font(Theme.Typography.title)
                    .foregroundStyle(Theme.Colours.textPrimary)
                if let explanation = entitlement.status.explanation {
                    Text(explanation)
                        .font(Theme.Typography.body)
                        .foregroundStyle(Theme.Colours.textSecondary)
                } else if let expiry = entitlement.expiresAt {
                    Text("Yenileme: \(expiry.formatted(date: .abbreviated, time: .omitted))")
                        .font(Theme.Typography.body)
                        .foregroundStyle(Theme.Colours.textSecondary)
                }
            } else {
                Text("Aracı almadan önce emin ol")
                    .font(Theme.Typography.display)
                    .foregroundStyle(Theme.Colours.textPrimary)
                Text("Premium, analiz ve takip sınırlarını kaldırır.")
                    .font(Theme.Typography.body)
                    .foregroundStyle(Theme.Colours.textSecondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func benefitRow(_ benefit: PremiumBenefit) -> some View {
        AdaptiveStack(horizontalSpacing: Theme.Spacing.sm) {
            Image(systemName: benefit.symbol)
                .font(Theme.Typography.headline)
                .foregroundStyle(Theme.Colours.brand)
                .frame(width: 28)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                Text(benefit.title)
                    .font(Theme.Typography.headline)
                    .foregroundStyle(Theme.Colours.textPrimary)
                Text(benefit.detail)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colours.textSecondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private var plans: some View {
        switch model.state {
        case .idle, .loading:
            ProgressView()
                .frame(maxWidth: .infinity)
                .padding(.vertical, Theme.Spacing.lg)

        case let .failed(message):
            VStack(spacing: Theme.Spacing.sm) {
                ErrorBanner(message: message)
                Button("Tekrar dene") {
                    Task { await model.load() }
                }
                .buttonStyle(SecondaryButtonStyle())
            }

        case let .loaded(products):
            VStack(spacing: Theme.Spacing.sm) {
                ForEach(products) { product in
                    planCard(product)
                }
            }
        }
    }

    private func planCard(_ product: StoreProduct) -> some View {
        Button {
            selectedProductID = product.id
            Task { await model.purchase(product) }
        } label: {
            AdaptiveStack(horizontalSpacing: Theme.Spacing.sm) {
                VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                    Text(product.displayName)
                        .font(Theme.Typography.headline)
                        .foregroundStyle(Theme.Colours.textPrimary)
                    Text(product.description)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colours.textSecondary)
                        .multilineTextAlignment(.leading)
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                if model.isWorking, selectedProductID == product.id {
                    ProgressView()
                } else {
                    Text(product.priceSummary)
                        .font(Theme.Typography.headline)
                        .foregroundStyle(Theme.Colours.brand)
                }
            }
            .padding(Theme.Spacing.md)
            .background(Theme.Colours.surfaceElevated)
            .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.medium))
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.medium)
                    .stroke(Theme.Colours.border, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .disabled(model.isWorking)
        .accessibilityLabel("\(product.displayName), \(product.priceSummary)")
        .accessibilityHint("Aboneliği başlatır")
    }

    private var footnote: some View {
        Text(
            """
            Abonelik, iptal edilmediği sürece dönem sonunda otomatik yenilenir. \
            Yönetim ve iptal işlemleri Apple Kimliği ayarlarından yapılır.
            """
        )
        .font(Theme.Typography.caption)
        .foregroundStyle(Theme.Colours.textSecondary)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
