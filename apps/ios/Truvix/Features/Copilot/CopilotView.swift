import SwiftUI

/// The AI copilot: a conversation about one specific vehicle.
struct CopilotView: View {
    @State private var model: CopilotModel
    private let vehicle: Vehicle
    private let latestScore: Int?

    init(api: any TruvixAPI, vehicle: Vehicle, latestScore: Int?) {
        _model = State(wrappedValue: CopilotModel(api: api, vehicleID: vehicle.id))
        self.vehicle = vehicle
        self.latestScore = latestScore
    }

    var body: some View {
        VStack(spacing: 0) {
            vehicleHeader

            switch model.state {
            case .idle, .loading:
                LoadingState(message: "Sohbet hazırlanıyor…")
            case let .failed(error):
                FailureState(error: error) {
                    Task { await model.load() }
                }
            case let .loaded(thread):
                transcript(thread)
            }

            composer
        }
        .screenBackground()
        .navigationTitle("Truvix AI Copilot")
        .navigationBarTitleDisplayMode(.inline)
        .task { await model.load() }
    }

    // MARK: - Sections

    private var vehicleHeader: some View {
        HStack(spacing: Theme.Spacing.sm) {
            VehicleGlyph()
                .frame(width: 64, height: 44)

            VStack(alignment: .leading, spacing: 2) {
                Text(vehicle.displayName)
                    .font(Theme.Typography.callout)
                    .foregroundStyle(Theme.Colours.textPrimary)
                    .lineLimit(1)
                Text(vehicle.specificationSummary)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colours.textSecondary)
                    .lineLimit(1)
            }

            Spacer(minLength: 0)

            if let latestScore {
                VStack(spacing: 2) {
                    ScoreBadge(score: latestScore, size: 40)
                    Text("Güven Skoru")
                        .font(.system(size: 9))
                        .foregroundStyle(Theme.Colours.textSecondary)
                }
            }
        }
        .padding(Theme.Spacing.sm)
        .background(Theme.Colours.surface)
        .overlay(alignment: .bottom) {
            Rectangle().fill(Theme.Colours.border).frame(height: 1)
        }
    }

    private func transcript(_ thread: CopilotThread) -> some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                    if !model.isAvailable {
                        unavailableNotice
                    }

                    if model.showsPrompts {
                        promptDeck
                    }

                    ForEach(thread.messages) { message in
                        MessageBubble(message: message)
                            .id(message.id)
                    }

                    if model.isSending {
                        TypingIndicator()
                            .id(Self.typingAnchor)
                    }

                    if let error = model.sendError {
                        ErrorBanner(message: error)
                    }
                }
                .padding(.horizontal, Theme.Spacing.md)
                .padding(.vertical, Theme.Spacing.md)
            }
            .scrollDismissesKeyboard(.interactively)
            .onChange(of: thread.messages.count) { _, _ in
                // Keep the newest reply in view; a chat that leaves the answer
                // below the fold makes people think nothing happened.
                withAnimation(Theme.Motion.standard) {
                    proxy.scrollTo(thread.messages.last?.id, anchor: .bottom)
                }
            }
            .onChange(of: model.isSending) { _, sending in
                guard sending else { return }
                withAnimation(Theme.Motion.standard) {
                    proxy.scrollTo(Self.typingAnchor, anchor: .bottom)
                }
            }
        }
    }

    private static let typingAnchor = "typing"

    private var unavailableNotice: some View {
        Card {
            HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                Image(systemName: "sparkles.slash")
                    .foregroundStyle(Theme.Colours.warning)
                VStack(alignment: .leading, spacing: 2) {
                    Text("AI Copilot şu anda kullanılamıyor")
                        .font(Theme.Typography.callout)
                        .foregroundStyle(Theme.Colours.textPrimary)
                    Text("Bu kurulumda yapay zekâ desteği açık değil. "
                        + "Analiz raporların çalışmaya devam ediyor.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colours.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
        }
    }

    private var promptDeck: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text("Merhaba! Bu araç hakkında merak ettiğin her şeyi sorabilirsin.")
                .font(Theme.Typography.body)
                .foregroundStyle(Theme.Colours.textPrimary)
                .padding(Theme.Spacing.sm)
                .background(Theme.Colours.surface)
                .clipShape(
                    RoundedRectangle(cornerRadius: Theme.Radius.medium, style: .continuous)
                )

            SectionHeader("Hazır Sorular")

            ForEach(CopilotPrompt.allCases) { prompt in
                Button {
                    Task { await model.ask(prompt) }
                } label: {
                    HStack(spacing: Theme.Spacing.xs) {
                        Image(systemName: prompt.symbolName)
                            .font(.system(size: 13))
                            .foregroundStyle(Theme.Colours.brand)
                        Text(prompt.text)
                            .font(Theme.Typography.callout)
                            .foregroundStyle(Theme.Colours.textPrimary)
                            .multilineTextAlignment(.leading)
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, Theme.Spacing.sm)
                    .padding(.vertical, Theme.Spacing.xs)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.Colours.surface)
                    .overlay(
                        Capsule().stroke(Theme.Colours.border, lineWidth: 1)
                    )
                    .clipShape(Capsule())
                }
                .buttonStyle(.plain)
                .disabled(!model.isAvailable || model.isSending)
                .opacity(model.isAvailable ? 1 : 0.5)
            }
        }
    }

    private var composer: some View {
        VStack(spacing: 0) {
            Rectangle().fill(Theme.Colours.border).frame(height: 1)

            HStack(spacing: Theme.Spacing.xs) {
                TextField("AI'ya soru sor…", text: $model.draft, axis: .vertical)
                    .font(Theme.Typography.body)
                    .foregroundStyle(Theme.Colours.textPrimary)
                    .lineLimit(1...4)
                    .padding(.horizontal, Theme.Spacing.md)
                    .padding(.vertical, Theme.Spacing.sm)
                    .background(Theme.Colours.surfaceElevated)
                    .clipShape(Capsule())
                    .disabled(!model.isAvailable)

                Button {
                    Task { await model.send() }
                } label: {
                    Image(systemName: "arrow.up")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(Theme.Colours.textOnBrand)
                        .frame(width: 44, height: 44)
                        .background(
                            model.canSend
                                ? AnyShapeStyle(Theme.Colours.brandGradient)
                                : AnyShapeStyle(Theme.Colours.surfaceElevated),
                            in: Circle()
                        )
                }
                .disabled(!model.canSend)
                .accessibilityLabel("Gönder")
            }
            .padding(.horizontal, Theme.Spacing.md)
            .padding(.vertical, Theme.Spacing.xs)
        }
        .background(Theme.Colours.background)
    }
}

