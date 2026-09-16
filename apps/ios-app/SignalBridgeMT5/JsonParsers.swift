import Foundation

enum JsonParsers {
    static func parseAccounts(_ array: [[String: Any]]?) -> [AccountRow] {
        guard let array else { return [] }
        return array.compactMap { item in
            AccountRow(
                id: string(item, "id"),
                name: string(item, "account_name", fallback: "Account"),
                number: string(item, "account_id"),
                risk: double(item, "risk_amount") ?? 0,
                equityBalance: double(item, "equity_balance"),
                availableMargin: double(item, "available_margin"),
                currencyCode: string(item, "currency_code", fallback: "USD"),
                brokerScopeKey: optionalString(item, "broker_scope_key"),
                marketType: optionalString(item, "market_type"),
                brokerType: optionalString(item, "broker_type"),
                brokerServer: optionalString(item, "broker_server")
            )
        }
    }

    static func parseWatchlist(_ rows: [[String: Any]]) -> [WatchRow] {
        rows.map { WatchRow(symbol: string($0, "symbol"), price: double($0, "price")) }
    }

    static func parsePrices(_ obj: [String: Any]?) -> [String: Double] {
        guard let obj else { return [:] }
        var result: [String: Double] = [:]
        for (symbol, value) in obj {
            let key = symbol.uppercased()
            if let row = value as? [String: Any] {
                let bid = double(row, "bid")
                let ask = double(row, "ask")
                let mid = (bid != nil && ask != nil) ? (bid! + ask!) / 2 : nil
                if let price = double(row, "price") ?? mid ?? bid ?? ask {
                    result[key] = price
                }
            } else if let price = value as? Double {
                result[key] = price
            }
        }
        return result
    }

    static func parsePriceDigitsFromPrices(_ obj: [String: Any]?) -> [String: Int] {
        guard let obj else { return [:] }
        var result: [String: Int] = [:]
        for (symbol, value) in obj {
            guard let row = value as? [String: Any], let entry = priceDigitEntry(row, fallbackSymbol: symbol) else { continue }
            result[entry.0] = entry.1
        }
        return result
    }

    static func parsePriceDigitsFromWatchlist(_ rows: [[String: Any]]) -> [String: Int] {
        var result: [String: Int] = [:]
        for row in rows {
            guard let entry = priceDigitEntry(row) else { continue }
            result[entry.0] = entry.1
        }
        return result
    }

