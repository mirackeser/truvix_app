import SwiftUI

/// The five destinations in the bottom bar, in the order the design lists them.
enum AppTab: Int, CaseIterable, Identifiable, Sendable {
    case home
    case garage
    case notifications
    case profile

    var id: Int { rawValue }

    var title: String {
        switch self {
        case .home: "Ana Sayfa"
        case .garage: "Garajım"
        case .notifications: "Bildirimler"
        case .profile: "Profil"
        }
    }

    var symbolName: String {
        switch self {
        case .home: "house"
        case .garage: "car.2"
        case .notifications: "bell"
        case .profile: "person"
        }
    }

    var filledSymbolName: String {
        symbolName + ".fill"
    }
}

/// The signed-in shell: four tabs around a raised central action.
///
/// The bar is drawn rather than using `TabView`'s, because the design's centre
/// action sits above the bar and overlaps it — something the system bar has no
/// way to express.
struct AppShell: View {
    let api: any TruvixAPI

    @State private var tab: AppTab = LaunchOverrides.initialTab ?? .home
    @State private var isPresentingNewAnalysis = LaunchOverrides.opensNewAnalysis

    var body: some View {
        ZStack(alignment: .bottom) {
            Group {
                switch tab {
                case .home:
                    DashboardView(
                        api: api,
                        onStartAnalysis: { isPresentingNewAnalysis = true },
                        onOpenNotifications: { tab = .notifications }
                    )
                case .garage:
                    GarageView(api: api) { isPresentingNewAnalysis = true }
                case .notifications:
                    NotificationsView(api: api)
                case .profile:
                    ProfileView()
                }
            }
            // The content extends under the bar so scrolling feels continuous;
            // the inset keeps the last row reachable above it.
            .safeAreaInset(edge: .bottom) {
                Color.clear.frame(height: 76)
            }

            TabBar(selection: $tab) { isPresentingNewAnalysis = true }
        }
        .screenBackground()
        .sheet(isPresented: $isPresentingNewAnalysis) {
            NewAnalysisView(api: api)
        }
    }
}

/// The custom bottom bar.
private struct TabBar: View {
    @Binding var selection: AppTab
    let onCentreAction: () -> Void

    var body: some View {
        HStack(spacing: 0) {
            item(.home)
            item(.garage)

            Button(action: onCentreAction) {
                Image(systemName: "plus")
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundStyle(Theme.Colours.textOnBrand)
                    .frame(width: 54, height: 54)
                    .background(Theme.Colours.brandGradient, in: Circle())
                    .shadow(color: Theme.Colours.brand.opacity(0.45), radius: 12, y: 4)
            }
            .frame(maxWidth: .infinity)
            .offset(y: -14)
            .accessibilityLabel("Yeni analiz başlat")

            item(.notifications)
            item(.profile)
        }
        .padding(.horizontal, Theme.Spacing.xs)
        .padding(.top, Theme.Spacing.xs)
        .padding(.bottom, Theme.Spacing.xxs)
        .background {
            // A material rather than a flat fill, so content scrolling beneath
            // stays faintly visible instead of vanishing at a hard edge.
            Rectangle()
                .fill(.ultraThinMaterial)
                .overlay(Theme.Colours.background.opacity(0.6))
                .overlay(alignment: .top) {
                    Rectangle()
                        .fill(Theme.Colours.border)
                        .frame(height: 1)
                }
                .ignoresSafeArea(edges: .bottom)
        }
    }

    private func item(_ candidate: AppTab) -> some View {
        Button {
            selection = candidate
        } label: {
            VStack(spacing: 3) {
                Image(
                    systemName: selection == candidate
                        ? candidate.filledSymbolName
                        : candidate.symbolName
                )
                .font(.system(size: 19, weight: .medium))
                Text(candidate.title)
                    .font(.system(size: 10, weight: .medium))
            }
            .foregroundStyle(
                selection == candidate ? Theme.Colours.brand : Theme.Colours.textSecondary
            )
            .frame(maxWidth: .infinity)
            .padding(.vertical, Theme.Spacing.xxs)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(candidate.title)
        .accessibilityAddTraits(selection == candidate ? [.isSelected] : [])
    }
}

/// A destination whose screen is not built yet.
///
/// Stating plainly that the section is on its way is more honest than a blank
/// screen, and it keeps the shell navigable while the remaining slices land.
struct ComingSoonView: View {
    let symbolName: String
    let title: String
    let message: String

    var body: some View {
        VStack(spacing: Theme.Spacing.md) {
            Spacer()
            ZStack {
                Circle()
                    .fill(Theme.Colours.brand.opacity(0.12))
                    .frame(width: 96, height: 96)
                Image(systemName: symbolName)
                    .font(.system(size: 38, weight: .light))
                    .foregroundStyle(Theme.Colours.brand)
            }
            Text(title)
                .font(Theme.Typography.title)
                .foregroundStyle(Theme.Colours.textPrimary)
            Text(message)
                .font(Theme.Typography.callout)
                .foregroundStyle(Theme.Colours.textSecondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            Spacer()
        }
        .padding(Theme.Spacing.lg)
        .screenBackground()
    }
}

/// The profile tab: the account and the way out of it.
struct ProfileView: View {
    @Environment(SessionStore.self) private var session

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: Theme.Spacing.lg) {
                    if let user = session.phase.user {
                        VStack(spacing: Theme.Spacing.xs) {
                            Text(user.firstName.prefix(1).uppercased())
                                .font(.system(size: 32, weight: .semibold))
                                .foregroundStyle(Theme.Colours.textOnBrand)
                                .frame(width: 84, height: 84)
                                .background(Theme.Colours.brandGradient, in: Circle())

                            Text(user.fullName)
                                .font(Theme.Typography.title)
                                .foregroundStyle(Theme.Colours.textPrimary)

                            Text(user.email)
                                .font(Theme.Typography.callout)
                                .foregroundStyle(Theme.Colours.textSecondary)

                            Text(user.subscriptionTier.displayName)
                                .font(Theme.Typography.label)
                                .foregroundStyle(Theme.Colours.brand)
                                .padding(.horizontal, Theme.Spacing.sm)
                                .padding(.vertical, Theme.Spacing.xxs)
                                .background(Theme.Colours.brand.opacity(0.14), in: Capsule())
                        }
                        .padding(.top, Theme.Spacing.lg)
                    }

                    Button("Çıkış Yap") {
                        Task { await session.signOut() }
                    }
                    .buttonStyle(SecondaryButtonStyle())
                }
                .padding(.horizontal, Theme.Spacing.md)
                .padding(.bottom, Theme.Spacing.xl)
            }
            .screenBackground()
            .navigationTitle("Profil")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}
