import Foundation

/// Launch-time overrides used to put the app into a known state.
///
/// These exist so a screen can be verified against real data without anybody
/// typing into a simulator — the same hook a UI test suite uses. The whole
/// type is compiled out of release builds, so there is no path in a shipped
/// app that reads credentials from anywhere but the person using it.
enum LaunchOverrides {

    #if DEBUG
    /// Credentials to sign in with automatically, if supplied.
    ///
    /// Launch arguments of the form `-truvixSignInEmail value` are surfaced by
    /// `UserDefaults`, so no argument parsing is needed.
    static var automaticSignIn: (email: String, password: String)? {
        let defaults = UserDefaults.standard
        guard let email = defaults.string(forKey: "truvixSignInEmail"),
              let password = defaults.string(forKey: "truvixSignInPassword"),
              !email.isEmpty, !password.isEmpty else {
            return nil
        }
        return (email, password)
    }

    /// Whether onboarding should be treated as already seen.
    static var skipsOnboarding: Bool {
        UserDefaults.standard.bool(forKey: "truvixSkipOnboarding")
    }

    /// The tab to open on, so any screen can be captured without tapping.
    static var initialTab: AppTab? {
        guard let raw = UserDefaults.standard.string(forKey: "truvixInitialTab") else {
            return nil
        }
        return AppTab.allCases.first { "\($0)" == raw }
    }

    /// Whether to open straight into the new-analysis sheet.
    static var opensNewAnalysis: Bool {
        UserDefaults.standard.bool(forKey: "truvixOpenNewAnalysis")
    }

    /// A vehicle to open on launch, so its detail screen is verifiable.
    static var initialVehicleID: UUID? {
        UserDefaults.standard.string(forKey: "truvixOpenVehicle").flatMap(UUID.init(uuidString:))
    }

    /// Whether to open straight into the paywall.
    static var opensPaywall: Bool {
        UserDefaults.standard.bool(forKey: "truvixOpenPaywall")
    }
    #else
    static var automaticSignIn: (email: String, password: String)? { nil }
    static var skipsOnboarding: Bool { false }
    static var initialTab: AppTab? { nil }
    static var opensNewAnalysis: Bool { false }
    static var initialVehicleID: UUID? { nil }
    static var opensPaywall: Bool { false }
    #endif
}
