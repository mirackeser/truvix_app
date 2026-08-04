import SwiftUI

/// What a screen currently has to show.
///
/// Modelling the four outcomes as one value makes it impossible to render a
/// spinner and an error at the same time, or to show an empty list while a
/// first load is still running — the two failures that make loading states
/// look broken.
enum LoadState<Value: Sendable>: Sendable {
    case idle
    case loading
    case loaded(Value)
    case failed(APIError)

    var value: Value? {
        if case let .loaded(value) = self { return value }
        return nil
    }

    var isLoading: Bool {
        if case .loading = self { return true }
        return false
    }
}

/// The placeholder shown while a screen's first load runs.
struct LoadingState: View {
    var message = "Yükleniyor…"

    var body: some View {
        VStack(spacing: Theme.Spacing.md) {
            ProgressView()
                .progressViewStyle(.circular)
                .tint(Theme.Colours.brand)
            Text(message)
                .font(Theme.Typography.callout)
                .foregroundStyle(Theme.Colours.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .combine)
    }
}

/// The state shown when a load fails.
///
/// A retry is offered only for failures where retrying could plausibly work;
/// offering it after a 409 would invite the user to repeat something that can
/// never succeed.
struct FailureState: View {
    let error: APIError
    var retry: (() -> Void)?

    var body: some View {
        VStack(spacing: Theme.Spacing.md) {
            Image(systemName: symbolName)
                .font(.system(size: 44, weight: .light))
                .foregroundStyle(Theme.Colours.textSecondary)

            Text(error.localizedDescription)
                .font(Theme.Typography.body)
                .foregroundStyle(Theme.Colours.textSecondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)

            if error.isRetryable, let retry {
                Button("Tekrar Dene", action: retry)
                    .buttonStyle(SecondaryButtonStyle())
                    .frame(maxWidth: 200)
            }
        }
        .padding(Theme.Spacing.lg)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var symbolName: String {
        switch error {
        case .offline: "wifi.slash"
        case .timedOut: "clock.badge.exclamationmark"
        case .unauthorised: "lock"
        default: "exclamationmark.triangle"
        }
    }
}

/// The state shown when a load succeeds but there is nothing yet.
struct EmptyState<Action: View>: View {
    let symbolName: String
    let title: String
    let message: String
    @ViewBuilder var action: Action

    var body: some View {
        VStack(spacing: Theme.Spacing.md) {
            ZStack {
                Circle()
                    .fill(Theme.Colours.brand.opacity(0.12))
                    .frame(width: 88, height: 88)
                Image(systemName: symbolName)
                    .font(.system(size: 34, weight: .light))
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

            action
                .padding(.top, Theme.Spacing.xs)
        }
        .padding(Theme.Spacing.lg)
        .frame(maxWidth: .infinity)
    }
}

extension EmptyState where Action == EmptyView {
    init(symbolName: String, title: String, message: String) {
        self.init(symbolName: symbolName, title: title, message: message) { EmptyView() }
    }
}
