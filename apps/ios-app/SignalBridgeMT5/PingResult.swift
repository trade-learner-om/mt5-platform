import Foundation

struct PingResult {
    let ok: Bool
    let statusCode: Int?
    let error: String?

    static let failed = PingResult(ok: false, statusCode: nil, error: nil)
}
