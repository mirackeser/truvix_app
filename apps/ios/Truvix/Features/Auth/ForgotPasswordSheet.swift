import SwiftUI

/// Asks for a reset link.
///
/// The confirmation is deliberately vague about whether the address had an
/// account. The backend will not say, because that would turn this screen into
/// a way to find out who has signed up, and a message here that said "no such
/// account" would give away exactly what the endpoint refuses to.
struct ForgotPasswordSheet: View {
    @Environment(\.dismiss) private var dismiss

    let auth: any AuthServicing
    /// Prefilled from whatever was typed on the sign-in screen.
    let initialEmail: String

    @State private var email: String
    @State private var isSending = false
    @State private var didSend = false
    @State private var failure: String?

    init(auth: any AuthServicing, initialEmail: String = "") {
        self.auth = auth
        self.initialEmail = initialEmail
        _email = State(initialValue: initialEmail)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.md) {
                    if didSend {
                        sent
                    } else {
                        form
                    }
                }
                .padding(Theme.Spacing.md)
            }
            .screenBackground()
            .navigationTitle("Şifreni Sıfırla")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(didSend ? "Kapat" : "Vazgeç") { dismiss() }
                }
            }
        }
    }

    // MARK: - Sections

    private var form: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.md) {
            Text(
                """
                Hesabının e-posta adresini gir. Kayıtlıysa şifreni \
                sıfırlaman için bir bağlantı göndereceğiz.
                """
            )
            .font(Theme.Typography.body)
            .foregroundStyle(Theme.Colours.textSecondary)
            .fixedSize(horizontal: false, vertical: true)

            TruvixTextField(
                title: "E-posta adresin",
                systemImage: "envelope",
                text: $email,
                keyboard: .emailAddress,
                contentType: .username,
                submitLabel: .send,
                onSubmit: send
            )
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .disabled(isSending)

            if let failure {
                ErrorBanner(message: failure)
            }

            Button(action: send) {
                Text("Bağlantı Gönder")
            }
            .buttonStyle(PrimaryButtonStyle(isLoading: isSending))
            .disabled(!isValid || isSending)
            .opacity(isValid ? 1 : 0.5)
        }
    }

    private var sent: some View {
        VStack(spacing: Theme.Spacing.sm) {
            Image(systemName: "envelope.badge")
                .font(.system(size: 44))
                .foregroundStyle(Theme.Colours.brand)
                .accessibilityHidden(true)

            Text("Bağlantıyı gönderdik")
                .font(Theme.Typography.title)
                .foregroundStyle(Theme.Colours.textPrimary)

            Text(
                """
                \(email) adresi kayıtlıysa şifreni sıfırlama bağlantısı \
                gelen kutunda olacak. Bulamazsan spam klasörüne de bak.
                """
            )
            .font(Theme.Typography.body)
            .foregroundStyle(Theme.Colours.textSecondary)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, Theme.Spacing.xl)
        .accessibilityElement(children: .combine)
    }

    // MARK: - Actions

    private var isValid: Bool {
        let trimmed = email.trimmingCharacters(in: .whitespaces)
        return trimmed.contains("@") && trimmed.count > 4
    }

    private func send() {
        guard isValid, !isSending else { return }
        Task {
            isSending = true
            failure = nil
            do {
                try await auth.requestPasswordReset(
                    email: email.trimmingCharacters(in: .whitespaces)
                )
                didSend = true
            } catch {
                // Only a transport or throttling failure reaches here; the
                // backend answers 202 whether or not the address is known.
                failure = error.localizedDescription
            }
            isSending = false
        }
    }
}
