import Foundation

enum AppConfig {
    static let fixedHost = "api.signalbridge.in"
    static let fixedApiBase = "https://api.signalbridge.in"

    static var platformHost: String {
        fixedHost
    }

    static var fixedHostIPAddress: String {
        hostIPAddress(fixedHost)
    }
}
