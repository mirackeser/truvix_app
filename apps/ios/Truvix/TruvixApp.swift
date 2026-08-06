import SwiftUI

@main
struct TruvixApp: App {
    @UIApplicationDelegateAdaptor(PushAppDelegate.self) private var appDelegate
    @State private var session: SessionStore
    @State private var push: PushRegistrar
    private let auth: any AuthServicing
    private let api: any TruvixAPI

    init() {
        let client = APIClient()
        let authService = AuthService(client: client)
        auth = authService
        api = LiveTruvixAPI(client: client)
        _session = State(wrappedValue: SessionStore(client: client, auth: authService))

        let registrar = PushRegistrar(auth: authService)
        _push = State(wrappedValue: registrar)
        // The device token arrives through the application delegate, which iOS
        // creates itself, so the registrar has to be reachable from there.
        PushAppDelegate.registrar = registrar
    }

    var body: some Scene {
        WindowGroup {
            RootView(auth: auth, api: api)
                .environment(session)
                .environment(push)
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
    @Environment(PushRegistrar.self) private var push
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
                // Stop notifications before the session goes: the next person
                // to use this handset must not receive somebody else's alerts.
                Task { await push.unregister() }
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
