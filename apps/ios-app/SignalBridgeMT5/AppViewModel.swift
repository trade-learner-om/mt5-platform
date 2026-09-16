import Foundation
import LocalAuthentication
import UserNotifications

@MainActor
final class AppViewModel: ObservableObject {
    @Published var state = AppState()

    private let network = NetworkService.shared
    private let store = SessionStore.shared
    private let webSocket = LiveWebSocket()
    private var reconnectTask: Task<Void, Never>?
    private var reconnectAttempts = 0
    private var subscribedLiveSymbols = Set<String>()
    private var lastLiveDataAt = Date.distantPast
    private var staleWatchdogTask: Task<Void, Never>?
    private let liveStaleSeconds: TimeInterval = 45
    private var seenStrategyNotificationIds = Set<String>()
    private var strategyNotificationsPrimed = false
    private var liveSocketAttempt = 0

    init() {
        state.appearance = store.savedAppearance
        webSocket.onConnected = { [weak self] in
            Task { @MainActor in self?.handleSocketConnected() }
        }
        webSocket.onMessage = { [weak self] text in
            Task { @MainActor in self?.handleSocketMessage(text) }
        }
        webSocket.onDisconnected = { [weak self] in
            Task { @MainActor in self?.handleSocketDisconnected() }
        }
        Task { await bootstrap() }
    }

    func changePage(_ page: AppPage) {
        state.page = page
        state.strategySection = nil
        state.error = ""
    }

    func stepPage(_ offset: Int) {
        let pages = AppPage.allCases
        guard let currentIndex = pages.firstIndex(of: state.page) else { return }
        let nextIndex = min(max(currentIndex + offset, 0), pages.count - 1)
        guard nextIndex != currentIndex else { return }
        changePage(pages[nextIndex])
    }

    func openPositionsFromSummary() {
        state.page = .positions
        state.positionsTab = "Positions"
        state.strategySection = nil
        state.error = ""
    }

    func openOrderHistoryFromSummary() {
        state.page = .positions
        state.positionsTab = "History"
        state.strategySection = nil
        state.error = ""
    }

    func setPositionsTab(_ tab: String) { state.positionsTab = tab }

    func openStrategy(_ section: StrategySection) {
        state.page = .strategies
        state.strategySection = section
    }

    func closeStrategy() { state.strategySection = nil }

    func openTrade(symbol: String = "") {
        state.page = .trading
        state.tradeDraftSymbol = symbol.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        state.showTradeSheet = true
    }

    func showTradeForm() {
        state.page = .trading
        state.showTradeSheet = true
    }

    func closeTradeSheet() { state.showTradeSheet = false }

    func openOrderEditor(_ order: OrderRow) {
        state.orderEditTarget = order
        state.showOrderEditSheet = true
    }

    func closeOrderEditSheet() {
        state.showOrderEditSheet = false
        state.orderEditTarget = nil
    }

    func saveHostAndConnect() {
        Task { await bootstrap() }
    }

    func retryPlatformConnection() {
        Task { await bootstrap() }
    }

    func resetSavedLogin() {
        reconnectTask?.cancel()
        webSocket.disconnect(intentional: true)
        store.clearToken()
        configureHost()
        state.token = ""
        state.bootStatus = .authRequired
        state.bootLoading = false
        state.dashboardSyncing = false
        state.syncMessage = ""
        state.message = "Ready to sign in."
        state.error = ""
        state.liveStatus = "DISCONNECTED"
    }

    func login(username: String, password: String, register: Bool, fullName: String) {
        Task {
            let path = register ? "/auth/register" : "/auth/login"
            var body: [String: Any] = ["username": username.trimmingCharacters(in: .whitespacesAndNewlines), "password": password]
            if register { body["full_name"] = fullName.trimmingCharacters(in: .whitespacesAndNewlines) }
            state.bootLoading = true
            state.error = ""
            state.message = "Signing in..."
            do {
                let data = try await network.request(path: path, method: "POST", body: body, apiBase: state.apiBase, token: "")
                let token = data["access_token"] as? String ?? ""
                store.savedToken = token
                state.token = token
                state.fullName = data["full_name"] as? String ?? username
                state.username = data["username"] as? String ?? username
                state.bootStatus = .ready
                state.bootLoading = false
                state.dashboardSyncing = true
                state.syncMessage = "Opening dashboard..."
                await refreshDashboardInternal(showIndicator: true)
            } catch {
                state.bootLoading = false
                state.bootStatus = .authRequired
                state.error = formatRequestError(error)
            }
        }
    }

