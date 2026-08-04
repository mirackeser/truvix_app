import Foundation

/// Who wrote a stored copilot message.
enum MessageRole: String, Codable, Sendable {
    case user
    case assistant
}

/// One message in a copilot conversation.
struct CopilotMessage: Codable, Identifiable, Equatable, Sendable {
    let id: UUID
    let role: MessageRole
    let content: String
    let createdAt: Date
}

/// A conversation and the vehicle it is about.
struct CopilotConversation: Codable, Identifiable, Equatable, Sendable {
    let id: UUID
    let vehicleId: UUID
    let vehicleDisplayName: String
    let createdAt: Date
}

/// A conversation with its full history.
struct CopilotThread: Codable, Equatable, Sendable {
    let conversation: CopilotConversation
    let messages: [CopilotMessage]
}

/// The user's message together with the assistant's reply.
struct MessageExchange: Codable, Sendable {
    let userMessage: CopilotMessage
    let assistantMessage: CopilotMessage
}

/// Whether AI assistance is configured on this deployment.
struct CopilotStatus: Codable, Sendable {
    let available: Bool
}

struct ConversationOpenRequest: Encodable, Sendable {
    let vehicleId: UUID
}

struct MessageSendRequest: Encodable, Sendable {
    let content: String
}

/// The suggested questions the copilot screen offers before the user types.
///
/// They exist because a blank chat box is the hardest possible starting point:
/// a person who has never used an AI assistant does not know what it can
/// answer, and these show the range in one glance.
enum CopilotPrompt: String, CaseIterable, Identifiable, Sendable {
    case worthBuying = "Bu araç alınır mı?"
    case whyRisky = "Bu araç neden riskli?"
    case realValue = "Gerçek piyasa değeri nedir?"
    case negotiation = "Nasıl pazarlık etmeliyim?"
    case inspection = "Ekspertizde neye dikkat etmeliyim?"
    case resale = "5 yıl sonra satılabilir mi?"

    var id: Self { self }

    var text: String { rawValue }

    var symbolName: String {
        switch self {
        case .worthBuying: "checkmark.seal"
        case .whyRisky: "exclamationmark.triangle"
        case .realValue: "turkishlirasign.circle"
        case .negotiation: "hand.raised"
        case .inspection: "wrench.and.screwdriver"
        case .resale: "clock.arrow.circlepath"
        }
    }
}
