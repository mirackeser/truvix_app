import SwiftUI
import Testing
import UIKit

@testable import Truvix

/// Verifies the app actually honours the reader's text size.
///
/// This is measured rather than asserted, because the failure mode is silent:
/// `Font.system(size:)` produces a fixed size that ignores Dynamic Type
/// entirely, and nothing about the call site says so. A design system can
/// claim to scale for months while every screen stays pinned at one size.
@Suite("Dynamic Type")
@MainActor
struct DynamicTypeTests {

    /// Render a label at a content size and report the height it takes.
    private func renderedHeight(
        font: Font,
        contentSize: ContentSizeCategory
    ) -> CGFloat {
        let label = Text("Güven Skoru")
            .font(font)
            .environment(\.sizeCategory, contentSize)
            .fixedSize()

        let controller = UIHostingController(rootView: label)
        controller.view.setNeedsLayout()
        controller.view.layoutIfNeeded()
        return controller.sizeThatFits(in: CGSize(width: 1000, height: 1000)).height
    }

    private func scales(_ font: Font) -> Bool {
        let small = renderedHeight(font: font, contentSize: .small)
        let large = renderedHeight(font: font, contentSize: .accessibilityExtraExtraExtraLarge)
        return large > small
    }

    @Test("Every typography token grows with the reader's text size")
    func typographyScales() {
        let tokens: [(name: String, font: Font)] = [
            ("displayLarge", Theme.Typography.displayLarge),
            ("display", Theme.Typography.display),
            ("title", Theme.Typography.title),
            ("headline", Theme.Typography.headline),
            ("body", Theme.Typography.body),
            ("callout", Theme.Typography.callout),
            ("caption", Theme.Typography.caption),
            ("label", Theme.Typography.label),
        ]

        for token in tokens {
            #expect(scales(token.font), "\(token.name) does not respond to Dynamic Type")
        }
    }

    @Test("The score badge's figure scales too")
    func scoreScales() {
        // Numbers matter as much as prose: a trust score the reader cannot
        // make out is the one thing the app exists to communicate.
        #expect(scales(Theme.Typography.score))
    }

    @Test("A fixed-size font is confirmed not to scale")
    func fixedSizeIsTheFailureMode() {
        // Documents why the tokens are defined the way they are: this is what
        // the design system would silently be doing if it used raw sizes.
        #expect(!scales(Font.system(size: 16)))
    }
}

@Suite("Contrast")
struct ContrastTests {

    /// The relative luminance of a colour, per WCAG.
    private func luminance(_ components: (red: Double, green: Double, blue: Double)) -> Double {
        func channel(_ value: Double) -> Double {
            value <= 0.039_28 ? value / 12.92 : pow((value + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * channel(components.red)
            + 0.7152 * channel(components.green)
            + 0.0722 * channel(components.blue)
    }

    private func ratio(
        _ first: (red: Double, green: Double, blue: Double),
        _ second: (red: Double, green: Double, blue: Double)
    ) -> Double {
        let lighter = max(luminance(first), luminance(second))
        let darker = min(luminance(first), luminance(second))
        return (lighter + 0.05) / (darker + 0.05)
    }

    // The palette, as the design specifies it.
    private let background = (red: 0x0B / 255.0, green: 0x0F / 255.0, blue: 0x0D / 255.0)
    private let surface = (red: 0x11 / 255.0, green: 0x18 / 255.0, blue: 0x17 / 255.0)
    private let textPrimary = (red: 1.0, green: 1.0, blue: 1.0)
    private let textSecondary = (red: 0x8A / 255.0, green: 0x8F / 255.0, blue: 0x95 / 255.0)
    private let brand = (red: 0x16 / 255.0, green: 0xC4 / 255.0, blue: 0x7F / 255.0)
    private let textOnBrand = (red: 0x06 / 255.0, green: 0x23 / 255.0, blue: 0x1A / 255.0)

    /// WCAG AA for body text.
    private let normalTextMinimum = 4.5
    /// WCAG AA for text at 18pt and above, and for interface components.
    private let largeTextMinimum = 3.0

    @Test("Primary text clears AA on both surfaces")
    func primaryTextIsReadable() {
        #expect(ratio(textPrimary, background) >= normalTextMinimum)
        #expect(ratio(textPrimary, surface) >= normalTextMinimum)
    }

    @Test("Secondary text clears AA on both surfaces")
    func secondaryTextIsReadable() {
        // Secondary text carries real content — specifications, timestamps,
        // price movements — so it is held to the body-text threshold, not the
        // looser one for decoration.
        #expect(ratio(textSecondary, background) >= normalTextMinimum)
        #expect(ratio(textSecondary, surface) >= normalTextMinimum)
    }

    @Test("Brand green clears AA against the background")
    func brandIsReadable() {
        #expect(ratio(brand, background) >= normalTextMinimum)
    }

    @Test("Text on a filled brand control clears AA")
    func textOnBrandIsReadable() {
        #expect(ratio(textOnBrand, brand) >= normalTextMinimum)
    }

    @Test("The brand colour is distinguishable as a control against the surface")
    func brandIsDistinguishableAsAControl() {
        #expect(ratio(brand, surface) >= largeTextMinimum)
    }
}

@Suite("Upload preparation")
@MainActor
struct ImagePreparationTests {

    private func image(width: Int, height: Int) -> Data {
        let size = CGSize(width: width, height: height)
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1
        let rendered = UIGraphicsImageRenderer(size: size, format: format).image { context in
            UIColor(red: 0.08, green: 0.7, blue: 0.5, alpha: 1).setFill()
            context.fill(CGRect(origin: .zero, size: size))
        }
        return rendered.pngData()!
    }

    private func dimensions(of data: Data) -> CGSize? {
        UIImage(data: data)?.size
    }

    @Test("A large photograph is reduced before upload")
    func largePhotographIsReduced() throws {
        let prepared = try #require(
            ImagePreparation.prepareForUpload(image(width: 4032, height: 3024))
        )

        let size = try #require(dimensions(of: prepared))
        #expect(max(size.width, size.height) == ImagePreparation.maximumDimension)
    }

    @Test("The aspect ratio survives the reduction")
    func aspectRatioSurvives() throws {
        let prepared = try #require(
            ImagePreparation.prepareForUpload(image(width: 4000, height: 2000))
        )

        let size = try #require(dimensions(of: prepared))
        #expect(size.width == ImagePreparation.maximumDimension)
        #expect(size.height == ImagePreparation.maximumDimension / 2)
    }

    @Test("A small photograph is not enlarged")
    func smallPhotographIsUntouched() throws {
        let prepared = try #require(
            ImagePreparation.prepareForUpload(image(width: 320, height: 240))
        )

        let size = try #require(dimensions(of: prepared))
        #expect(size == CGSize(width: 320, height: 240))
    }

    @Test("Preparation shrinks the payload")
    func payloadShrinks() throws {
        // The point of the exercise: a mobile upload that finishes quickly.
        let original = image(width: 4032, height: 3024)

        let prepared = try #require(ImagePreparation.prepareForUpload(original))

        #expect(prepared.count < original.count)
    }

    @Test("Bytes that are not an image are refused")
    func nonImageIsRefused() {
        // Returned as nil so the picker skips the file rather than uploading
        // something the backend will reject anyway.
        #expect(ImagePreparation.prepareForUpload(Data("not an image".utf8)) == nil)
    }
}
