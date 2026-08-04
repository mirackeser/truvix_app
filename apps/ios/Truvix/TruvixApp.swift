import SwiftUI

@main
struct TruvixApp: App {
    @State private var session: SessionStore
    private let auth: any AuthServicing

    init() {
        let client = APIClient()
        let authService = AuthService(client: client)
        auth = authService
        _session = State(wrappedValue: SessionStore(client: client, auth: authService))
    }

    var body: some Scene {
        WindowGroup {
            RootView(auth: auth)
                .environment(session)
                .preferredColorScheme(.dark)
        }
    }
}

/// Chooses what to show based on the session, and nothing else.
///
/// Every transition in the app's outermost layer follows from one observed
/// value, so there is no path where the UI and the session can disagree about
/// whether somebody is signed in.
struct RootView: View {
    @Environment(SessionStore.self) private var session
    @AppStorage("hasSeenOnboarding") private var hasSeenOnboarding = false

    let auth: any AuthServicing

    var body: some View {
        Group {
            switch session.phase {
            case .restoring:
                SplashView()
            case .signedOut:
                if hasSeenOnboarding {
                    SignInView(auth: auth)
                } else {
                    OnboardingView { hasSeenOnboarding = true }
                }
            case let .signedIn(user):
                SignedInPlaceholderView(user: user)
            }
        }
        .animation(Theme.Motion.standard, value: session.phase)
        .task {
            await session.restore()
        }
    }
}

/// Landing screen for an authenticated session.
///
/// The home screen replaces this in the next slice; it exists so the sign-in
/// flow can be exercised end to end today rather than dead-ending.
struct SignedInPlaceholderView: View {
    @Environment(SessionStore.self) private var session

    let user: UserProfile

    var body: some View {
        VStack(spacing: Theme.Spacing.lg) {
            Spacer()

            ScoreBadge(score: 91, size: 88)

            VStack(spacing: Theme.Spacing.xs) {
                Text("Merhaba, \(user.firstName) 👋")
                    .font(Theme.Typography.display)
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

            Spacer()

            Button("Çıkış Yap") {
                Task { await session.signOut() }
            }
            .buttonStyle(SecondaryButtonStyle())
            .padding(.horizontal, Theme.Spacing.lg)
            .padding(.bottom, Theme.Spacing.lg)
        }
        .screenBackground()
    }
}
