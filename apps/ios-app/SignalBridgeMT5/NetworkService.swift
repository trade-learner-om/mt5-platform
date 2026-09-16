import Foundation

final class NetworkService {
    static let shared = NetworkService()
    private init() {}

    private lazy var session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 60
        config.timeoutIntervalForResource = 120
        config.waitsForConnectivity = false
        return URLSession(configuration: config)
    }()

    private lazy var lanPingSession: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 20
        config.timeoutIntervalForResource = 20
        config.waitsForConnectivity = false
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSession(configuration: config)
    }()

    func pingFrontend(_ host: String) async -> PingResult {
        guard let url = URL(string: frontendBase(host)) else {
            return PingResult(ok: false, statusCode: nil, error: "Invalid host URL.")
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = 20
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("SignalBridgeMT5/1.0", forHTTPHeaderField: "User-Agent")
        let client = isPrivateLANHost(host) ? lanPingSession : session
        do {
            let (_, response) = try await client.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                return PingResult(ok: false, statusCode: nil, error: "No HTTP response.")
            }
            let ok = http.statusCode < 500
            return PingResult(
                ok: ok,
                statusCode: http.statusCode,
                error: ok ? nil : "Server returned HTTP \(http.statusCode)."
            )
        } catch {
            return PingResult(ok: false, statusCode: nil, error: error.localizedDescription)
        }
    }

    func pingApi(_ apiBase: String) async -> PingResult {
        guard let url = URL(string: "\(apiBase)/health") else {
            return PingResult(ok: false, statusCode: nil, error: "Invalid API URL.")
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = 20
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("SignalBridgeMT5/1.0", forHTTPHeaderField: "User-Agent")
        let host = URL(string: apiBase)?.host ?? apiBase
        let client = isPrivateLANHost(host) ? lanPingSession : session
        do {
            let (_, response) = try await client.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                return PingResult(ok: false, statusCode: nil, error: "No HTTP response.")
            }
            let ok = (200..<300).contains(http.statusCode)
            return PingResult(
                ok: ok,
                statusCode: http.statusCode,
                error: ok ? nil : "Backend health returned HTTP \(http.statusCode)."
            )
        } catch {
            return PingResult(ok: false, statusCode: nil, error: error.localizedDescription)
        }
    }

    func request(path: String, method: String = "GET", body: [String: Any]? = nil, apiBase: String, token: String) async throws -> [String: Any] {
        guard let url = URL(string: "\(apiBase)\(path)") else { throw ApiError.invalidResponse }
        var request = URLRequest(url: url)
        request.httpMethod = method.uppercased()
        request.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        if !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body, method.uppercased() != "GET" {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw ApiError.invalidResponse }
        if !(200..<300).contains(http.statusCode) {
            let detail = (try? JsonParsers.jsonObject(from: data))?["detail"].map { String(describing: $0) } ?? HTTPURLResponse.localizedString(forStatusCode: http.statusCode)
            throw ApiError.http(status: http.statusCode, detail: "HTTP \(http.statusCode): \(detail)")
        }
        if data.isEmpty { return [:] }
        if let text = String(data: data, encoding: .utf8), text.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix("[") {
            let array = try JsonParsers.jsonArray(from: data)
            return ["__array": array]
        }
        return try JsonParsers.jsonObject(from: data)
    }

    func requestArray(path: String, apiBase: String, token: String) async throws -> [[String: Any]] {
        let payload = try await request(path: path, apiBase: apiBase, token: token)
        return payload["__array"] as? [[String: Any]] ?? []
    }
}

final class LiveWebSocket: NSObject, URLSessionWebSocketDelegate {
    static let heartbeatInterval: TimeInterval = 20

    var onMessage: ((String) -> Void)?
    var onConnected: (() -> Void)?
    var onDisconnected: (() -> Void)?

    private var task: URLSessionWebSocketTask?
    private var session: URLSession?
    private let delegateQueue: OperationQueue = {
        let queue = OperationQueue()
        queue.maxConcurrentOperationCount = 1
        queue.name = "SignalBridge.LiveWebSocket"
        return queue
    }()
    private var generation = 0
    private var heartbeatTimer: Timer?
    private var connectedNotified = false
    private var intentionalClose = false

    func connect(wsBase: String, token: String) {
        intentionalClose = false
        connectedNotified = false
        generation += 1
        let currentGeneration = generation
        stopHeartbeat()
        task?.cancel(with: .goingAway, reason: nil)
        task = nil

        guard var components = URLComponents(string: "\(wsBase)/ws/live") else { return }
        components.queryItems = [URLQueryItem(name: "token", value: token)]
        guard let url = components.url else { return }

        if session == nil {
            let config = URLSessionConfiguration.default
            config.timeoutIntervalForRequest = 60
            config.timeoutIntervalForResource = 120
            config.waitsForConnectivity = true
            session = URLSession(configuration: config, delegate: self, delegateQueue: delegateQueue)
        }

        task = session?.webSocketTask(with: url)
        task?.resume()
        receiveLoop(generation: currentGeneration)
    }

    func disconnect(intentional: Bool = false) {
        intentionalClose = intentional
        connectedNotified = false
        generation += 1
        stopHeartbeat()
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        session?.invalidateAndCancel()
        session = nil
    }

    func send(_ text: String) {
        task?.send(.string(text)) { _ in }
    }

    func sendPing() {
        send("{\"type\":\"ping\"}")
    }

    private func notifyConnectedIfNeeded() {
        guard !connectedNotified else { return }
        connectedNotified = true
        DispatchQueue.main.async { self.onConnected?() }
    }

    private func deliverDisconnectedIfNeeded() {
        guard !intentionalClose else {
            intentionalClose = false
            return
        }
        guard connectedNotified else { return }
        connectedNotified = false
        DispatchQueue.main.async { self.onDisconnected?() }
    }

    private func startHeartbeat() {
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.stopHeartbeat()
            self.heartbeatTimer = Timer.scheduledTimer(withTimeInterval: Self.heartbeatInterval, repeats: true) { [weak self] _ in
                self?.sendPing()
            }
        }
    }

    private func stopHeartbeat() {
        DispatchQueue.main.async { [weak self] in
            self?.heartbeatTimer?.invalidate()
            self?.heartbeatTimer = nil
        }
    }

    private func receiveLoop(generation: Int) {
        task?.receive { [weak self] result in
            guard let self, generation == self.generation else { return }
            switch result {
            case .success(let message):
                if case .string(let text) = message {
                    if let data = text.data(using: .utf8),
                       let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                       let type = payload["type"] as? String {
                        let normalized = type.lowercased()
                        if normalized == "ping" {
                            self.send("{\"type\":\"pong\"}")
                            self.receiveLoop(generation: generation)
                            return
                        }
                        if normalized == "pong" {
                            self.receiveLoop(generation: generation)
                            return
                        }
                    }
                    self.notifyConnectedIfNeeded()
                    DispatchQueue.main.async { self.onMessage?(text) }
                }
                self.receiveLoop(generation: generation)
            case .failure:
                self.deliverDisconnectedIfNeeded()
            }
        }
    }

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didOpenWithProtocol protocol: String?) {
        guard session === self.session, webSocketTask === self.task else { return }
        send("ready")
        startHeartbeat()
        notifyConnectedIfNeeded()
    }

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?) {
        guard session === self.session else { return }
        stopHeartbeat()
        deliverDisconnectedIfNeeded()
    }
}
