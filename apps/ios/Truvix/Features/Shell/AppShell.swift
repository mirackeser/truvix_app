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
    /// Set when a notification asks for a vehicle, and consumed by the garage.
    @State private var requestedVehicleID: UUID?

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    /// Reserved space under the content, matching the bar's two layouts.
    private var barHeight: CGFloat {
        dynamicTypeSize.isAccessibilitySize ? 62 : 76
    }

    var body: some View {
        ZStack(alignment: .bottom) {
            Group {
                switch tab {
                case .home:
                    DashboardView(
                        api: api,
                        onStartAnalysis: { isPresentingNewAnalysis = true },
                        onOpenNotifications: { tab = .notifications },
                        onOpenProfile: { tab = .profile }
                    )
                case .garage:
                    GarageView(
                        api: api,
                        openingVehicleID: $requestedVehicleID
                    ) { isPresentingNewAnalysis = true }
                case .notifications:
                    NotificationsView(api: api) { vehicleID in
                        // Switching tab first means the garage's stack is on
                        // screen by the time it consumes the request.
                        requestedVehicleID = vehicleID
                        tab = .garage
                    }
                case .profile:
                    ProfileView(api: api)
                }
            }
            // The content extends under the bar so scrolling feels continuous;
            // the inset keeps the last row reachable above it.
            .safeAreaInset(edge: .bottom) {
                Color.clear.frame(height: barHeight)
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
///
/// At accessibility text sizes the labels are dropped and only the icons
/// remain. Letting them scale freely wraps each label over three lines, which
/// pushes the bar to half the screen and overlaps the centre action — the
/// navigation becomes unusable at precisely the setting meant to make the app
/// easier to use. Each item keeps its accessibility label, so nothing is lost
/// to VoiceOver, and the icons themselves grow.
private struct TabBar: View {
    @Binding var selection: AppTab
    let onCentreAction: () -> Void

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var showsLabels: Bool { !dynamicTypeSize.isAccessibilitySize }

    var body: some View {
        HStack(spacing: 0) {
            item(.home)
            item(.garage)

            Button(action: onCentreAction) {
                Image(systemName: "plus")
                    .font(Theme.Typography.title)
                    .foregroundStyle(Theme.Colours.textOnBrand)
                    .frame(width: 54, height: 54)
                    .background(Theme.Colours.brandGradient, in: Circle())
                    .shadow(color: Theme.Colours.brand.opacity(0.45), radius: 12, y: 4)
            }
            .frame(maxWidth: .infinity)
            .offset(y: showsLabels ? -14 : 0)
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
                .font(Theme.Typography.headline)

                if showsLabels {
                    Text(candidate.title)
                        .font(Theme.Typography.micro)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                }
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
            .accessibilityHidden(true)
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
