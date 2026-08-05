import UIKit

/// Reduces a picked photograph before it is uploaded.
///
/// A phone photograph is several megabytes. Uploading it whole costs the user
/// their data allowance, costs the platform storage, and buys nothing: the
/// server reduces every image again before a model looks at it. Shrinking here
/// makes the upload fast enough to feel instant on a mobile connection.
///
/// The server still reduces what it receives. A client can be replaced, and an
/// analysis whose quality depends on the caller having behaved is not a
/// controlled analysis — this is an optimisation, not the enforcement.
enum ImagePreparation {

    /// Wide enough that panel damage stays legible after the server's own
    /// reduction, small enough to upload quickly.
    static let maximumDimension: CGFloat = 1600

    /// High enough to preserve paint defects, low enough for a small payload.
    static let compressionQuality: CGFloat = 0.8

    /// Prepare picked data for upload.
    ///
    /// - Parameter data: The bytes as the picker supplied them.
    /// - Returns: JPEG data ready to upload, or `nil` when the bytes are not a
    ///   readable image so the caller can skip the file.
    static func prepareForUpload(_ data: Data) -> Data? {
        guard let image = UIImage(data: data) else { return nil }

        let resized = resize(image, fitting: maximumDimension)
        return resized.jpegData(compressionQuality: compressionQuality)
    }

    /// Scale an image to fit within a square of the given side, never up.
    ///
    /// `UIImage` already carries the orientation from the picker, and drawing
    /// through a renderer bakes it in — so the uploaded file is the right way
    /// up rather than relying on the server to read EXIF.
    private static func resize(_ image: UIImage, fitting side: CGFloat) -> UIImage {
        let longestSide = max(image.size.width, image.size.height)
        guard longestSide > side else { return image }

        let scale = side / longestSide
        let target = CGSize(
            width: (image.size.width * scale).rounded(),
            height: (image.size.height * scale).rounded()
        )

        let format = UIGraphicsImageRendererFormat.default()
        // The output is a file, not a screen, so a device's pixel density must
        // not multiply the dimensions back up.
        format.scale = 1
        format.opaque = true

        return UIGraphicsImageRenderer(size: target, format: format).image { _ in
            image.draw(in: CGRect(origin: .zero, size: target))
        }
    }
}
