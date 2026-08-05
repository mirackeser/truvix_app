import SwiftUI

@main
struct TruvixApp: App {
    @State private var session: SessionStore
    private let auth: any AuthServicing
    private let api: any TruvixAPI

    init() {
        let client = APIClient()
        let authService = AuthService(client: client)
        auth = authService
        api = LiveTruvixAPI(client: client)
        _session = State(wrappedValue: SessionStore(client: client, auth: authService))
    }

    var body: some Scene {
        WindowGroup {
            RootView(auth: auth, api: api)
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
    let api: any TruvixAPI

    /// Watches the App Store for the whole time somebody is signed in.
    ///
    /// Renewals, purchases approved later and purchases made on another device
    /// arrive without the paywall being open, and each one has to reach the
    /// backend to be verified. Owning the listener here rather than in the
    /// paywall is what makes that happen.
    @State private var subscriptions: SubscriptionModel?

    var body: some View {
        Group {
            switch session.phase {
            case .restoring:
                SplashView()
            case .signedOut:
                if hasSeenOnboarding || LaunchOverrides.skipsOnboarding {
                    SignInView(auth: auth)
                } else {
                    OnboardingView { hasSeenOnboarding = true }
                }
            case .signedIn:
                AppShell(api: api)
            }
        }
        .animation(Theme.Motion.standard, value: session.phase)
        .task {
            await session.restore()
        }
        .onChange(of: session.phase.user?.id) { _, userID in
            guard userID != nil else {
                // Signing out ends the listener: a transaction verified against
                // whoever signs in next would attach the purchase to the wrong
                // account.
                subscriptions = nil
                return
            }
            let model = SubscriptionModel(api: api)
            model.startListeningForStoreUpdates()
            subscriptions = model
        }
    }
}