    func logout() {
        reconnectTask?.cancel()
        webSocket.disconnect(intentional: true)
        store.clearToken()
        state.token = ""
        state.bootStatus = .authRequired
        state.fullName = ""
        state.username = ""
        state.liveStatus = "DISCONNECTED"
        state.orders = []
        state.plans = []
        state.goldStrategy = nil
    }

    func unlockSavedLogin() {
        state.bootStatus = .ready
        state.bootLoading = false
        state.dashboardSyncing = true
        state.syncMessage = "Opening dashboard..."
        Task { await refreshDashboardInternal(showIndicator: true) }
    }

    func usePasswordLogin(message: String = "Please login again.") {
        Task { await requireLogin(message) }
    }

    func refresh() { Task { await refreshDashboardInternal(showIndicator: true) } }

    func setAppearance(_ appearance: AppAppearance) {
        state.appearance = appearance
        store.savedAppearance = appearance
    }

    func onAppForegrounded() {
        guard state.bootStatus == .ready, !state.token.isEmpty else { return }
        let stale = Date().timeIntervalSince(lastLiveDataAt) > liveStaleSeconds
        guard stale || state.liveStatus != "CONNECTED" else { return }
        reconnectTask?.cancel()
        reconnectAttempts = 0
        state.liveStatus = "RECONNECTING"
        Task { await refreshDashboardInternal(showIndicator: false) }
    }

