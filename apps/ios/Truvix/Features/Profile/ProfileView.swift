import SwiftUI

/// The profile tab: the account, its plan, and the settings that belong to it.
struct ProfileView: View {
    @Environment(SessionStore.self) private var session

    let api: any TruvixAPI

    @State private var stats: GarageStats = .empty
    @State private var isConfirmingSignOut = false
    @State private var isShowingPaywall = false
    @State private var verificationMessage: String?
    @State private var isSendingVerification = false
    @State private var isShowingDeleteAccount = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: Theme.Spacing.md) {
                    if let user = session.phase.user {
                        identityCard(user)
                        activityCard
                        planCard(user)
                    }
                    settingsCard
                    signOutButton
                    deleteAccountButton
                    versionFooter
                }
                .padding(.horizontal, Theme.Spacing.md)
                .padding(.top, Theme.Spacing.sm)
                .padding(.bottom, Theme.Spacing.xl)
            }
            .screenBackground()
            .navigationTitle("Profil")
            .navigationBarTitleDisplayMode(.inline)
        }
        .task {
            stats = (try? await api.garageStats()) ?? .empty
        }
        .sheet(isPresented: $isShowingPaywall) {
            PaywallView(api: api)
        }
        .sheet(isPresented: $isShowingDeleteAccount) {
            DeleteAccountSheet(isPremium: session.phase.user?.isPremium ?? false)
        }
        .task {
            if LaunchOverrides.opensPaywall {
                isShowingPaywall = true
            }
            if LaunchOverrides.opensDeleteAccount {
                isShowingDeleteAccount = true
            }
        }
        .onChange(of: isShowingPaywall) { _, isShowing in
            // The plan shown here comes from the session, so a purchase made in
            // the sheet has to be picked up when it closes or the card would
            // still read "Ücretsiz Plan" after paying.
            if !isShowing {
                Task { await session.refreshProfile() }
            }
        }
        .confirmationDialog(
            "Çıkış yapmak istediğine emin misin?",
            isPresented: $isConfirmingSignOut,
            titleVisibility: .visible
        ) {
            Button("Çıkış Yap", role: .destructive) {
                Task { await session.signOut() }
            }
            Button("Vazgeç", role: .cancel) {}
        } message: {
            Text("Garajın ve analizlerin hesabında kalır; tekrar giriş yaptığında "
                + "her şey yerinde olur.")
        }
    }

    // MARK: - Sections

    private func identityCard(_ user: UserProfile) -> some View {
        Card(padding: Theme.Spacing.lg) {
            VStack(spacing: Theme.Spacing.xs) {
                Text(user.firstName.prefix(1).uppercased())
                    .font(Theme.Typography.displayLarge)
                    .foregroundStyle(Theme.Colours.textOnBrand)
                    .frame(width: 84, height: 84)
                    .background(Theme.Colours.brandGradient, in: Circle())
                    .accessibilityHidden(true)

                Text(user.fullName)
                    .font(Theme.Typography.title)
                    .foregroundStyle(Theme.Colours.textPrimary)

                Text(user.email)
                    .font(Theme.Typography.callout)
                    .foregroundStyle(Theme.Colours.textSecondary)

                if !user.emailVerified {
                    VStack(spacing: Theme.Spacing.xs) {
                        Label("E-posta doğrulanmadı", systemImage: "exclamationmark.circle")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colours.warning)

                        if let verificationMessage {
                            Text(verificationMessage)
                                .font(Theme.Typography.caption)
                                .foregroundStyle(Theme.Colours.textSecondary)
                                .multilineTextAlignment(.center)
                                .fixedSize(horizontal: false, vertical: true)
                        } else {
                            // A warning somebody cannot act on is just nagging,
                            // so it comes with the thing that resolves it.
                            Button("Doğrulama bağlantısı gönder") {
                                Task {
                                    isSendingVerification = true
                                    verificationMessage = await session.resendVerificationEmail()
                                    isSendingVerification = false
                                }
                            }
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colours.brand)
                            .disabled(isSendingVerification)
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity)
        }
    }

    private var activityCard: some View {
        Card {
            HStack {
                statistic(value: stats.total, label: "Araç")
                Divider().frame(height: 32).overlay(Theme.Colours.border)
                statistic(value: stats.favourites, label: "Favori")
                Divider().frame(height: 32).overlay(Theme.Colours.border)
                statistic(value: stats.priceDropped, label: "Fiyatı Düştü")
            }
        }
    }

    private func statistic(value: Int, label: String) -> some View {
        VStack(spacing: 2) {
            Text("\(value)")
                .font(Theme.Typography.title)
                .monospacedDigit()
                .foregroundStyle(Theme.Colours.textPrimary)
            Text(label)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colours.textSecondary)
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(value) \(label)")
    }

    private func planCard(_ user: UserProfile) -> some View {
        Card {
            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                HStack {
                    Image(systemName: "crown.fill")
                        .foregroundStyle(Theme.Colours.warning)
                    Text(user.isPremium ? "Truvix Premium" : "Ücretsiz Plan")
                        .font(Theme.Typography.headline)
                        .foregroundStyle(Theme.Colours.textPrimary)
                    Spacer()
                }

                Text(
                    user.isPremium
                        ? "Sınırsız analiz, gelişmiş AI raporları ve öncelikli destek dahil."
                        : "Şu an temel özellikleri kullanıyorsun."
                )
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colours.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

                if user.isPremium {
                    Button("Aboneliği yönet") {
                        isShowingPaywall = true
                    }
                    .buttonStyle(SecondaryButtonStyle())
                } else {
                    Button("Premium'a geç") {
                        isShowingPaywall = true
                    }
                    .buttonStyle(PrimaryButtonStyle())
                }
            }
        }
    }

    private var settingsCard: some View {
        Card(padding: Theme.Spacing.sm) {
            VStack(spacing: 0) {
                NavigationLink {
                    NotificationsView(api: api)
                } label: {
                    settingRow(
                        title: "Bildirim Ayarları",
                        symbolName: "bell.badge",
                        detail: "Fiyat, risk ve AI bildirimleri"
                    )
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func settingRow(title: String, symbolName: String, detail: String) -> some View {
        HStack(spacing: Theme.Spacing.sm) {
            Image(systemName: symbolName)
                .font(Theme.Typography.body)
                .foregroundStyle(Theme.Colours.brand)
                .frame(width: 32, height: 32)
                .background(Theme.Colours.brand.opacity(0.12), in: Circle())

            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(Theme.Typography.callout)
                    .foregroundStyle(Theme.Colours.textPrimary)
                Text(detail)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colours.textSecondary)
            }

            Spacer(minLength: 0)

            Image(systemName: "chevron.right")
                .font(Theme.Typography.label)
                .foregroundStyle(Theme.Colours.textSecondary)
        }
        .padding(.vertical, Theme.Spacing.xs)
        .contentShape(Rectangle())
    }

    private var signOutButton: some View {
        Button("Çıkış Yap") {
            isConfirmingSignOut = true
        }
        .buttonStyle(SecondaryButtonStyle())
    }

    /// Required by App Store Review Guideline 5.1.1(v).
    ///
    /// It lives in the profile beside signing out, where somebody looking for it
    /// would look, rather than being hidden a level deeper to discourage use.
    private var deleteAccountButton: some View {
        Button("Hesabımı Sil") {
            isShowingDeleteAccount = true
        }
        .font(Theme.Typography.callout)
        .foregroundStyle(Theme.Colours.danger)
        .padding(.top, Theme.Spacing.xs)
    }

    private var versionFooter: some View {
        Text("Truvix \(Bundle.main.shortVersion) (\(Bundle.main.buildNumber))")
            .font(Theme.Typography.caption)
            .foregroundStyle(Theme.Colours.textSecondary)
            .padding(.top, Theme.Spacing.xs)
    }
}

extension Bundle {
    /// The marketing version, as the App Store shows it.
    var shortVersion: String {
        object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "—"
    }

    /// The build number, which a bug report needs to identify the exact binary.
    var buildNumber: String {
        object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "—"
    }
}