    private static func priceDigitEntry(_ item: [String: Any], fallbackSymbol: String? = nil) -> (String, Int)? {
        guard let digitsValue = item["price_digits"], !(digitsValue is NSNull) else { return nil }
        let digits: Int
        if let number = digitsValue as? Int { digits = number }
        else if let number = digitsValue as? Double { digits = Int(number) }
        else { return nil }
        let symbol = (item["symbol"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? fallbackSymbol
        let key = normalizeSymbolKey(symbol)
        guard !key.isEmpty else { return nil }
        return (key, min(max(digits, 0), 10))
    }

    static func parseOrders(_ array: [[String: Any]]) -> [OrderRow] {
        array.map { item in
            let brokerInfo = item["broker_info"] as? [String: Any]
            return OrderRow(
                id: string(item, "id"),
                accountId: string(item, "account_id"),
                symbol: string(item, "symbol"),
                side: string(item, "side"),
                status: string(item, "status"),
                orderType: string(item, "order_type", fallback: "SL"),
                entry: double(item, "entry"),
                stopLoss: double(item, "stop_loss"),
                target: double(item, "target"),
                quantity: double(item, "quantity"),
                positionQuantity: double(item, "position_quantity"),
                unrealizedPl: double(item, "unrealized_pl"),
                realizedPl: double(item, "realized_pl"),
                dryRun: bool(item, "dry_run"),
                failureReason: optionalString(item, "failure_reason"),
                placementFallbackReason: optionalString(item, "placement_fallback_reason"),
                comment: optionalString(item, "comment"),
                metaPositionId: optionalString(item, "meta_position_id"),
                externalSource: optionalString(item, "external_source"),
                rrRatio: double(item, "rr_ratio"),
                isOpenPosition: bool(item, "is_open_position"),
                plannerPlanAccountId: optionalString(item, "planner_plan_account_id"),
                brokerInfoAccountId: brokerInfo.flatMap { optionalString($0, "account_id") },
                brokerInfoAccountName: brokerInfo.flatMap { optionalString($0, "account_name") },
                brokerInfoAvailableMargin: brokerInfo.flatMap { double($0, "available_margin") },
                createdAt: optionalString(item, "created_at"),
                openedAt: optionalString(item, "opened_at"),
                closedAt: optionalString(item, "closed_at"),
                updatedAt: optionalString(item, "updated_at")
            )
        }
    }

    static func parseNotifications(_ array: [[String: Any]]) -> [NotificationRow] {
        array.map {
            NotificationRow(
                id: string($0, "id"),
                category: string($0, "category"),
                symbol: string($0, "symbol"),
                status: string($0, "status"),
                activity: string($0, "activity"),
                failureReason: optionalString($0, "failure_reason"),
                placementFallbackReason: optionalString($0, "placement_fallback_reason")
            )
        }
    }

    static func parsePlans(_ array: [[String: Any]]) -> [PlannerRow] {
        array.map {
            PlannerRow(
                id: string($0, "id"),
                symbol: string($0, "symbol"),
                status: string($0, "status"),
                runtime: string($0, "runtime_status"),
                entry: double($0, "entry_price"),
                stopLoss: double($0, "stop_loss")
            )
        }
    }

    static func parseGoldStrategy(_ payload: [String: Any]) -> GoldStrategyState {
        let config = payload["config"] as? [String: Any] ?? [:]
        return GoldStrategyState(
            config: GoldConfigRow(
                symbol: string(config, "symbol", fallback: "XAUUSD"),
                running: bool(config, "running"),
                triggerSource: string(config, "trigger_source", fallback: "previous_day"),
                pdHigh: double(config, "pd_high"),
                pdLow: double(config, "pd_low"),
                userTriggerPrice: double(config, "user_trigger_price")
            ),
            running: parseGoldRunArray(configArray(payload, "running")),
            history: parseGoldRunArray(configArray(payload, "history"))
        )
    }

    static func parseGoldRunArray(_ array: [[String: Any]]) -> [GoldRunRow] {
        array.map {
            GoldRunRow(
                id: string($0, "id"),
                symbol: string($0, "symbol", fallback: "XAUUSD"),
                status: string($0, "status"),
                runningPl: double($0, "running_pl") ?? 0,
                bookedPl: double($0, "booked_pl") ?? 0,
                quantity: double($0, "quantity") ?? 0
            )
        }
    }

    static func parseContinuationFailure(_ payload: [String: Any]) -> ContinuationFailureState {
        let symbols = (payload["symbols"] as? [[String: Any]] ?? []).map {
            ContinuationFailureSymbolConfig(
                symbol: string($0, "symbol"),
                pivotPrice: double($0, "pivot_price")
            )
        }
        return ContinuationFailureState(
            symbols: symbols,
            running: parseContinuationFailureRuns(configArray(payload, "running")),
            history: parseContinuationFailureRuns(configArray(payload, "history"))
        )
    }

    private static func parseContinuationFailureRuns(_ array: [[String: Any]]) -> [ContinuationFailureRunRow] {
        array.map { item in
            let events = (item["events"] as? [[String: Any]] ?? []).map { event in
                ContinuationFailureEventRow(
                    id: string(event, "id"),
                    eventType: string(event, "event_type"),
                    status: string(event, "status"),
                    message: string(event, "message"),
                    createdAt: string(event, "created_at"),
                    createdAtIst: string(event, "created_at_ist")
                )
            }
            return ContinuationFailureRunRow(
                id: string(item, "id"),
                symbol: string(item, "symbol"),
                status: string(item, "status"),
                direction: string(item, "direction"),
                pivotPrice: double(item, "pivot_price"),
                runningPl: double(item, "running_pl") ?? 0,
                bookedPl: double(item, "booked_pl") ?? 0,
                events: events
            )
        }
    }

    static func parseOrderEvents(_ array: [[String: Any]]) -> [OrderEventRow] {
        array.map {
            OrderEventRow(
                id: string($0, "id"),
                eventType: string($0, "event_type"),
                status: string($0, "status"),
                message: string($0, "message"),
                eventTsIst: string($0, "event_ts_ist"),
                failureReason: optionalString($0, "failure_reason"),
                payloadJson: optionalString($0, "payload_json")
            )
        }
    }

    static func parseBrokerTradeHistory(_ payload: [String: Any]) -> [BrokerTradeHistoryRow] {
        guard let records = payload["records"] as? [[String: Any]] else { return [] }
        return records.enumerated().map { index, item in
            BrokerTradeHistoryRow(
                id: string(item, "id", fallback: string(item, "position_id", fallback: "\(index)")),
                symbol: string(item, "symbol"),
                type: string(item, "type"),
                status: string(item, "status"),
                openPrice: double(item, "open_price"),
                closePrice: double(item, "close_price"),
                profit: double(item, "profit") ?? 0,
                netProfit: double(item, "net_profit") ?? 0,
                isRunning: bool(item, "is_running")
            )
        }
    }

    static func jsonArray(from data: Data) throws -> [[String: Any]] {
        guard let array = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] else {
            throw ApiError.invalidResponse
        }
        return array
    }

    static func jsonObject(from data: Data) throws -> [String: Any] {
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw ApiError.invalidResponse
        }
        return object
    }