// MARK: - Components

private struct MessageBubble: View {
    let message: CopilotMessage

    private var isUser: Bool { message.role == .user }

    var body: some View {
        HStack(alignment: .top, spacing: Theme.Spacing.xs) {
            if isUser {
                Spacer(minLength: Theme.Spacing.xl)
            } else {
                assistantAvatar
            }

            VStack(alignment: isUser ? .trailing : .leading, spacing: 3) {
                Text(message.content)
                    .font(Theme.Typography.body)
                    .foregroundStyle(
                        isUser ? Theme.Colours.textOnBrand : Theme.Colours.textPrimary
                    )
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, Theme.Spacing.sm)
                    .padding(.vertical, Theme.Spacing.xs)
                    .background {
                        if isUser {
                            RoundedRectangle(
                                cornerRadius: Theme.Radius.medium, style: .continuous
                            )
                            .fill(Theme.Colours.brandGradient)
                        } else {
                            RoundedRectangle(
                                cornerRadius: Theme.Radius.medium, style: .continuous
                            )
                            .fill(Theme.Colours.surface)
                        }
                    }

                Text(message.createdAt.formatted(.dateTime.hour().minute()))
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.Colours.textSecondary)
            }

            if !isUser {
                Spacer(minLength: Theme.Spacing.xl)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(isUser ? "Sen: \(message.content)" : "Truvix AI: \(message.content)")
    }

    private var assistantAvatar: some View {
        Text("T")
            .font(.system(size: 13, weight: .bold))
            .foregroundStyle(Theme.Colours.textOnBrand)
            .frame(width: 28, height: 28)
            .background(Theme.Colours.brandGradient, in: Circle())
            .accessibilityHidden(true)
    }
}

/// The three-dot pulse shown while the model is composing a reply.
private struct TypingIndicator: View {
    @State private var phase = 0.0

    var body: some View {
        HStack(spacing: Theme.Spacing.xs) {
            Text("T")
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(Theme.Colours.textOnBrand)
                .frame(width: 28, height: 28)
                .background(Theme.Colours.brandGradient, in: Circle())

            HStack(spacing: 4) {
                ForEach(0..<3, id: \.self) { index in
                    Circle()
                        .fill(Theme.Colours.textSecondary)
                        .frame(width: 6, height: 6)
                        .opacity(opacity(for: index))
                }
            }
            .padding(.horizontal, Theme.Spacing.sm)
            .padding(.vertical, Theme.Spacing.sm)
            .background(Theme.Colours.surface)
            .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.medium, style: .continuous))

            Spacer(minLength: 0)
        }
        .task {
            // A continuous animation rather than a spinner: it reads as "still
            // writing" rather than "still loading", which is what is happening.
            withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) {
                phase = 1
            }
        }
        .accessibilityLabel("Truvix AI yanıt yazıyor")
    }

    private func opacity(for index: Int) -> Double {
        let offset = Double(index) * 0.25
        return 0.35 + 0.65 * abs(sin((phase + offset) * .pi))
    }
}
