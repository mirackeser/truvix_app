import Observation
import SwiftUI

/// Drives the notification centre: the tab in view, its page, and the counts.
@MainActor
@Observable
final class NotificationsModel {
    private(set) var state: LoadState<[AppNotification]> = .idle
    private(set) var summary: NotificationSummary = .empty
    private(set) var preferences: NotificationPreferences = .allEnabled

    /// `nil` means the "Tümü" tab.
    var category: NotificationCategory? {
        didSet {
            guard category != oldValue else { return }
            Task { await load() }
        }
    }

    private let api: any TruvixAPI
    private static let pageSize = 50

    init(api: any TruvixAPI) {
        self.api = api
    }

    func load() async {
        if state.value == nil {
            state = .loading
        }

        do {
            async let listing = api.notifications(
                category: category, unreadOnly: false, page: 1, pageSize: Self.pageSize
            )
            async let counts = api.notificationSummary()

            let (page, summaryCounts) = try await (listing, counts)
            summary = summaryCounts
            state = .loaded(page.items)
        } catch {
            if state.value == nil {
                state = .failed(APIError.wrapping(error))
            }
        }
    }

    func loadPreferences() async {
        if let loaded = try? await api.notificationPreferences() {
            preferences = loaded
        }
    }

    /// Mark one entry read, updating the row before the server confirms.
    func markRead(_ notification: AppNotification) async {
        guard !notification.read, let items = state.value else { return }
        guard let index = items.firstIndex(where: { $0.id == notification.id }) else { return }

        state = .loaded(replacing(items, at: index, read: true))
        summary = summary.decrementingUnread()

        do {
            _ = try await api.markNotificationRead(id: notification.id)
        } catch {
            // Put the badge back rather than leave the list claiming something
            // the server never recorded.
            if let current = state.value,
               let position = current.firstIndex(where: { $0.id == notification.id }) {
                state = .loaded(replacing(current, at: position, read: false))
            }
            summary = (try? await api.notificationSummary()) ?? summary
        }
    }

    func markAllRead() async {
        guard summary.unread > 0 else { return }
        _ = try? await api.markAllNotificationsRead(category: category)
        await load()
    }

    func setPreference(_ update: NotificationPreferencesUpdate) async {
        let previous = preferences
        if let applied = try? await api.updateNotificationPreferences(update) {
            preferences = applied
        } else {
            preferences = previous
        }
    }

    private func replacing(
        _ items: [AppNotification],
        at index: Int,
        read: Bool
    ) -> [AppNotification] {
        var updated = items
        let existing = updated[index]
        updated[index] = AppNotification(
            id: existing.id,
            category: existing.category,
            eventType: existing.eventType,
            title: existing.title,
            body: existing.body,
            vehicleId: existing.vehicleId,
            read: read,
            createdAt: existing.createdAt
        )
        return updated
    }
}

private extension NotificationSummary {
    func decrementingUnread() -> NotificationSummary {
        NotificationSummary(
            total: total,
            unread: max(unread - 1, 0),
            opportunities: opportunities,
            risks: risks,
            aiSuggestions: aiSuggestions
        )
    }
}

/// The notification centre.
struct NotificationsView: View {
    @State private var model: NotificationsModel
    @State private var isShowingPreferences = false

    /// Called when an entry that concerns a vehicle is tapped.
    private let onOpenVehicle: (UUID) -> Void

    init(api: any TruvixAPI, onOpenVehicle: @escaping (UUID) -> Void = { _ in }) {
        _model = State(wrappedValue: NotificationsModel(api: api))
        self.onOpenVehicle = onOpenVehicle
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                categoryTabs

                Group {
                    switch model.state {
                    case .idle, .loading:
                        LoadingState()
                    case let .failed(error):
                        FailureState(error: error) {
                            Task { await model.load() }
                        }
                    case let .loaded(notifications):
                        if notifications.isEmpty {
                            emptyState
                        } else {
                            list(notifications)
                        }
                    }
                }
            }
            .screenBackground()
            .navigationTitle("Bildirimler")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button {
                            Task { await model.markAllRead() }
                        } label: {
                            Label("Tümünü Okundu İşaretle", systemImage: "checkmark.circle")
                        }
                        .disabled(model.summary.unread == 0)

