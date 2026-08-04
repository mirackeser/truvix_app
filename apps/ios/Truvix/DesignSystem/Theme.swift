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

    /// Every style resolves through `Font.system`, which is SF Pro on Apple
    /// platforms and, unlike a bundled font file, scales with the reader's
    /// Dynamic Type setting.
    enum Typography {
        static let displayLarge = Font.system(size: 34, weight: .bold, design: .default)
        static let display = Font.system(size: 28, weight: .bold, design: .default)
        static let title = Font.system(size: 22, weight: .semibold, design: .default)
        static let headline = Font.system(size: 17, weight: .semibold, design: .default)
        static let body = Font.system(size: 16, weight: .regular, design: .default)
        static let callout = Font.system(size: 15, weight: .medium, design: .default)
        static let caption = Font.system(size: 13, weight: .regular, design: .default)
        static let label = Font.system(size: 12, weight: .semibold, design: .default)
        /// Monospaced digits keep prices and scores from shifting as they change.
        static let score = Font.system(size: 28, weight: .bold, design: .rounded)
            .monospacedDigit()
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