    private static func configArray(_ payload: [String: Any], _ key: String) -> [[String: Any]] {
        payload[key] as? [[String: Any]] ?? []
    }

    private static func string(_ item: [String: Any], _ key: String, fallback: String = "") -> String {
        (item[key] as? String) ?? fallback
    }

    private static func optionalString(_ item: [String: Any], _ key: String) -> String? {
        guard let value = item[key] else { return nil }
        if value is NSNull { return nil }
        let text = String(describing: value).trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty || text.lowercased() == "null" { return nil }
        return text
    }

    private static func double(_ item: [String: Any], _ key: String) -> Double? {
        guard let value = item[key], !(value is NSNull) else { return nil }
        if let number = value as? Double { return number.isNaN ? nil : number }
        if let number = value as? Int { return Double(number) }
        if let text = value as? String, let number = Double(text) { return number }
        return nil
    }

    private static func int(_ item: [String: Any], _ key: String, fallback: Int = 0) -> Int {
        if let value = item[key] as? Int { return value }
        if let value = item[key] as? Double { return Int(value) }
        return fallback
    }

    private static func bool(_ item: [String: Any], _ key: String) -> Bool {
        if let value = item[key] as? Bool { return value }
        if let value = item[key] as? Int { return value != 0 }
        return false
    }

    static func parseTrendPilotRuns(_ array: [[String: Any]]?) -> [TrendPilotRunRow] {
        guard let array else { return [] }
        return array.map { item in
            TrendPilotRunRow(
                runId: string(item, "run_id"),
                accountId: string(item, "account_id"),
                accountName: string(item, "account_name"),
                symbol: string(item, "requested_symbol", fallback: string(item, "symbol")),
                displaySymbol: string(item, "display_symbol", fallback: string(item, "symbol")),
                state: string(item, "state"),
                currentSide: string(item, "current_side"),
                rollCount: int(item, "roll_count"),
                quantity: double(item, "quantity") ?? 0.01,
                windowHigh: double(item, "window_high"),
                windowLow: double(item, "window_low"),
                cumulativePnl: double(item, "cumulative_pnl") ?? 0,
                lossCapEnabled: bool(item, "funded_loss_cap_enabled"),
                lossCapPct: double(item, "loss_cap_exit_pct") ?? 0.95,
                lastError: string(item, "last_error")
            )
        }
    }

