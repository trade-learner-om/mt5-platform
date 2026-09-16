import Foundation

final class SessionStore {
    static let shared = SessionStore()
    private let defaults = UserDefaults.standard
    private let tokenKey = "signalbridge_jwt_token"
    private let appearanceKey = "signalbridge_appearance"

    var savedToken: String {
        get { defaults.string(forKey: tokenKey) ?? "" }
        set { defaults.set(newValue, forKey: tokenKey) }
    }

    var savedAppearance: AppAppearance {
        get {
            guard let raw = defaults.string(forKey: appearanceKey), let appearance = AppAppearance(rawValue: raw) else {
                return .system
            }
            return appearance
        }
        set { defaults.set(newValue.rawValue, forKey: appearanceKey) }
    }

    func clearToken() {
        defaults.removeObject(forKey: tokenKey)
    }
}
