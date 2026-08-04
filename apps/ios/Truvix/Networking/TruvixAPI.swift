import Foundation

/// The application's calls, gathered behind one protocol.
///
/// Screens depend on this rather than on `APIClient`, so a view model can be
/// exercised against a stub without a network, and so every endpoint the app
/// uses is visible in one place instead of scattered through views.
protocol TruvixAPI: Sendable {
    func dashboard() async throws(APIError) -> Dashboard

    func garage(
        filter: GarageFilter,
        sort: VehicleSort,
        page: Int,
        pageSize: Int
    ) async throws(APIError) -> Page<VehicleSummary>

    func garageStats() async throws(APIError) -> GarageStats
    func vehicle(id: UUID) async throws(APIError) -> Vehicle
    func setFavourite(_ isFavourite: Bool, vehicleID: UUID) async throws(APIError) -> Vehicle
    func setInComparison(_ isInComparison: Bool, vehicleID: UUID) async throws(APIError) -> Vehicle
    func deleteVehicle(id: UUID) async throws(APIError)

    func analyses(page: Int, pageSize: Int) async throws(APIError) -> Page<AnalysisSummary>
    func analysis(id: UUID) async throws(APIError) -> Analysis
}

/// The live implementation, talking to the backend through `APIClient`.
struct LiveTruvixAPI: TruvixAPI {
    private let client: APIClient

    init(client: APIClient) {
        self.client = client
    }

    func dashboard() async throws(APIError) -> Dashboard {
        try await client.send(APIRequest(path: "dashboard"))
    }

    func garage(
        filter: GarageFilter,
        sort: VehicleSort,
        page: Int,
        pageSize: Int
    ) async throws(APIError) -> Page<VehicleSummary> {
        try await client.send(
            APIRequest(
                path: "vehicles",
                query: [
                    "filter": filter.rawValue,
                    "sort": sort.rawValue,
                    "page": String(page),
                    "page_size": String(pageSize),
                ]
            )
        )
    }

    func garageStats() async throws(APIError) -> GarageStats {
        try await client.send(APIRequest(path: "vehicles/stats"))
    }

    func vehicle(id: UUID) async throws(APIError) -> Vehicle {
        try await client.send(APIRequest(path: "vehicles/\(id.uuidString.lowercased())"))
    }

    func setFavourite(_ isFavourite: Bool, vehicleID: UUID) async throws(APIError) -> Vehicle {
        try await patchVehicle(id: vehicleID, body: VehicleFlagUpdate(isFavourite: isFavourite))
    }

    func setInComparison(
        _ isInComparison: Bool,
        vehicleID: UUID
    ) async throws(APIError) -> Vehicle {
        try await patchVehicle(
            id: vehicleID,
            body: VehicleFlagUpdate(isInComparison: isInComparison)
        )
    }

    func deleteVehicle(id: UUID) async throws(APIError) {
        try await client.send(
            APIRequest(method: .delete, path: "vehicles/\(id.uuidString.lowercased())")
        )
    }

    func analyses(page: Int, pageSize: Int) async throws(APIError) -> Page<AnalysisSummary> {
        try await client.send(
            APIRequest(
                path: "analyses",
                query: ["page": String(page), "page_size": String(pageSize)]
            )
        )
    }

    func analysis(id: UUID) async throws(APIError) -> Analysis {
        try await client.send(APIRequest(path: "analyses/\(id.uuidString.lowercased())"))
    }

    private func patchVehicle(
        id: UUID,
        body: VehicleFlagUpdate
    ) async throws(APIError) -> Vehicle {
        try await client.send(
            APIRequest(
                method: .patch,
                path: "vehicles/\(id.uuidString.lowercased())",
                body: body
            )
        )
    }
}

/// A partial vehicle update carrying only the flags the garage toggles.
///
/// Sending just the changed field means a toggle cannot clobber a concurrent
/// edit to the price or the notes.
private struct VehicleFlagUpdate: Encodable, Sendable {
    var isFavourite: Bool?
    var isInComparison: Bool?
}
