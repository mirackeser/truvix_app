import Foundation
import Observation

/// Drives the home screen.
///
/// The view owns no loading logic of its own: it observes this and renders
/// whichever state it is in, which is what keeps "loading" and "failed" from
/// ever being on screen together.
@MainActor
@Observable
final class DashboardModel {
    private(set) var state: LoadState<Dashboard> = .idle

    private let api: any TruvixAPI

    init(api: any TruvixAPI) {
        self.api = api
    }

    /// Load the screen, showing a spinner only when there is nothing to show.
    ///
    /// A refresh that already has content keeps it on screen: replacing a
    /// populated dashboard with a spinner on every appearance makes the app
    /// feel like it is reloading from scratch each time.
    func load() async {
        if state.value == nil {
            state = .loading
        }

        do {
            state = .loaded(try await api.dashboard())
        } catch {
            // An existing dashboard survives a failed refresh; only a first
            // load has nothing better to show than the error.
            if state.value == nil {
                state = .failed(error)
            }
        }
    }

    /// Reload for a pull-to-refresh, where the control provides the feedback.
    func refresh() async {
        do {
            state = .loaded(try await api.dashboard())
        } catch {
            if state.value == nil {
                state = .failed(error)
            }
        }
    }
}
