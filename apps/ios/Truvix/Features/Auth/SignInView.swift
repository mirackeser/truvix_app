import SwiftUI

/// Sign-in and registration, sharing one screen with a mode toggle.
///
/// Keeping both on one screen removes a navigation step from the most common
/// first-run path, and lets a typed email survive switching between them.
struct SignInView: View {
    enum Mode: String, CaseIterable, Identifiable {
        case signIn
        case register

        var id: Self { self }

        var title: String {
            switch self {
            case .signIn: "Giriş Yap"
            case .register: "Kayıt Ol"
            }
        }
    }

    @Environment(SessionStore.self) private var session

    let auth: any AuthServicing

    @State private var mode: Mode = .signIn
    @State private var fullName = ""
    @State private var email = ""
    @State private var password = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var isShowingForgotPassword = false

    var body: some View {
        ScrollView {
            VStack(spacing: Theme.Spacing.lg) {
                hero
                form
            }
            .padding(.horizontal, Theme.Spacing.lg)
            .padding(.bottom, Theme.Spacing.xl)
        }
        .scrollDismissesKeyboard(.interactively)
        .screenBackground()
        .sheet(isPresented: $isShowingForgotPassword) {
            ForgotPasswordSheet(auth: auth, initialEmail: email)
        }
    }

    // MARK: - Sections

    private var hero: some View {
        VStack(spacing: Theme.Spacing.sm) {
            Text("TRUVIX")
                .font(Theme.Typography.display.weight(.light))
                .kerning(8)
                .foregroundStyle(Theme.Colours.textPrimary)

            Text(mode == .signIn ? "Tekrar Hoş Geldin!" : "Hesabını Oluştur")
                .font(Theme.Typography.display)
                .foregroundStyle(Theme.Colours.textPrimary)

            Text(
                mode == .signIn
                    ? "Devam etmek için hesabına giriş yap."
                    : "Birkaç saniyede hesabını oluştur."
            )
            .font(Theme.Typography.callout)
            .foregroundStyle(Theme.Colours.textSecondary)
        }
        .multilineTextAlignment(.center)
        .padding(.top, Theme.Spacing.xl)
    }

    private var form: some View {
        Card(padding: Theme.Spacing.lg) {
            VStack(spacing: Theme.Spacing.md) {
                modePicker

                if mode == .register {
                    TruvixTextField(
                        title: "Ad Soyad",
                        systemImage: "person",
                        text: $fullName,
                        contentType: .name
                    )
                    .transition(.opacity.combined(with: .move(edge: .top)))
                }

                TruvixTextField(
                    title: "E-posta adresin",
                    systemImage: "envelope",
                    text: $email,
                    keyboard: .emailAddress,
                    contentType: .emailAddress
                )

                TruvixTextField(
                    title: "Şifren",
                    systemImage: "lock",
                    text: $password,
                    isSecure: true,
                    contentType: mode == .signIn ? .password : .newPassword,
                    submitLabel: .go,
                    onSubmit: submit
                )

                if mode == .register {
                    Text("Şifren en az \(Self.minimumPasswordLength) karakter olmalı.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colours.textSecondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    // Sitting under the password field, where somebody who has
                    // just failed to remember it is already looking.
                    Button("Şifreni mi unuttun?") {
                        isShowingForgotPassword = true
                    }
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colours.brand)
                    .frame(maxWidth: .infinity, alignment: .trailing)
                }

                if let errorMessage {
                    ErrorBanner(message: errorMessage)
                }

                Button(action: submit) {
                    Text(mode.title)
                }
                .buttonStyle(PrimaryButtonStyle(isLoading: isSubmitting))
                .disabled(!canSubmit || isSubmitting)
                .opacity(canSubmit ? 1 : 0.5)

                Button {
                    withAnimation(Theme.Motion.standard) {
                        mode = mode == .signIn ? .register : .signIn
                        errorMessage = nil
                    }
                } label: {
                    Text(mode == .signIn ? "Hesabın yok mu? " : "Zaten hesabın var mı? ")
                        .foregroundStyle(Theme.Colours.textSecondary)
                    + Text(mode == .signIn ? "Kayıt Ol" : "Giriş Yap")
                        .foregroundStyle(Theme.Colours.brand)
                }
                .font(Theme.Typography.callout)
            }
        }
    }

    private var modePicker: some View {
        HStack(spacing: 0) {
            ForEach(Mode.allCases) { candidate in
                Button {
                    withAnimation(Theme.Motion.standard) {
                        mode = candidate
                        errorMessage = nil
                    }
                } label: {
                    Text(candidate.title)
                        .font(Theme.Typography.callout)
                        .foregroundStyle(
                            mode == candidate
                                ? Theme.Colours.textOnBrand
                                : Theme.Colours.textSecondary
                        )
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, Theme.Spacing.xs)
                        .background {
                            if mode == candidate {
                                Capsule().fill(Theme.Colours.brandGradient)
                            }
                        }
                }
            }
        }
        .padding(Theme.Spacing.xxs)
        .background(Theme.Colours.surfaceElevated, in: Capsule())
    }

    // MARK: - Behaviour

    /// The backend enforces this; mirroring it here turns a round trip and a
    /// rejection into immediate, quiet guidance.
    private static let minimumPasswordLength = 10

    private var canSubmit: Bool {
        guard email.contains("@"), !password.isEmpty else { return false }
        switch mode {
        case .signIn:
            return true
        case .register:
            return fullName.trimmingCharacters(in: .whitespaces).count >= 2
                && password.count >= Self.minimumPasswordLength
        }
    }

    private func submit() {
        guard canSubmit, !isSubmitting else { return }
        isSubmitting = true
        errorMessage = nil

        Task {
            defer { isSubmitting = false }
            do {
                let user: UserProfile
                switch mode {
                case .signIn:
                    user = try await auth.signIn(
                        email: email.trimmingCharacters(in: .whitespaces),
                        password: password
                    )
                case .register:
                    user = try await auth.register(
                        RegistrationRequest(
                            email: email.trimmingCharacters(in: .whitespaces),
                            password: password,
                            fullName: fullName.trimmingCharacters(in: .whitespaces)
                        )
                    )
                }
                session.signedIn(as: user)
            } catch {
                // APIError conforms to LocalizedError, so this surfaces the
                // Turkish message the error case defines.
                errorMessage = error.localizedDescription
            }
        }
    }
}
