import Foundation
import Observation

/// Drives the garage screen: the tab in view, its page, and the tab counts.
@MainActor
@Observable
final class GarageModel {
    private(set) var state: LoadState<[VehicleSummary]> = .idle
    private(set) var stats: GarageStats = .empty
    private(set) var isLoadingMore = false

    var filter: GarageFilter = .all {
        didSet {
            guard filter != oldValue else { return }
            Task { await load() }
        }
    }

    var sort: VehicleSort = .recentlyAdded {
        didSet {
            guard sort != oldValue else { return }
            Task { await load() }
        }
    }

    private let api: any TruvixAPI
    private var page = 1
    private var hasNextPage = false

    /// Large enough to fill a tall screen, small enough that the first page
    /// arrives quickly on a slow connection.
    private static let pageSize = 20

    init(api: any TruvixAPI) {
        self.api = api
    }

    func load() async {
        if state.value == nil {
            state = .loading
        }
        page = 1

        do {
            async let listing = api.garage(
                filter: filter, sort: sort, page: 1, pageSize: Self.pageSize
            )
            async let counts = api.garageStats()

            let (result, garageStats) = try await (listing, counts)
            hasNextPage = result.hasNext
            stats = garageStats
            state = .loaded(result.items)
        } catch {
            // An existing list survives a failed refresh; only a first load has
            // nothing better to show than the error.
            if state.value == nil {
                state = .failed(APIError.wrapping(error))
            }
        }
    }

    /// Fetch the next page when the list nears its end.
    ///
    /// Guarded on both the flag and the known `hasNext`, so scrolling fast
    /// cannot fire several overlapping requests for the same page.
    func loadMoreIfNeeded(currentItem: VehicleSummary) async {
        guard hasNextPage, !isLoadingMore, let items = state.value else { return }
        guard items.suffix(3).contains(where: { $0.id == currentItem.id }) else { return }

        isLoadingMore = true
        defer { isLoadingMore = false }

        do {
            let next = try await api.garage(
                filter: filter, sort: sort, page: page + 1, pageSize: Self.pageSize
            )
            page += 1
            hasNextPage = next.hasNext
            state = .loaded(items + next.items)
        } catch {
            // A failed page keeps the list intact; the user can scroll again.
            hasNextPage = false
        }
    }

    /// Toggle the favourite flag, updating the row before the server replies.
    ///
    /// The optimistic update is reverted if the call fails, so the star never
    /// stays in a state the backend did not accept.
    func toggleFavourite(_ summary: VehicleSummary) async {
        guard let items = state.value,
              let index = items.firstIndex(where: { $0.id == summary.id }) else { return }

        let desired = !summary.vehicle.isFavourite
        state = .loaded(replacing(items, at: index, isFavourite: desired))

        do {
            _ = try await api.setFavourite(desired, vehicleID: summary.vehicle.id)
            stats = try await api.garageStats()
            // Leaving the favourites tab means the row no longer belongs here.
            if filter == .favourites, !desired {
                await load()
            }
        } catch {
            if let current = state.value,
               let position = current.firstIndex(where: { $0.id == summary.id }) {
                state = .loaded(replacing(current, at: position, isFavourite: !desired))
            }
        }
    }

    private func replacing(
        _ items: [VehicleSummary],
        at index: Int,
        isFavourite: Bool
    ) -> [VehicleSummary] {
        var updated = items
        let existing = updated[index]
        updated[index] = VehicleSummary(
            vehicle: existing.vehicle.settingFavourite(isFavourite),
            priceTrend: existing.priceTrend
        )
        return updated
    }
}

extension Vehicle {
    /// A copy with the favourite flag changed, for optimistic updates.
    func settingFavourite(_ isFavourite: Bool) -> Vehicle {
        Vehicle(
            id: id,
            make: make,
            model: model,
            variant: variant,
            displayName: displayName,
            modelYear: modelYear,
            mileageKm: mileageKm,
            fuelType: fuelType,
            transmission: transmission,
            bodyType: bodyType,
            colour: colour,
            plate: plate,
            vin: vin,
            listingSource: listingSource,
            listingURL: listingURL,
            sellerType: sellerType,
            city: city,
            askingPrice: askingPrice,
            currency: currency,
            isFavourite: isFavourite,
            isInComparison: isInComparison,
            notes: notes,
            lastViewedAt: lastViewedAt,
            createdAt: createdAt,
            updatedAt: updatedAt
        )
    }
}