    func authenticateWithBiometrics(onSuccess: @escaping () -> Void, onPassword: @escaping () -> Void) {
        let context = LAContext()
        var error: NSError?
        guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) else {
            onPassword()
            return
        }
        context.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: "Unlock MT5 Platform") { success, _ in
            Task { @MainActor in
                if success { onSuccess() } else { onPassword() }
            }
        }
    }

    func addWatchSymbol(_ symbol: String) {
        Task { await runAction("Adding \(symbol)...") {
            let response = try await self.network.request(path: "/watchlist", method: "POST", body: ["symbol": symbol.uppercased()], apiBase: self.state.apiBase, token: self.state.token)
            if let digitsValue = response["price_digits"], !(digitsValue is NSNull) {
                let digits: Int
                if let number = digitsValue as? Int { digits = number }
                else if let number = digitsValue as? Double { digits = Int(number) }
                else { digits = 0 }
                let brokerSymbol = response["broker_symbol"] as? String ?? ""
                let entries = symbolPriceDigitEntries(brokerSymbol: brokerSymbol, requestedSymbol: symbol, digits: digits)
                if !entries.isEmpty {
                    self.state.priceDigits.merge(entries) { _, new in new }
                }
            }
        }}
    }

    func removeWatchSymbol(_ symbol: String) {
        Task { await runAction("Removing \(symbol)...") {
            _ = try await self.network.request(path: "/watchlist?symbol=\(symbol.uppercased())", method: "DELETE", apiBase: self.state.apiBase, token: self.state.token)
        }}
    }

    func placeOrder(symbol: String, orderType: String, side: String, entry: String, stopLoss: String, target: String, retryableOrder: Bool, automaticTradeManagement: Bool) {
        Task { await runAction("Placing order...") {
            var body: [String: Any] = [
                "symbol": symbol.uppercased(),
                "order_type": orderType,
                "side": side,
                "entry": Double(entry) ?? 0,
                "stop_loss": Double(stopLoss) ?? 0,
                "automatic_trade_management": automaticTradeManagement
            ]
            if let targetValue = Double(target) { body["target"] = targetValue }
            if orderType == "LIMIT" || orderType == "SL" { body["retryable_order"] = retryableOrder }
            _ = try await self.network.request(path: "/orders", method: "POST", body: body, apiBase: self.state.apiBase, token: self.state.token)
            self.closeTradeSheet()
        }}
    }

    func fetchOrderEvents(orderId: String) async throws -> [OrderEventRow] {
        let rows = try await network.requestArray(path: "/orders/\(orderId)/events", apiBase: state.apiBase, token: state.token)
        return JsonParsers.parseOrderEvents(rows)
    }

    func fetchBrokerTradeHistory(
        accountId: String? = nil,
        page: Int = 1,
        pageSize: Int = 20,
        type: String = "all",
        today: Bool = false
    ) async throws -> [BrokerTradeHistoryRow] {
        let resolvedAccountId = accountId?.isEmpty == false
            ? accountId!
            : (state.selectedAccountId.isEmpty ? (state.accounts.first?.id ?? "") : state.selectedAccountId)
        var path = "/broker/trade-history?page=\(page)&page_size=\(pageSize)&type=\(type)"
        if today { path += "&today=true" }
        if !resolvedAccountId.isEmpty { path += "&account_id=\(resolvedAccountId)" }
        let payload = try await network.request(path: path, apiBase: state.apiBase, token: state.token)
        return JsonParsers.parseBrokerTradeHistory(payload)
    }

    func fetchClosedTodayBrokerTrades(accountFilter: String, accounts: [AccountRow]) async throws -> [BrokerTradeHistoryRow] {
        let accountIds = accountFilter == "ALL"
            ? accounts.map(\.id).filter { !$0.isEmpty }
            : [accountFilter].filter { !$0.isEmpty }
        var rows: [BrokerTradeHistoryRow] = []
        for accountId in accountIds {
            let batch = try await fetchBrokerTradeHistory(accountId: accountId, pageSize: 500, type: "closed", today: true)
            rows.append(contentsOf: batch)
        }
        return rows
    }

    func cancelOrder(_ orderId: String) {
        Task { await runAction("Cancelling order...") {
            _ = try await self.network.request(path: "/orders/\(orderId)/cancel", method: "POST", apiBase: self.state.apiBase, token: self.state.token)
        }}
    }

    func modifyOrder(_ order: OrderRow, entry: String, stopLoss: String, target: String, quantity: String) {
        Task { await runAction("Updating order...") {
            var body: [String: Any] = [
                "entry": Double(entry) ?? 0,
                "stop_loss": Double(stopLoss) ?? 0,
                "quantity": Double(quantity) ?? 0
            ]
            if let targetValue = Double(target) { body["target"] = targetValue }
            _ = try await self.network.request(path: "/orders/\(order.id)/modify", method: "POST", body: body, apiBase: self.state.apiBase, token: self.state.token)
            self.closeOrderEditSheet()
        }}
    }

    func closeOrder(_ order: OrderRow) {
        let qty = order.positionQuantity ?? order.quantity ?? 0
        Task { await runAction("Closing position...") {
            _ = try await self.network.request(path: "/orders/\(order.id)/close", method: "POST", body: ["quantity": qty], apiBase: self.state.apiBase, token: self.state.token)
        }}
    }

    func togglePlan(_ plan: PlannerRow, running: Bool) {
        Task { await runAction(running ? "Activating plan..." : "Deactivating plan...") {
            _ = try await self.network.request(path: "/trade-planner/plans/\(plan.id)", method: "PATCH", body: ["auto_execution_enabled": running], apiBase: self.state.apiBase, token: self.state.token)
        }}
    }

    func deletePlan(_ planId: String) {
        Task { await runAction("Deleting plan...") {
            _ = try await self.network.request(path: "/trade-planner/plans/\(planId)", method: "DELETE", apiBase: self.state.apiBase, token: self.state.token)
        }}
    }

    func stopGoldStrategy() {
        Task { await runAction("Stopping GOLD strategy...") {
            _ = try await self.network.request(path: "/gold-strategy/stop", method: "POST", apiBase: state.apiBase, token: state.token)
        }}
    }

    func stopContinuationFailure(symbol: String) {
        Task { await runAction("Stopping Continuation Failure...") {
            _ = try await self.network.request(
                path: "/continuation-failure/stop",
                method: "POST",
                body: ["symbol": symbol.uppercased()],
                apiBase: self.state.apiBase,
                token: self.state.token
            )
            try await self.refreshContinuationFailure()
        }}
    }

    func startContinuationFailure(
        symbol: String,
        pivotPrice: Double,
        startReferencePrice: Double,
        targets: [(String, Double)],
        exitTargets: [(Double, Double?)]
    ) {
        Task { await runAction("Starting Continuation Failure...") {
            let targetsBody = targets.map { ["account_db_id": $0.0, "risk_amount": $0.1] }
            let exitBody: [[String: Any]] = exitTargets.map { target in
                var row: [String: Any] = ["price": target.0]
                row["quantity"] = target.1 ?? NSNull()
                return row
            }
            let body: [String: Any] = [
                "symbol": symbol.uppercased(),
                "pivot_price": pivotPrice,
                "start_reference_price": startReferencePrice,
                "targets": targetsBody,
                "exit_targets": exitBody
            ]
            _ = try await self.network.request(path: "/continuation-failure/start", method: "POST", body: body, apiBase: self.state.apiBase, token: self.state.token)
            try await self.refreshContinuationFailure()
        }}
    }

    func suggestInstruments(query: String) async throws -> [String] {
        let encoded = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query
        let payload = try await network.request(path: "/instruments/suggest?q=\(encoded)&limit=8", apiBase: state.apiBase, token: state.token)
        return payload["symbols"] as? [String] ?? []
    }

    func resolveContinuationFailureSymbol(_ symbol: String) async throws -> [String: Any] {
        let encoded = symbol.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? symbol
        return try await network.request(path: "/continuation-failure/symbol?symbol=\(encoded)", apiBase: state.apiBase, token: state.token)
    }

    private func refreshContinuationFailure() async throws {
        let payload = try await network.request(path: "/continuation-failure", apiBase: state.apiBase, token: state.token)
        state.continuationFailure = JsonParsers.parseContinuationFailure(payload)
    }

    func fetchTrapReversalActive() async throws -> [TrapReversalRunRow] {
        let payload = try await network.request(path: "/trap-reversal/active", apiBase: state.apiBase, token: state.token)
        return JsonParsers.parseTrapReversalRuns(payload["runs"] as? [[String: Any]])
    }

    func fetchTrapReversalLevels(symbol: String) async throws -> TrapReversalLevels {
        let encoded = symbol.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? symbol
        let payload = try await network.request(path: "/trap-reversal/levels/\(encoded)", apiBase: state.apiBase, token: state.token)
        return JsonParsers.parseTrapReversalLevels(payload)
    }

    func startTrapReversal(symbol: String, riskAmount: Double) async throws {
        _ = try await network.request(
            path: "/trap-reversal/start",
            method: "POST",
            body: ["symbol": symbol.uppercased(), "risk_amount": riskAmount],
            apiBase: state.apiBase,
            token: state.token
        )
    }

    func stopTrapReversal(symbol: String) async throws {
        _ = try await network.request(
            path: "/trap-reversal/stop",
            method: "POST",
            body: ["symbol": symbol.uppercased()],
            apiBase: state.apiBase,
            token: state.token
        )
    }

    func fetchTrendPilotActive() async throws -> [TrendPilotRunRow] {
        let payload = try await network.request(path: "/trend-pilot/active", apiBase: state.apiBase, token: state.token)
        return JsonParsers.parseTrendPilotRuns(payload["runs"] as? [[String: Any]])
    }

    func fetchTrendPilotHistoryList() async throws -> [TrendPilotHistoryRow] {
        let payload = try await network.request(path: "/trend-pilot/runs?limit=20", apiBase: state.apiBase, token: state.token)
        return JsonParsers.parseTrendPilotHistoryRows(payload["runs"] as? [[String: Any]])
    }

    func fetchTrendPilotHistoryDetail(runId: String) async throws -> [String: Any] {
        let encoded = runId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? runId
        return try await network.request(path: "/trend-pilot/history/\(encoded)", apiBase: state.apiBase, token: state.token)
    }

    func startTrendPilot(symbol: String, quantity: Double, accountIds: [String]) async throws {
        let payload = try await network.request(
            path: "/trend-pilot/start",
            method: "POST",
            body: ["symbol": symbol.uppercased(), "quantity": quantity, "account_ids": accountIds],
            apiBase: state.apiBase,
            token: state.token
        )
        let started = payload["started_count"] as? Int ?? (payload["runs"] as? [[String: Any]])?.count ?? 0
        if started <= 0 {
            let errors = payload["errors"] as? [[String: Any]]
            let message = errors?.first?["error"] as? String ?? "Trend Pilot could not be started."
            throw ApiError.http(status: 400, detail: message)
        }
    }

    func stopTrendPilot(symbol: String, accountIds: [String]) async throws {
        _ = try await network.request(
            path: "/trend-pilot/stop",
            method: "POST",
            body: ["symbol": symbol.uppercased(), "close_position": true, "account_ids": accountIds],
            apiBase: state.apiBase,
            token: state.token
        )
    }

    func fetchTrendPilotBacktests(limit: Int = 10, cursor: String? = nil) async throws -> TrendPilotBacktestPage {
        var path = "/trend-pilot/backtests?limit=\(min(50, max(1, limit)))"
        if let cursor, !cursor.isEmpty {
            let encoded = cursor.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? cursor
            path += "&cursor=\(encoded)"
        }
        let payload = try await network.request(path: path, apiBase: state.apiBase, token: state.token)
        let pageInfo = payload["page_info"] as? [String: Any]
        let parsedLimit = pageInfo?["limit"] as? Int ?? limit
        let totalCount = pageInfo?["total_count"] as? Int ?? 0
        let totalPages = max(1, pageInfo?["total_pages"] as? Int ?? 1)
        return TrendPilotBacktestPage(
            results: JsonParsers.parseTrendPilotBacktests(payload["results"] as? [[String: Any]]),
            hasNextPage: pageInfo?["has_next_page"] as? Bool ?? false,
            hasPreviousPage: pageInfo?["has_previous_page"] as? Bool ?? false,
            endCursor: pageInfo?["end_cursor"] as? String,
            totalCount: totalCount,
            totalPages: totalPages,
            limit: parsedLimit
        )
    }

    func fetchTrendPilotBacktestsPage(targetPage: Int, pageSize: Int, cursors: inout [Int: String?]) async throws -> TrendPilotBacktestPage {
        let safePage = max(1, targetPage)
        let safeSize = min(50, max(1, pageSize))

        if safePage == 1 {
            let page = try await fetchTrendPilotBacktests(limit: safeSize, cursor: nil)
            if let endCursor = page.endCursor {
                cursors[2] = endCursor
            }
            return page
        }

        if cursors.keys.contains(safePage) {
            let page = try await fetchTrendPilotBacktests(limit: safeSize, cursor: cursors[safePage] ?? nil)
            if let endCursor = page.endCursor {
                cursors[safePage + 1] = endCursor
            }
            return page
        }

        var walkPage = 1
        for page in stride(from: safePage, through: 1, by: -1) where cursors.keys.contains(page) {
            walkPage = page
            break
        }

        var cursor = walkPage == 1 ? nil : cursors[walkPage] ?? nil
        var latest = try await fetchTrendPilotBacktests(limit: safeSize, cursor: walkPage == 1 ? nil : cursor)
        if walkPage == 1, let endCursor = latest.endCursor {
            cursors[2] = endCursor
            cursor = endCursor
        }
        for page in (walkPage + 1)...safePage {
            latest = try await fetchTrendPilotBacktests(limit: safeSize, cursor: cursor)
            if let endCursor = latest.endCursor {
                cursors[page + 1] = endCursor
            }
            cursor = latest.endCursor
            if !latest.hasNextPage { break }
        }
        return latest
    }

    func fetchTrendPilotBacktestDetail(resultId: String) async throws -> [String: Any] {
        let encoded = resultId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? resultId
        return try await network.request(path: "/trend-pilot/backtest/\(encoded)", apiBase: state.apiBase, token: state.token)
    }

    func runTrendPilotBacktest(symbol: String, quantity: Double, fromDate: String, toDate: String) async throws {
        _ = try await network.request(
            path: "/trend-pilot/backtest",
            method: "POST",
            body: ["symbol": symbol.uppercased(), "quantity": quantity, "from_date": fromDate, "to_date": toDate],
            apiBase: state.apiBase,
            token: state.token
        )
    }

    func deleteTrendPilotBacktest(resultId: String) async throws {
        let encoded = resultId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? resultId
        _ = try await network.request(path: "/trend-pilot/backtest/\(encoded)", method: "DELETE", apiBase: state.apiBase, token: state.token)
    }

    func fetchTrendPilotBacktestSettings() async throws -> [String: Any] {
        try await network.request(path: "/trend-pilot/backtest/settings", apiBase: state.apiBase, token: state.token)
    }

    func saveTrendPilotBacktestSettings(partialAtPct: Double, partialQtyPct: Double, moveSlToBreakeven: Bool) async throws {
        _ = try await network.request(
            path: "/trend-pilot/backtest/settings",
            method: "PUT",
            body: [
                "partial_at_pct": partialAtPct,
                "partial_qty_pct": partialQtyPct,
                "move_sl_to_breakeven": moveSlToBreakeven,
            ],
            apiBase: state.apiBase,
            token: state.token
        )
    }

    private func bootstrap() async {
        let token = store.savedToken
        await connectToPlatform(existingToken: token)
    }

    private func connectToPlatform(existingToken: String? = nil) async {
        let token = existingToken ?? store.savedToken
        state.bootLoading = true
        state.error = ""
        state.message = "Connecting securely..."
        configureHost()
        let apiPing = await network.pingApi(state.apiBase)
        guard apiPing.ok else {
            state.bootLoading = false
            state.bootStatus = .hostRequired
            state.error = "SignalBridge Cloud is unavailable right now. Retry when the service is available again."
            state.message = "Connection failed"
            return
        }
        if token.isEmpty {
            state.bootStatus = .authRequired
            state.bootLoading = false
            state.message = "Ready to sign in."
            state.error = ""
            return
        }
        state.token = token
        state.bootStatus = .biometricRequired
        state.bootLoading = false
        state.message = "Unlock saved login."
        state.error = ""
    }

    private func refreshDashboardInternal(showIndicator: Bool) async {
        guard !state.token.isEmpty else { return }
        if showIndicator {
            state.dashboardSyncing = true
            state.syncMessage = "Syncing dashboard..."
            state.error = ""
        }
        do {
            async let meTask = network.request(path: "/auth/me", apiBase: state.apiBase, token: state.token)
            async let watchTask = network.requestArray(path: "/watchlist", apiBase: state.apiBase, token: state.token)
            async let plansTask = network.requestArray(path: "/trade-planner/plans", apiBase: state.apiBase, token: state.token)
            let me = try await meTask
            let watchlistRows = try await watchTask
            let plans = try await plansTask
            state.bootStatus = .ready
            state.bootLoading = false
            state.dashboardSyncing = false
            state.syncMessage = ""
            state.fullName = me["full_name"] as? String ?? me["username"] as? String ?? ""
            state.username = me["username"] as? String ?? ""
            state.selectedMarket = me["selected_market"] as? String ?? "INTERNATIONAL"
            state.selectedAccountId = me["selected_account_id"] as? String ?? ""
            state.accounts = JsonParsers.parseAccounts(me["accounts"] as? [[String: Any]])
            state.watchlist = JsonParsers.parseWatchlist(watchlistRows)
            state.priceDigits.merge(JsonParsers.parsePriceDigitsFromWatchlist(watchlistRows)) { _, new in new }
            state.plans = JsonParsers.parsePlans(plans)
            connectLiveSocket()
            await loadStrategySnapshots()
        } catch {
            if isAuthFailure(error) {
                await requireLogin("Saved login expired. Please login again.")
                return
            }
            state.bootLoading = false
            state.dashboardSyncing = false
            state.syncMessage = ""
            state.error = formatRequestError(error)
        }
    }

    private func loadStrategySnapshots() async {
        do {
            async let goldPayload = network.request(path: "/gold-strategy", apiBase: state.apiBase, token: state.token)
            async let cfPayload = network.request(path: "/continuation-failure", apiBase: state.apiBase, token: state.token)
            let gold = try await goldPayload
            let cf = try await cfPayload
            state.goldStrategy = JsonParsers.parseGoldStrategy(gold)
            state.continuationFailure = JsonParsers.parseContinuationFailure(cf)
        } catch {
            // Strategy endpoints can be slow; core dashboard should still work.
        }
    }

    private func configureHost() {
        state.apiBase = AppConfig.fixedApiBase
        state.wsBase = AppConfig.fixedApiBase
            .replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "http://", with: "ws://")
    }

    private func reconnectLiveSocket() {
        reconnectTask?.cancel()
        reconnectAttempts = 0
        connectLiveSocket()
    }

    private func runAction(_ message: String, _ block: () async throws -> Void) async {
        let onDashboard = state.bootStatus == .ready
        if onDashboard {
            state.actionBusy = true
            state.actionMessage = message
            state.error = ""
        } else {
            state.bootLoading = true
            state.message = message
            state.error = ""
        }
        do {
            try await block()
            state.bootLoading = false
            state.actionBusy = false
            state.actionMessage = ""
            if !onDashboard { state.message = "Done" }
        } catch {
            state.bootLoading = false
            state.actionBusy = false
            state.actionMessage = ""
            state.error = formatRequestError(error)
        }
    }

    private func connectLiveSocket() {
        configureHost()
        guard !state.token.isEmpty, !state.wsBase.isEmpty else { return }
        reconnectTask?.cancel()
        reconnectAttempts = 0
        subscribedLiveSymbols = []
        liveSocketAttempt += 1
        let attempt = liveSocketAttempt
        state.liveStatus = "CONNECTING"
        webSocket.connect(wsBase: state.wsBase, token: state.token)
        Task { [weak self] in
            try? await Task.sleep(nanoseconds: 20_000_000_000)
            guard let self, !Task.isCancelled else { return }
            guard attempt == self.liveSocketAttempt, self.state.liveStatus == "CONNECTING" else { return }
            self.handleSocketDisconnected()
        }
    }

    private func handleSocketConnected() {
        liveSocketAttempt += 1
        reconnectAttempts = 0
        lastLiveDataAt = Date()
        state.liveStatus = "CONNECTED"
        startLiveStaleWatchdog()
        maybeSubscribeLiveSymbols()
    }

    private func handleSocketDisconnected() {
        staleWatchdogTask?.cancel()
        staleWatchdogTask = nil
        state.liveStatus = "DISCONNECTED"
        scheduleLiveReconnect()
    }

    private func handleSocketMessage(_ text: String) {
        guard let data = text.data(using: .utf8),
              let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
        if let socketError = payload["error"] as? String,
           socketError.localizedCaseInsensitiveContains("invalid token") || socketError.localizedCaseInsensitiveContains("session expired") {
            Task { await requireLogin("Saved login expired. Please login again.") }
            return
        }
        if snapshotHasFreshPrices(payload) {
            lastLiveDataAt = Date()
        }
        let prices = JsonParsers.parsePrices((payload["prices"] as? [String: Any]) ?? (payload["livePrices"] as? [String: Any]))
        let incomingDigits = JsonParsers.parsePriceDigitsFromPrices((payload["prices"] as? [String: Any]) ?? (payload["livePrices"] as? [String: Any]))
            .merging(JsonParsers.parsePriceDigitsFromWatchlist((payload["watchlist"] as? [[String: Any]]) ?? [])) { _, new in new }
        if let orders = payload["orders"] as? [[String: Any]] {
            state.orders = normalizeLiveOrders(JsonParsers.parseOrders(orders))
        }
        if let gold = payload["gold_strategy"] as? [String: Any] { state.goldStrategy = JsonParsers.parseGoldStrategy(gold) }
        if let cf = payload["continuation_failure"] as? [String: Any] {
            state.continuationFailure = JsonParsers.parseContinuationFailure(cf)
        }
        if !prices.isEmpty { state.prices.merge(prices) { _, new in new } }
        if !incomingDigits.isEmpty { state.priceDigits.merge(incomingDigits) { _, new in new } }
        if let notifications = payload["notifications"] as? [[String: Any]] {
            handleStrategyNotifications(JsonParsers.parseNotifications(notifications))
        }
        state.liveStatus = "CONNECTED"
        liveSocketAttempt += 1
        maybeSubscribeLiveSymbols()
    }

    private func liveSymbolsForState() -> Set<String> {
        let watchSymbols = state.watchlist.map { $0.symbol.uppercased() }
        let goldSymbol = state.goldStrategy?.config.symbol.uppercased()
        let cfSymbols = state.continuationFailure?.running.map { $0.symbol.uppercased() } ?? []
        return Set((watchSymbols + [goldSymbol].compactMap { $0 } + cfSymbols).filter { !$0.isEmpty })
    }

    private func maybeSubscribeLiveSymbols() {
        let symbols = liveSymbolsForState()
        guard !symbols.isEmpty, symbols != subscribedLiveSymbols else { return }
        subscribedLiveSymbols = symbols
        let payload: [String: Any] = ["type": "subscribe_symbols", "symbols": Array(symbols)]
        if let data = try? JSONSerialization.data(withJSONObject: payload), let text = String(data: data, encoding: .utf8) {
            webSocket.send(text)
        }
    }

    private func startLiveStaleWatchdog() {
        staleWatchdogTask?.cancel()
        staleWatchdogTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 10_000_000_000)
                guard let self, !Task.isCancelled else { return }
                guard self.state.liveStatus == "CONNECTED" else { continue }
                if Date().timeIntervalSince(self.lastLiveDataAt) > self.liveStaleSeconds {
                    self.reconnectLiveSocket()
                    return
                }
            }
        }
    }

    private func snapshotHasFreshPrices(_ payload: [String: Any], staleSeconds: TimeInterval = 45) -> Bool {
        let now = Date()
        func freshTime(_ raw: String?) -> Bool {
            guard let raw, !raw.isEmpty else { return false }
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            let parsed = formatter.date(from: raw) ?? ISO8601DateFormatter().date(from: raw)
            guard let parsed else { return false }
            return now.timeIntervalSince(parsed) < staleSeconds
        }
        if let prices = payload["prices"] as? [String: Any] {
            for (_, value) in prices {
                guard let tick = value as? [String: Any], freshTime(tick["time"] as? String) else { continue }
                return true
            }
        }
        if let watchlist = payload["watchlist"] as? [[String: Any]] {
            for item in watchlist where freshTime(item["time"] as? String) {
                return true
            }
        }
        return false
    }

    private func scheduleLiveReconnect() {
        guard state.bootStatus == .ready, !state.token.isEmpty else { return }
        reconnectTask?.cancel()
        let delay = min(30.0, pow(2.0, Double(min(reconnectAttempts, 5))))
        reconnectAttempts += 1
        state.liveStatus = "RECONNECTING"
        reconnectTask = Task {
            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            guard !Task.isCancelled else { return }
            connectLiveSocket()
        }
    }

    private func requireLogin(_ message: String) async {
        reconnectTask?.cancel()
        staleWatchdogTask?.cancel()
        staleWatchdogTask = nil
        webSocket.disconnect(intentional: true)
        store.clearToken()
        state.token = ""
        state.bootStatus = .authRequired
        state.bootLoading = false
        state.dashboardSyncing = false
        state.message = message
        state.error = message
        state.liveStatus = "DISCONNECTED"
    }

    private func isAuthFailure(_ error: Error) -> Bool {
        let message = error.localizedDescription.lowercased()
        return message.contains("401") || message.contains("invalid token") || message.contains("session expired") || message.contains("user not found")
    }

    private func formatRequestError(_ error: Error) -> String {
        let message = error.localizedDescription.lowercased()
        if message.contains("timed out") || message.contains("timeout") {
            return "SignalBridge Cloud is taking too long to respond. Gold strategy sync can still take a moment; retry shortly."
        }
        if message.contains("could not connect") || message.contains("failed to connect") {
            return "SignalBridge Cloud is unavailable right now. Please try again shortly."
        }
        return error.localizedDescription.isEmpty ? "Could not load dashboard" : error.localizedDescription
    }

    private func handleStrategyNotifications(_ notifications: [NotificationRow]) {
        let rows = notifications.filter { ["gold_strategy", "strategy", "continuation_failure"].contains($0.category) }
        if !strategyNotificationsPrimed {
            seenStrategyNotificationIds.formUnion(rows.map(\.id))
            strategyNotificationsPrimed = true
            return
        }
        for notification in rows.reversed() where seenStrategyNotificationIds.insert(notification.id).inserted {
            NotificationManager.shared.showStrategy(notification)
        }
    }
}

final class NotificationManager {
    static let shared = NotificationManager()

    func requestAuthorization() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in }
    }

    func showStrategy(_ notification: NotificationRow) {
        let content = UNMutableNotificationContent()
        content.title = "\(notification.symbol) strategy \(plainStatus(notification.status))"
        content.body = notification.activity
        content.sound = .default
        let request = UNNotificationRequest(identifier: notification.id, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }
}