    static func parseTrendPilotHistoryRows(_ array: [[String: Any]]?) -> [TrendPilotHistoryRow] {
        guard let array else { return [] }
        return array.map { item in
            TrendPilotHistoryRow(
                runId: string(item, "run_id"),
                accountId: string(item, "account_id"),
                accountName: string(item, "account_name"),
                symbol: string(item, "symbol"),
                displaySymbol: string(item, "display_symbol", fallback: string(item, "symbol")),
                status: string(item, "status"),
                rollCount: int(item, "roll_count"),
                startedAt: string(item, "started_at"),
                totalPnl: double(item, "total_pnl"),
                closedTrades: int(item, "closed_trades"),
                maxDrawdown: double(item, "max_drawdown")
            )
        }
    }

    static func parseTrendPilotBacktests(_ array: [[String: Any]]?) -> [TrendPilotBacktestRow] {
        guard let array else { return [] }
        return array.map { item in
            TrendPilotBacktestRow(
                resultId: string(item, "result_id"),
                symbol: string(item, "symbol"),
                displaySymbol: string(item, "display_symbol", fallback: string(item, "symbol")),
                fromDate: string(item, "from_date"),
                toDate: string(item, "to_date"),
                quantity: double(item, "quantity") ?? 0.01,
                totalPnl: double(item, "total_pnl"),
                closedTrades: int(item, "closed_trades"),
                rollCount: int(item, "roll_count"),
                maxDrawdown: double(item, "max_drawdown")
            )
        }
    }

    static func parseTrendPilotRolls(_ array: [[String: Any]]?) -> [TrendPilotRollRow] {
        guard let array else { return [] }
        return array.map { item in
            TrendPilotRollRow(
                eventType: string(item, "event_type"),
                eventTime: string(item, "event_time"),
                fromSide: string(item, "from_side"),
                toSide: string(item, "to_side"),
                pnlUpdate: double(item, "pnl_update") ?? 0,
                cumulativePnl: double(item, "cumulative_pnl") ?? 0,
                message: string(item, "message")
            )
        }
    }

    static func parseTrapReversalRuns(_ array: [[String: Any]]?) -> [TrapReversalRunRow] {
        guard let array else { return [] }
        return array.map { item in
            TrapReversalRunRow(
                symbol: string(item, "symbol"),
                displaySymbol: string(item, "display_symbol", fallback: string(item, "symbol")),
                state: string(item, "state"),
                riskAmount: double(item, "risk_amount") ?? 0
            )
        }
    }

    static func parseTrapReversalLevels(_ payload: [String: Any]) -> TrapReversalLevels {
        let supports = (payload["active_h1_supports"] as? [Any] ?? payload["supports"] as? [Any] ?? []).compactMap { value in
            if let number = value as? Double { return number }
            if let number = value as? Int { return Double(number) }
            return nil
        }
        let resistances = (payload["active_h1_resistances"] as? [Any] ?? payload["resistances"] as? [Any] ?? []).compactMap { value in
            if let number = value as? Double { return number }
            if let number = value as? Int { return Double(number) }
            return nil
        }
        return TrapReversalLevels(
            symbol: string(payload, "symbol"),
            displaySymbol: string(payload, "display_symbol", fallback: string(payload, "symbol")),
            supports: supports,
            resistances: resistances,
            priceDigits: int(payload, "price_digits")
        )
    }
}

enum ApiError: LocalizedError {
    case invalidResponse
    case http(status: Int, detail: String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse: return "Invalid server response"
        case .http(_, let detail): return detail
        }
    }
}
