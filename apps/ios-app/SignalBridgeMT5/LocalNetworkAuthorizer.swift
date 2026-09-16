import Foundation
import Network

private final class ContinuationGate: @unchecked Sendable {
    private let lock = NSLock()
    private var resumed = false
    private let continuation: CheckedContinuation<Void, Never>
    private let cleanup: () -> Void

    init(continuation: CheckedContinuation<Void, Never>, cleanup: @escaping () -> Void) {
        self.continuation = continuation
        self.cleanup = cleanup
    }

    func finish() {
        lock.lock()
        defer { lock.unlock() }
        guard !resumed else { return }
        resumed = true
        cleanup()
        continuation.resume()
    }
}

enum LocalNetworkAuthorizer {
    /// iOS only registers Local Network privacy (and shows the Allow dialog) after
    /// Bonjour browse or an explicit local endpoint connection — plain URLSession
    /// to a LAN IP often fails silently without appearing in Settings.
    static func requestAccess(host: String) async {
        let normalizedHost = normalizeHost(host)
        guard !normalizedHost.isEmpty, isPrivateLANHost(normalizedHost) else { return }

        async let bonjour: Void = browseBonjour(timeoutSeconds: 2.5)
        async let tcp5173: Void = probeTCP(host: normalizedHost, port: 5173, timeoutSeconds: 2.0)
        async let tcp8000: Void = probeTCP(host: normalizedHost, port: 8000, timeoutSeconds: 2.0)
        _ = await (bonjour, tcp5173, tcp8000)
        // Give the system a moment to surface the permission alert if needed.
        try? await Task.sleep(nanoseconds: 400_000_000)
    }

    private static func browseBonjour(timeoutSeconds: Double) async {
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            let browser = NWBrowser(for: .bonjour(type: "_http._tcp", domain: nil), using: .tcp)
            let gate = ContinuationGate(continuation: continuation) {
                browser.cancel()
            }

            browser.stateUpdateHandler = { state in
                switch state {
                case .ready, .failed, .cancelled:
                    gate.finish()
                default:
                    break
                }
            }
            browser.browseResultsChangedHandler = { _, _ in
                gate.finish()
            }
            browser.start(queue: .global(qos: .userInitiated))
            DispatchQueue.global(qos: .userInitiated).asyncAfter(deadline: .now() + timeoutSeconds) {
                gate.finish()
            }
        }
    }

    private static func probeTCP(host: String, port: UInt16, timeoutSeconds: Double) async {
        let hostPart = host.split(separator: ":", maxSplits: 1).first.map(String.init) ?? host
        guard let nwPort = NWEndpoint.Port(rawValue: port) else { return }

        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            let connection = NWConnection(
                host: NWEndpoint.Host(hostPart),
                port: nwPort,
                using: .tcp
            )
            let gate = ContinuationGate(continuation: continuation) {
                connection.cancel()
            }

            connection.stateUpdateHandler = { state in
                switch state {
                case .ready, .failed, .cancelled:
                    gate.finish()
                default:
                    break
                }
            }
            connection.start(queue: .global(qos: .userInitiated))
            DispatchQueue.global(qos: .userInitiated).asyncAfter(deadline: .now() + timeoutSeconds) {
                gate.finish()
            }
        }
    }
}
