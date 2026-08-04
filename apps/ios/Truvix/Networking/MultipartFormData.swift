import Foundation

/// Builds a `multipart/form-data` body.
///
/// Written by hand rather than pulled from a dependency: the format is a few
/// lines of well-specified text framing, and an upload path is exactly the
/// place where an opaque third-party encoder becomes hard to debug.
struct MultipartFormData: Sendable {
    /// A boundary that cannot appear inside binary content by chance.
    private let boundary = "truvix.\(UUID().uuidString)"
    private var body = Data()

    var contentType: String {
        "multipart/form-data; boundary=\(boundary)"
    }

    /// Add a plain text field.
    mutating func append(_ value: String, name: String) {
        body.append("--\(boundary)\r\n")
        body.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n")
        body.append("\(value)\r\n")
    }

    /// Add a file.
    ///
    /// The filename is sent for display only; the backend decides the real
    /// type by inspecting the bytes, so a wrong extension here changes nothing.
    mutating func append(
        _ data: Data,
        name: String,
        filename: String,
        contentType: String
    ) {
        body.append("--\(boundary)\r\n")
        body.append(
            "Content-Disposition: form-data; name=\"\(name)\"; filename=\"\(filename)\"\r\n"
        )
        body.append("Content-Type: \(contentType)\r\n\r\n")
        body.append(data)
        body.append("\r\n")
    }

    /// Close the body. Must be called exactly once, after every part is added.
    func finalised() -> Data {
        var closed = body
        closed.append("--\(boundary)--\r\n")
        return closed
    }
}

private extension Data {
    /// Append text as UTF-8, which every part of the framing is.
    mutating func append(_ text: String) {
        append(Data(text.utf8))
    }
}
