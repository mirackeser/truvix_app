import SwiftUI

/// The three-page introduction shown before a first sign-in.
struct OnboardingView: View {
    let onFinish: () -> Void

    @State private var page = 0

    private let pages = OnboardingPage.all

    var body: some View {
        VStack(spacing: 0) {
            header

            TabView(selection: $page) {
                ForEach(Array(pages.enumerated()), id: \.element.id) { index, page in
                    OnboardingPageView(page: page)
                        .tag(index)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .never))

            footer
        }
        .screenBackground()
    }

    private var header: some View {
        HStack {
            Text("\(page + 1)/\(pages.count)")
                .font(Theme.Typography.label)
                .foregroundStyle(Theme.Colours.brand)
                .padding(.horizontal, Theme.Spacing.sm)
                .padding(.vertical, Theme.Spacing.xxs)
                .background(Theme.Colours.brand.opacity(0.14), in: Capsule())

            Spacer()

            Button("Atla", action: onFinish)
                .font(Theme.Typography.callout)
                .foregroundStyle(Theme.Colours.textSecondary)
                .padding(.horizontal, Theme.Spacing.md)
                .padding(.vertical, Theme.Spacing.xs)
                .background(Theme.Colours.surface, in: Capsule())
        }
        .padding(.horizontal, Theme.Spacing.lg)
        .padding(.top, Theme.Spacing.sm)
    }

    private var footer: some View {
        VStack(spacing: Theme.Spacing.md) {
            HStack(spacing: Theme.Spacing.xs) {
                ForEach(pages.indices, id: \.self) { index in
                    Capsule()
                        .fill(index == page ? Theme.Colours.brand : Theme.Colours.surfaceElevated)
                        .frame(width: index == page ? 22 : 8, height: 8)
                        .animation(Theme.Motion.spring, value: page)
                }
            }

            Button {
                if page < pages.count - 1 {
                    withAnimation(Theme.Motion.standard) { page += 1 }
                } else {
                    onFinish()
                }
            } label: {
                HStack {
                    Text(page < pages.count - 1 ? "Devam Et" : "Hadi Başlayalım")
                    Image(systemName: "arrow.right")
                }
            }
            .buttonStyle(PrimaryButtonStyle())
        }
        .padding(.horizontal, Theme.Spacing.lg)
        .padding(.bottom, Theme.Spacing.lg)
    }
}

/// One page of the introduction.
struct OnboardingPage: Identifiable, Sendable {
    let id: Int
    let title: String
    let highlight: String
    let titleSuffix: String
    let body: String
    let symbol: String
    let facts: [Fact]

    struct Fact: Identifiable, Sendable {
        let id = UUID()
        let caption: String
        let value: String
    }

    static let all: [OnboardingPage] = [
        OnboardingPage(
            id: 0,
            title: "Aracınızı\n",
            highlight: "Şansa",
            titleSuffix: " Bırakmayın",
            body: "Truvix; ilanı, fotoğrafları ve araç geçmişini analiz ederek "
                + "satın almadan önce riskleri ortaya çıkarır.",
            symbol: "car.side.arrowtriangle.up.arrowtriangle.down",
            facts: [
                .init(caption: "RİSK SKORU", value: "82/100"),
                .init(caption: "VERİ TARAMA", value: "%98"),
            ]
        ),
        OnboardingPage(
            id: 1,
            title: "",
            highlight: "Yapay Zekâ",
            titleSuffix: "\nBinlerce Veriyi Analiz Eder",
            body: "Fotoğraflar, fiyat, kilometre, ekspertiz raporu ve piyasa "
                + "verileri tek raporda birleşir.",
            symbol: "brain.head.profile",
            facts: [
                .init(caption: "GÜVEN SKORU", value: "84"),
                .init(caption: "KONTROL", value: "20+ kriter"),
            ]
        ),
        OnboardingPage(
            id: 2,
            title: "Karar Vermeden\nÖnce ",
            highlight: "Truvix",
            titleSuffix: "'e Sor",
            body: "Pazarlık önerileri, gerçek piyasa değeri ve satın alma "
                + "tavsiyesiyle doğru kararı ver.",
            symbol: "checkmark.seal",
            facts: [
                .init(caption: "PAZARLIK ÖNERİSİ", value: "830.000 ₺"),
                .init(caption: "DEĞERLENDİRME", value: "Öneriliyor"),
            ]
        ),
    ]
}

private struct OnboardingPageView: View {
    let page: OnboardingPage

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
            Spacer(minLength: Theme.Spacing.md)

            Group {
                Text(page.title)
                    .foregroundStyle(Theme.Colours.textPrimary)
                + Text(page.highlight)
                    .foregroundStyle(Theme.Colours.brand)
                + Text(page.titleSuffix)
                    .foregroundStyle(Theme.Colours.textPrimary)
            }
            .font(Theme.Typography.displayLarge)
            .fixedSize(horizontal: false, vertical: true)

            Text(page.body)
                .font(Theme.Typography.body)
                .foregroundStyle(Theme.Colours.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            illustration

            HStack(spacing: Theme.Spacing.sm) {
                ForEach(page.facts) { fact in
                    Card(padding: Theme.Spacing.sm) {
                        VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                            Text(fact.caption)
                                .font(Theme.Typography.label)
                                .foregroundStyle(Theme.Colours.textSecondary)
                            Text(fact.value)
                                .font(Theme.Typography.headline)
                                .foregroundStyle(Theme.Colours.brand)
                        }
                    }
                }
            }

            Spacer(minLength: 0)
        }
        .padding(.horizontal, Theme.Spacing.lg)
    }

    private var illustration: some View {
        ZStack {
            RoundedRectangle(cornerRadius: Theme.Radius.large, style: .continuous)
                .fill(
                    RadialGradient(
                        colors: [Theme.Colours.brand.opacity(0.28), .clear],
                        center: .center,
                        startRadius: 8,
                        endRadius: 190
                    )
                )
            Image(systemName: page.symbol)
                .font(.system(size: 74, weight: .light))
                .foregroundStyle(Theme.Colours.brandGradient)
        }
        .frame(maxWidth: .infinity)
        .frame(height: 210)
        .accessibilityHidden(true)
    }
}

#Preview {
    OnboardingView(onFinish: {})
}
