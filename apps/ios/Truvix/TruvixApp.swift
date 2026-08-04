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
    }
}
