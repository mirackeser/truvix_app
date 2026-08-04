import SwiftUI

// MARK: - Buttons

/// The filled green button used for the primary action on every screen.
struct PrimaryButtonStyle: ButtonStyle {
    var isLoading = false

    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: Theme.Spacing.xs) {
            if isLoading {
                ProgressView()
                    .progressViewStyle(.circular)
                    .tint(Theme.Colours.textOnBrand)
            }
            configuration.label
        }
        .font(Theme.Typography.headline)
        .foregroundStyle(Theme.Colours.textOnBrand)
        .frame(maxWidth: .infinity)
        .frame(height: 54)
        .background(Theme.Colours.brandGradient)
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.medium, style: .continuous))
        // Pressed and disabled states are dimmed rather than resized, so a tap
        // near the edge cannot shrink the target out from under the finger.
        .opacity(configuration.isPressed ? 0.85 : 1)
        .animation(Theme.Motion.quick, value: configuration.isPressed)
    }
}

/// The outlined button used for secondary actions beside a primary one.
struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.Typography.headline)
            .foregroundStyle(Theme.Colours.textPrimary)
            .frame(maxWidth: .infinity)
            .frame(height: 54)
            .background(Theme.Colours.surface)
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.medium, style: .continuous)
                    .stroke(Theme.Colours.border, lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.medium, style: .continuous))
            .opacity(configuration.isPressed ? 0.7 : 1)
            .animation(Theme.Motion.quick, value: configuration.isPressed)
    }
}

// MARK: - Containers

/// The rounded dark card that groups related content on every screen.
struct Card<Content: View>: View {
    var padding: CGFloat = Theme.Spacing.md
    @ViewBuilder var content: Content

    var body: some View {
        content
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.Colours.surface)
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.large, style: .continuous)
                    .stroke(Theme.Colours.border, lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.large, style: .continuous))
    }
}

/// A section heading with an optional trailing action, as used above each
/// horizontal carousel on the home screen.
struct SectionHeader<Trailing: View>: View {
    let title: String
    @ViewBuilder var trailing: Trailing

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title)
                .font(Theme.Typography.label)
                .kerning(0.8)
                .foregroundStyle(Theme.Colours.textSecondary)
                .textCase(.uppercase)
            Spacer(minLength: Theme.Spacing.sm)
            trailing
        }
    }
}

extension SectionHeader where Trailing == EmptyView {
    init(_ title: String) {
        self.init(title: title) { EmptyView() }
    }
}

// MARK: - Fields

/// The dark rounded text field used across the sign-in and analysis forms.
struct TruvixTextField: View {
    let title: String
    let systemImage: String
    @Binding var text: String
    var isSecure = false
    var keyboard: UIKeyboardType = .default
    var contentType: UITextContentType?
    var submitLabel: SubmitLabel = .next
    var onSubmit: () -> Void = {}

    @State private var isRevealed = false
    @FocusState private var isFocused: Bool

    var body: some View {
        HStack(spacing: Theme.Spacing.sm) {
            Image(systemName: systemImage)
                .foregroundStyle(Theme.Colours.textSecondary)
                .frame(width: 20)

            Group {
                if isSecure && !isRevealed {
                    SecureField(title, text: $text)
                } else {
                    TextField(title, text: $text)
                }
            }
            .font(Theme.Typography.body)
            .foregroundStyle(Theme.Colours.textPrimary)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .keyboardType(keyboard)
            .textContentType(contentType)
            .submitLabel(submitLabel)
            .focused($isFocused)
            .onSubmit(onSubmit)

            if isSecure {
                Button {
                    isRevealed.toggle()
                } label: {
                    Image(systemName: isRevealed ? "eye.slash" : "eye")
                        .foregroundStyle(Theme.Colours.textSecondary)
                }
                .accessibilityLabel(isRevealed ? "Şifreyi gizle" : "Şifreyi göster")
            }
        }
        .padding(.horizontal, Theme.Spacing.md)
        .frame(height: 54)
        .background(Theme.Colours.surfaceElevated)
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.medium, style: .continuous)
                .stroke(isFocused ? Theme.Colours.brand : Theme.Colours.border, lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.medium, style: .continuous))
        .animation(Theme.Motion.quick, value: isFocused)
    }
}

// MARK: - Feedback

/// An inline error banner. Errors are shown in place rather than in an alert,
/// so the field that caused them stays visible while it is corrected.
struct ErrorBanner: View {
    let message: String

    var body: some View {
        HStack(alignment: .top, spacing: Theme.Spacing.xs) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(Theme.Colours.danger)
            Text(message)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colours.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(Theme.Spacing.sm)
        .background(Theme.Colours.danger.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous))
        .accessibilityElement(children: .combine)
    }
}

/// The circular trust score badge that appears on every vehicle card.
struct ScoreBadge: View {
    let score: Int
    var size: CGFloat = 44

    private var tint: Color {
        switch score {
        case 80...: Theme.Colours.brand
        case 60..<80: Theme.Colours.warning
        default: Theme.Colours.danger
        }
    }

    var body: some View {
        ZStack {
            Circle()
                .stroke(tint.opacity(0.25), lineWidth: 3)
            Circle()
                .trim(from: 0, to: CGFloat(score) / 100)
                .stroke(tint, style: StrokeStyle(lineWidth: 3, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Text("\(score)")
                .font(.system(size: size * 0.36, weight: .bold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(Theme.Colours.textPrimary)
        }
        .frame(width: size, height: size)
        .accessibilityElement()
        .accessibilityLabel("Güven skoru \(score) / 100")
    }
}

// MARK: - Layout helpers

extension View {
    /// Apply the app's standard screen background and horizontal padding.
    func screenBackground() -> some View {
        self
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Theme.Colours.background.ignoresSafeArea())
    }
}