                        Button {
                            isShowingPreferences = true
                        } label: {
                            Label("Ayarları Yönet", systemImage: "gearshape")
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                            .foregroundStyle(Theme.Colours.textPrimary)
                    }
                }
            }
            .sheet(isPresented: $isShowingPreferences) {
                NotificationPreferencesView(model: model)
            }
        }
        .task {
            await model.load()
            await model.loadPreferences()
        }
    }

    private var categoryTabs: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: Theme.Spacing.xs) {
                tab(title: "Tümü", category: nil)
                ForEach(NotificationCategory.allCases) { candidate in
                    tab(title: candidate.title, category: candidate)
                }
            }
            .padding(.horizontal, Theme.Spacing.md)
        }
        .padding(.bottom, Theme.Spacing.sm)
    }

    private func tab(title: String, category: NotificationCategory?) -> some View {
        let isSelected = model.category == category
        let count = model.summary.count(for: category)

        return Button {
            model.category = category
        } label: {
            HStack(spacing: Theme.Spacing.xxs) {
                Text(title)
                    .font(Theme.Typography.callout)
                if count > 0 {
                    Text("\(count)")
                        .font(Theme.Typography.microBold)
                        .monospacedDigit()
                        .opacity(0.8)
                }
            }
            .foregroundStyle(
                isSelected ? Theme.Colours.textOnBrand : Theme.Colours.textSecondary
            )
            .padding(.horizontal, Theme.Spacing.md)
            .padding(.vertical, Theme.Spacing.xs)
            .background {
                if isSelected {
                    Capsule().fill(Theme.Colours.brandGradient)
                } else {
                    Capsule().fill(Theme.Colours.surface)
                }
            }
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(isSelected ? [.isSelected] : [])
    }

    private func list(_ notifications: [AppNotification]) -> some View {
        ScrollView {
            LazyVStack(spacing: Theme.Spacing.xs) {
                ForEach(notifications) { notification in
                    NotificationRow(notification: notification) {
                        // Reading and acting are one gesture: a notification
                        // that only marks itself read is a dead end.
                        Task { await model.markRead(notification) }
                        if let vehicleID = notification.vehicleId {
                            onOpenVehicle(vehicleID)
                        }
                    }
                }
            }
            .padding(.horizontal, Theme.Spacing.md)
            .padding(.bottom, Theme.Spacing.xl)
        }
        .refreshable { await model.load() }
    }

    private var emptyState: some View {
        ScrollView {
            EmptyState(
                symbolName: "bell.slash",
                title: "Bildirim yok",
                message: "Fiyat düşüşleri, risk uyarıları ve AI önerileri burada görünecek."
            )
            .padding(.top, Theme.Spacing.xxl)
        }
        .refreshable { await model.load() }
    }
}

private struct NotificationRow: View {
    let notification: AppNotification
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            Card(padding: Theme.Spacing.sm) {
                HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                    Image(systemName: notification.category.symbolName)
                        .font(Theme.Typography.callout)
                        .foregroundStyle(tint)
                        .frame(width: 36, height: 36)
                        .background(tint.opacity(0.14), in: Circle())

                    VStack(alignment: .leading, spacing: 3) {
                        HStack(alignment: .firstTextBaseline) {
                            Text(notification.title)
                                .font(Theme.Typography.callout)
                                .foregroundStyle(Theme.Colours.textPrimary)
                            Spacer(minLength: Theme.Spacing.xs)
                            Text(
                                notification.createdAt
                                    .formatted(.dateTime.hour().minute())
                            )
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colours.textSecondary)
                        }

                        Text(notification.body)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colours.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                            .multilineTextAlignment(.leading)
                    }

                    if !notification.read {
                        Circle()
                            .fill(Theme.Colours.brand)
                            .frame(width: 8, height: 8)
                            .padding(.top, 6)
                    }
                }
            }
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityHint(hint)
    }

    private var hint: String {
        if notification.vehicleId != nil {
            return "Aracı açmak için dokun"
        }
        return notification.read ? "" : "Okundu işaretlemek için dokun"
    }

    private var tint: Color {
        switch notification.category {
        case .opportunity: Theme.Colours.brand
        case .risk: Theme.Colours.danger
        case .aiSuggestion: Theme.Colours.brandBright
        case .system: Theme.Colours.textSecondary
        }
    }
}

/// The notification switches, as the settings list in the design shows them.
private struct NotificationPreferencesView: View {
    let model: NotificationsModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: Theme.Spacing.sm) {
                    Card {
                        VStack(spacing: Theme.Spacing.sm) {
                            toggle(
                                title: "Fiyat Değişimleri",
                                symbolName: "chart.line.downtrend.xyaxis",
                                isOn: model.preferences.priceChanges
                            ) { NotificationPreferencesUpdate(priceChanges: $0) }

                            Divider().overlay(Theme.Colours.border)

                            toggle(
                                title: "Risk Uyarıları",
                                symbolName: "exclamationmark.triangle",
                                isOn: model.preferences.riskAlerts
                            ) { NotificationPreferencesUpdate(riskAlerts: $0) }

                            Divider().overlay(Theme.Colours.border)

                            toggle(
                                title: "AI Önerileri",
                                symbolName: "sparkles",
                                isOn: model.preferences.aiSuggestions
                            ) { NotificationPreferencesUpdate(aiSuggestions: $0) }

                            Divider().overlay(Theme.Colours.border)

                            toggle(
                                title: "Piyasa Analizleri",
                                symbolName: "chart.bar",
                                isOn: model.preferences.marketUpdates
                            ) { NotificationPreferencesUpdate(marketUpdates: $0) }
                        }
                    }

                    Text("Kapattığın kategorilerde bildirim üretilmez; geçmiş "
                        + "bildirimlerin silinmez.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colours.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(.horizontal, Theme.Spacing.md)
                .padding(.top, Theme.Spacing.md)
            }
            .screenBackground()
            .navigationTitle("Bildirim Ayarları")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Bitti") { dismiss() }
                        .foregroundStyle(Theme.Colours.brand)
                }
            }
        }
    }

    private func toggle(
        title: String,
        symbolName: String,
        isOn: Bool,
        update: @escaping (Bool) -> NotificationPreferencesUpdate
    ) -> some View {
        Toggle(isOn: Binding(
            get: { isOn },
            set: { newValue in
                Task { await model.setPreference(update(newValue)) }
            }
        )) {
            Label(title, systemImage: symbolName)
                .font(Theme.Typography.callout)
                .foregroundStyle(Theme.Colours.textPrimary)
        }
        .tint(Theme.Colours.brand)
    }
}
