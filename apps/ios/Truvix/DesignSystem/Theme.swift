import SwiftUI

/// The colour, spacing and typography values every Truvix screen draws from.
///
/// Values are defined once here rather than inline at call sites, so a brand
/// change is one edit and a screen cannot quietly drift from the design. The
/// palette is taken directly from the design files' colour specification.
enum Theme {

    // MARK: - Colour

    enum Colours {
        /// The near-black the app sits on.
        static let background = Color(hex: 0x0B0F0D)
        /// Cards and grouped rows, one step above the background.
        static let surface = Color(hex: 0x111817)
        /// A raised element on top of a surface, such as an inner tile.
        static let surfaceElevated = Color(hex: 0x18211F)
        /// The deep brand green used for filled controls.
        static let brand = Color(hex: 0x16C47F)
        /// The lighter green used for emphasis and gradient tops.
        static let brandBright = Color(hex: 0x22E29D)
        /// A pale green for subtle highlights on dark surfaces.
        static let brandSoft = Color(hex: 0xA8F5D0)

        static let textPrimary = Color.white
        static let textSecondary = Color(hex: 0x8A8F95)
        /// Text on top of a filled brand control.
        static let textOnBrand = Color(hex: 0x06231A)

        static let border = Color.white.opacity(0.08)
        static let danger = Color(hex: 0xFF5A5A)
        static let warning = Color(hex: 0xFFB020)

        /// The gradient used on primary buttons and hero cards.
        static let brandGradient = LinearGradient(
            colors: [brandBright, brand],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    // MARK: - Spacing

    /// A four-point scale. Using steps rather than arbitrary numbers is what
    /// keeps rhythm consistent between screens built at different times.
    enum Spacing {
        static let xxs: CGFloat = 4
        static let xs: CGFloat = 8
        static let sm: CGFloat = 12
        static let md: CGFloat = 16
        static let lg: CGFloat = 24
        static let xl: CGFloat = 32
        static let xxl: CGFloat = 48
    }

    // MARK: - Radius

    enum Radius {
        static let small: CGFloat = 10
        static let medium: CGFloat = 16
        static let large: CGFloat = 22
        static let pill: CGFloat = 999
    }

    // MARK: - Typography

    /// Every style is built from a semantic text style, so it grows with the
    /// reader's Dynamic Type setting.
    ///
    /// This is deliberate and load-bearing. `Font.system(size:)` produces a
    /// fixed size that ignores Dynamic Type entirely, and nothing at the call
    /// site reveals it — a design system can claim to scale for months while
    /// every screen stays pinned at one size. The text styles below happen to
    /// resolve to the design's specified sizes at the default setting, so
    /// fidelity is unchanged and accessibility is gained. `DynamicTypeTests`
    /// measures this rather than trusting it.
    ///
    /// | Token        | Style        | Default size |
    /// | ------------ | ------------ | ------------ |
    /// | displayLarge | largeTitle   | 34 |
    /// | display      | title        | 28 |
    /// | title        | title2       | 22 |
    /// | headline     | headline     | 17 |
    /// | body         | callout      | 16 |
    /// | callout      | subheadline  | 15 |
    /// | caption      | footnote     | 13 |
    /// | label        | caption      | 12 |
    enum Typography {
        static let displayLarge = Font.system(.largeTitle, design: .default, weight: .bold)
        static let display = Font.system(.title, design: .default, weight: .bold)
        static let title = Font.system(.title2, design: .default, weight: .semibold)
        static let headline = Font.system(.headline, design: .default, weight: .semibold)
        static let body = Font.system(.callout, design: .default, weight: .regular)
        static let callout = Font.system(.subheadline, design: .default, weight: .medium)
        static let caption = Font.system(.footnote, design: .default, weight: .regular)
        static let label = Font.system(.caption, design: .default, weight: .semibold)

        /// Monospaced digits keep prices and scores from shifting as they change.
        static let score = Font.system(.title, design: .rounded, weight: .bold)
            .monospacedDigit()

        /// The smallest label the design uses, for badge counts and axis ticks.
        static let micro = Font.system(.caption2, design: .default, weight: .medium)

        /// A bold variant of `micro`, for counts that must stand out.
        static let microBold = Font.system(.caption2, design: .default, weight: .bold)
    }

    // MARK: - Motion

    enum Motion {
        static let quick = Animation.easeOut(duration: 0.2)
        static let standard = Animation.easeInOut(duration: 0.32)
        static let spring = Animation.spring(response: 0.42, dampingFraction: 0.82)
    }
}

extension Color {
    /// Build a colour from a packed 24-bit RGB literal, as the design files list them.
    ///
    /// - Parameter hex: A value such as `0x16C47F`.
    init(hex: UInt32) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: 1
        )
    }
}
