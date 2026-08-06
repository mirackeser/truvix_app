import SwiftUI

/// The screen for deleting an account.
///
/// Deliberately slow to get through. It is the only action in the app that
/// cannot be undone, so it states plainly what goes, asks for the password
/// rather than accepting the session as proof, and puts the destructive button
/// behind a confirmation.
struct DeleteAccountSheet: View {
    @Environment(SessionStore.self) private var session
    @Environment(\.dismiss) private var dismiss

    @State private var password = ""
    @State private var isConfirming = false
    @State private var isDeleting = false
    @State private var failure: String?

    /// Whether the account holds a subscription that will outlive the account.
    let isPremium: Bool

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                    consequences

                    if isPremium {
                        subscriptionWarning
                    }

                    confirmation

                    if let failure {
                        ErrorBanner(message: failure)
                    }
                }
                .padding(Theme.Spacing.md)
            }
            .screenBackground()
            .navigationTitle("Hesabı Sil")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Vazgeç") { dismiss() }
                        .disabled(isDeleting)
                }
            }
        }
        .interactiveDismissDisabled(isDeleting)
        .confirmationDialog(
            "Hesabın ve tüm verilerin kalıcı olarak silinecek.",
            isPresented: $isConfirming,
            titleVisibility: .visible
        ) {
            Button("Hesabımı Kalıcı Olarak Sil", role: .destructive) {
                Task { await delete() }
            }
            Button("Vazgeç", role: .cancel) {}
        } message: {
            Text("Bu işlem geri alınamaz.")
        }
    }

    // MARK: - Sections

    private var consequences: some View {
        Card {
            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                Text("Silinecekler")
                    .font(Theme.Typography.headline)
                    .foregroundStyle(Theme.Colours.textPrimary)

                ForEach(
                    [
                        "Hesabın ve profil bilgilerin",
                        "Garajındaki tüm araçlar ve fiyat geçmişi",
                        "Tüm analizler, raporlar ve yüklediğin fotoğraflar",
                        "Copilot sohbetlerin ve bildirimlerin"
                    ],
                    id: \.self
                ) { item in
                    Label(item, systemImage: "minus.circle")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colours.textSecondary)
                }

                Text("Bu işlem geri alınamaz.")
                    .font(Theme.Typography.callout)
                    .foregroundStyle(Theme.Colours.danger)
                    .padding(.top, Theme.Spacing.xxs)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// Deleting the account does not end the App Store subscription.
    ///
    /// Apple owns that relationship and only the customer can end it. Somebody
    /// who deletes their account assuming the billing stops with it would keep
    /// paying, so it is said here rather than discovered on the next renewal.
    private var subscriptionWarning: some View {
        Card {
            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                Label("Aboneliğin devam eder", systemImage: "exclamationmark.triangle.fill")
                    .font(Theme.Typography.headline)
                    .foregroundStyle(Theme.Colours.warning)

                Text(
                    """
                    Hesabını silmek Truvix Premium aboneliğini iptal etmez. \
                    Aboneliği Apple Kimliği ayarlarından iptal etmen gerekir, \
                    yoksa ücretlendirme devam eder.
                    """
                )
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colours.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

                if let url = URL(string: "https://apps.apple.com/account/subscriptions") {
                    Link("Abonelikleri yönet", destination: url)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colours.brand)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var confirmation: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text("Devam etmek için şifreni gir")
                .font(Theme.Typography.callout)
                .foregroundStyle(Theme.Colours.textSecondary)

            TruvixTextField(
                title: "Şifren",
                systemImage: "lock",
                text: $password,
                isSecure: true,
                contentType: .password,
                submitLabel: .done
            )
            .disabled(isDeleting)

            Button {
                isConfirming = true
            } label: {
                if isDeleting {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                } else {
                    Text("Hesabımı Sil")
                        .frame(maxWidth: .infinity)
                }
            }
            .buttonStyle(DestructiveButtonStyle())
            .disabled(password.isEmpty || isDeleting)
        }
    }

    // MARK: - Actions

    private func delete() async {
        isDeleting = true
        failure = await session.deleteAccount(password: password)
        isDeleting = false

        // On success the session store has already signed out, and the root
        // view has swapped to the signed-out screen underneath this sheet.
        if failure == nil {
            dismiss()
        }
    }
}
