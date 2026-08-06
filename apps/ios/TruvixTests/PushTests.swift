import Foundation
import Testing

@testable import Truvix

@Suite("Notification destinations")
struct NotificationDestinationTests {

    @Test("A price drop payload names the vehicle it is about")
    func vehiclePayloadIsRead() throws {
        let id = UUID()
        let payload: [AnyHashable: Any] = [
            "event_type": "price_drop",
            "vehicle_id": id.uuidString,
            "notification_id": UUID().uuidString
        ]

        let destination = try #require(NotificationDestination(payload: payload))

        #expect(destination.eventType == "price_drop")
        #expect(destination.vehicleID == id)
    }

    @Test("A payload with no vehicle still names its event")
    func eventWithoutVehicle() throws {
        let destination = try #require(
            NotificationDestination(payload: ["event_type": "risk_alert"])
        )

        #expect(destination.eventType == "risk_alert")
        #expect(destination.vehicleID == nil)
    }

    @Test("A payload naming no event is refused")
    func unnamedPayloadIsRefused() {
        // Better to leave somebody where they were than to navigate somewhere
        // arbitrary because a payload was malformed or came from a newer build.
        #expect(NotificationDestination(payload: ["vehicle_id": UUID().uuidString]) == nil)
        #expect(NotificationDestination(payload: [:]) == nil)
    }

    @Test("A vehicle id that is not a uuid is dropped, not guessed at")
    func malformedVehicleIsDropped() throws {
        let destination = try #require(
            NotificationDestination(payload: ["event_type": "price_drop", "vehicle_id": "nope"])
        )

        #expect(destination.vehicleID == nil)
    }
}
