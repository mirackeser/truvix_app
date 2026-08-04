import Foundation
import Observation

/// Drives one copilot conversation.
@MainActor
@Observable
final class CopilotModel {
    private(set) var state: LoadState<CopilotThread> = .idle
    private(set) var isAvailable = true
    private(set) var isSending = false
    private(set) var sendError: String?

    /// The message being composed.
    var draft = ""

    private let api: any TruvixAPI
    private let vehicleID: UUID
    private var conversationID: UUID?

    /// Matches the backend's cap, so an over-long message is stopped here
    /// rather than after a round trip.
    static let maximumMessageLength = 4000

    init(api: any TruvixAPI, vehicleID: UUID) {
        self.api = api
        self.vehicleID = vehicleID
    }

    var canSend: Bool {
        let trimmed = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        return isAvailable
            && !isSending
            && !trimmed.isEmpty
            && trimmed.count <= Self.maximumMessageLength
    }

    /// Whether to offer the suggested questions rather than the history.
    var showsPrompts: Bool {
        state.value?.messages.isEmpty ?? false
    }

    func load() async {
        if state.value == nil {
            state = .loading
        }

        // Availability is checked first: without it, a deployment with no AI
        // key shows an inviting chat box that rejects everything typed into it.
        isAvailable = (try? await api.copilotStatus())?.available ?? false

        do {
            let thread = try await api.openConversation(vehicleID: vehicleID)
            conversationID = thread.conversation.id
            state = .loaded(thread)
        } catch {
            if state.value == nil {
                state = .failed(APIError.wrapping(error))
            }
        }
    }

    /// Send the composed message and append the exchange.
    ///
    /// The draft is only cleared once the reply arrives, so a failure leaves
    /// the question in the box to retry rather than losing what was typed.
    func send() async {
        guard canSend, let conversationID, let thread = state.value else { return }

        let content = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        isSending = true
        sendError = nil
        defer { isSending = false }

        do {
            let exchange = try await api.sendCopilotMessage(content, conversationID: conversationID)
            state = .loaded(
                CopilotThread(
                    conversation: thread.conversation,
                    messages: thread.messages + [
                        exchange.userMessage,
                        exchange.assistantMessage,
                    ]
                )
            )
            draft = ""
        } catch {
            sendError = APIError.wrapping(error).localizedDescription
        }
    }

    /// Fill the composer with a suggested question and send it.
    func ask(_ prompt: CopilotPrompt) async {
        guard !isSending else { return }
        draft = prompt.text
        await send()
    }
}
