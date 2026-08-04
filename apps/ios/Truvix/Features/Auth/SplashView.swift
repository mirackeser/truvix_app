import SwiftUI

/// The first screen after launch, shown while the stored session is verified.
///
/// The animation is deliberately short and non-blocking: it covers the session
/// check rather than adding time to it, so a returning user reaches the home
/// screen as soon as the backend answers.
struct SplashView: View {
    @State private var logoAppeared = false
    @State private var wordmarkAppeared = false
    @State private var progress: CGFloat = 0

    var body: some View {
        ZStack {
            Theme.Colours.background.ignoresSafeArea()
            NetworkBackdrop()
                .ignoresSafeArea()
                .opacity(logoAppeared ? 1 : 0)

            VStack(spacing: Theme.Spacing.lg) {
                Spacer()

                VStack(spacing: Theme.Spacing.sm) {
                    TruvixMark()
                        .frame(width: 92, height: 92)
                        .opacity(logoAppeared ? 1 : 0)
                        .scaleEffect(logoAppeared ? 1 : 0.82)

                    Text("TRUVIX")
                        .font(.system(size: 34, weight: .light))
                        .kerning(10)
                        .foregroundStyle(Theme.Colours.textPrimary)
                        .opacity(wordmarkAppeared ? 1 : 0)

                    Text("AI ARAÇ DANIŞMANINIZ")
                        .font(Theme.Typography.label)
                        .kerning(3)
                        .foregroundStyle(Theme.Colours.brand)
                        .opacity(wordmarkAppeared ? 1 : 0)
                }

                Spacer()

                VStack(spacing: Theme.Spacing.md) {
                    Text("Karar vermeden önce")
                        .font(Theme.Typography.title)
                        .foregroundStyle(Theme.Colours.textPrimary)
                    + Text("\nTruvix")
                        .font(Theme.Typography.title)
                        .foregroundStyle(Theme.Colours.brand)
                    + Text("'e sor.")
                        .font(Theme.Typography.title)
                        .foregroundStyle(Theme.Colours.textPrimary)

                    ProgressTrack(progress: progress)
                        .frame(height: 3)
                        .padding(.horizontal, Theme.Spacing.xxl)

                    Text("YAPAY ZEKÂ HAZIRLANIYOR")
                        .font(Theme.Typography.label)
                        .kerning(2)
                        .foregroundStyle(Theme.Colours.textSecondary)
                }
                .multilineTextAlignment(.center)
                .opacity(wordmarkAppeared ? 1 : 0)
                .padding(.bottom, Theme.Spacing.xxl)
            }
            .padding(.horizontal, Theme.Spacing.lg)
        }
        .task {
            withAnimation(Theme.Motion.spring) { logoAppeared = true }
            try? await Task.sleep(for: .milliseconds(280))
            withAnimation(Theme.Motion.standard) { wordmarkAppeared = true }
            withAnimation(.easeInOut(duration: 1.6)) { progress = 1 }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Truvix açılıyor")
    }
}

/// The angular "T" from the brand mark, drawn as a shape so it stays crisp at
/// any size and needs no image asset.
private struct TruvixMark: View {
    var body: some View {
        GeometryReader { proxy in
            let side = min(proxy.size.width, proxy.size.height)
            let unit = side / 100

            ZStack {
                // The horizontal bar, sheared to match the mark's italic cut.
                Path { path in
                    path.move(to: CGPoint(x: 12 * unit, y: 16 * unit))
                    path.addLine(to: CGPoint(x: 88 * unit, y: 16 * unit))
                    path.addLine(to: CGPoint(x: 78 * unit, y: 38 * unit))
                    path.addLine(to: CGPoint(x: 2 * unit, y: 38 * unit))
                    path.closeSubpath()
                }
                // The descending stem.
                Path { path in
                    path.move(to: CGPoint(x: 44 * unit, y: 16 * unit))
                    path.addLine(to: CGPoint(x: 66 * unit, y: 16 * unit))
                    path.addLine(to: CGPoint(x: 52 * unit, y: 92 * unit))
                    path.addLine(to: CGPoint(x: 30 * unit, y: 92 * unit))
                    path.closeSubpath()
                }
            }
            .foregroundStyle(Theme.Colours.brandGradient)
            .shadow(color: Theme.Colours.brand.opacity(0.55), radius: 18)
        }
        .accessibilityHidden(true)
    }
}

/// The determinate loading bar under the wordmark.
private struct ProgressTrack: View {
    let progress: CGFloat

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                Capsule().fill(Theme.Colours.surfaceElevated)
                Capsule()
                    .fill(Theme.Colours.brandGradient)
                    .frame(width: proxy.size.width * progress)
            }
        }
        .accessibilityHidden(true)
    }
}

/// The faint constellation behind the mark, evoking the AI network graphic in
/// the design without shipping a large image.
private struct NetworkBackdrop: View {
    private let nodes: [CGPoint] = (0..<26).map { index in
        // A fixed pseudo-random layout: deterministic, so the backdrop does not
        // reshuffle on every redraw, and cheap, because it is computed once.
        let angle = Double(index) * 2.399_963
        let radius = Double(index).squareRoot() / 5.2
        return CGPoint(
            x: 0.5 + cos(angle) * radius,
            y: 0.62 + sin(angle) * radius * 0.55
        )
    }

    var body: some View {
        Canvas { context, size in
            let points = nodes.map { CGPoint(x: $0.x * size.width, y: $0.y * size.height) }

            for (index, point) in points.enumerated() {
                for other in points[(index + 1)...] where distance(point, other) < size.width * 0.22 {
                    var line = Path()
                    line.move(to: point)
                    line.addLine(to: other)
                    context.stroke(
                        line,
                        with: .color(Theme.Colours.brand.opacity(0.16)),
                        lineWidth: 0.6
                    )
                }
                context.fill(
                    Path(ellipseIn: CGRect(x: point.x - 1.6, y: point.y - 1.6, width: 3.2, height: 3.2)),
                    with: .color(Theme.Colours.brandBright.opacity(0.5))
                )
            }
        }
        .accessibilityHidden(true)
    }

    private func distance(_ a: CGPoint, _ b: CGPoint) -> CGFloat {
        hypot(a.x - b.x, a.y - b.y)
    }
}

#Preview {
    SplashView()
}
