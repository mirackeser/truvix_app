import Foundation
import OSLog
import Observation
import UIKit
import UserNotifications

/// What a tapped notification wants opened.
struct NotificationDestination: Equatable, Sendable {
    let eventType: String
    let vehicleID: UUID?

    /// Read the destination out of an APNs payload.
    ///
    /// Returns `nil` for anything that does not name a destination, so a
    /// malformed or unfamiliar payload leaves the app where it was rather than
    /// navigating somewhere arbitrary.
    init?(payload: [AnyHashable: Any]) {
        guard let eventType = payload["event_type"] as? String else { return nil }
        self.eventType = eventType
        vehicleID = (payload["vehicle_id"] as? String).flatMap(UUID.init(uuidString:))
    }
}

/// Asks for notification permission and keeps the backend told where to send.
///
/// The token is not stable: iOS reissues it after a restore, an update, or for
/// no reason at all, so the app registers on every launch rather than once.
/// Registration is idempotent on the backend, which is what makes that cheap.
@Observable
@MainActor
final class PushRegistrar: NSObject {
    /// Where a tapped notification wants to go, consumed by the shell.
    var pendingDestination: NotificationDestination?

    /// Whether the person has been asked yet.
    private(set) var hasBeenAsked = false

    @ObservationIgnored private let auth: any AuthServicing
    @ObservationIgnored private let logger = Logger(
        subsystem: "app.truvix.ios",
        category: "push"
    )
    @ObservationIgnored private var lastRegisteredToken: String?

    init(auth: any AuthServicing) {
        self.auth = auth
        super.init()
        UNUserNotificationCenter.current().delegate = self
    }

    /// Ask for permission, if it has not been settled already.
    ///
    /// Deliberately not called at launch. A permission prompt shown before
    /// somebody knows what the app does is usually refused, and iOS only asks
    /// once — a refusal is close to permanent. The shell asks after the first
    /// vehicle is saved, when "tell me if this gets cheaper" means something.
    func requestAuthorisationIfNeeded() async {
        let centre = UNUserNotificationCenter.current()
        let settings = await centre.notificationSettings()

        guard settings.authorizationStatus == .notDetermined else {
            hasBeenAsked = true
            if settings.authorizationStatus == .authorized {
                UIApplication.shared.registerForRemoteNotifications()
            }
            return
        }

        do {
            let granted = try await centre.requestAuthorization(options: [
                .alert, .badge, .sound
            ])
            hasBeenAsked = true
            if granted {
                UIApplication.shared.registerForRemoteNotifications()
            }
        } catch {
            logger.error("İzin istenemedi: \(error.localizedDescription, privacy: .public)")
        }
    }

    /// Register with the backend once iOS has issued a token.
    ///
    /// - Parameter deviceToken: The raw token from
    ///   `didRegisterForRemoteNotificationsWithDeviceToken`.
    func register(deviceToken: Data) async {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        guard token != lastRegisteredToken else { return }

        do {
            try await auth.registerDevice(token: token)
            lastRegisteredToken = token
            logger.info("Cihaz kaydedildi")
        } catch {
            // Worth retrying next launch rather than escalating: the person
            // still gets their notifications in the app.
            logger.error("Cihaz kaydedilemedi: \(error.localizedDescription, privacy: .public)")
        }
    }

    /// Stop notifications reaching this device.
    ///
    /// Called when signing out, so the next person to use the handset does not
    /// receive somebody else's alerts.
    func unregister() async {
        guard let token = lastRegisteredToken else { return }
        lastRegisteredToken = nil
        do {
            try await auth.unregisterDevice(token: token)
        } catch {
            logger.error("Cihaz kaydı silinemedi: \(error.localizedDescription, privacy: .public)")
        }
    }

    /// Clear the app icon's badge.
    func clearBadge() async {
        do {
            try await UNUserNotificationCenter.current().setBadgeCount(0)
        } catch {
            logger.error("Rozet temizlenemedi: \(error.localizedDescription, privacy: .public)")
        }
    }
}

extension PushRegistrar: UNUserNotificationCenterDelegate {
    /// Show the notification even while the app is open.
    ///
    /// Without this iOS suppresses it, and somebody reading a report would
    /// never learn that a different vehicle just dropped in price.
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner, .list, .sound]
    }

    /// Record where a tapped notification wants to go.
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse
    ) async {
        let payload = response.notification.request.content.userInfo
        guard let destination = NotificationDestination(payload: payload) else { return }
        await MainActor.run { self.pendingDestination = destination }
    }
}

/// Bridges the UIKit callbacks SwiftUI has no equivalent for.
///
/// Device token delivery arrives only through the application delegate; there
/// is no SwiftUI counterpart, so this exists solely to forward it.
final class PushAppDelegate: NSObject, UIApplicationDelegate {
    /// Set by the app on launch, before iOS can call back.
    @MainActor static var registrar: PushRegistrar?

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        Task { @MainActor in
            await Self.registrar?.register(deviceToken: deviceToken)
        }
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: any Error
    ) {
        Logger(subsystem: "app.truvix.ios", category: "push")
            .error("APNs kaydı başarısız: \(error.localizedDescription, privacy: .public)")
    }
}
