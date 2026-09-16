import Foundation
import SwiftUI

func normalizeSymbolKey(_ symbol: String?) -> String {
    (symbol ?? "")
        .uppercased()
        .replacingOccurrences(of: "/", with: "")
        .replacingOccurrences(of: "-", with: "")
}

func symbolPriceDigitEntries(brokerSymbol: String, requestedSymbol: String?, digits: Int) -> [String: Int] {
    let clamped = min(max(digits, 0), 10)
    var entries: [String: Int] = [:]
    let brokerKey = normalizeSymbolKey(brokerSymbol)
    let requestedKey = normalizeSymbolKey(requestedSymbol)
    if !brokerKey.isEmpty { entries[brokerKey] = clamped }
    if !requestedKey.isEmpty { entries[requestedKey] = clamped }
    return entries
}

private func decimalPlaces(_ value: Double?) -> Int {
    guard let value, value.isFinite else { return 0 }
    var text = String(format: "%.10f", value)
    while text.hasSuffix("0") { text.removeLast() }
    if text.hasSuffix(".") { text.removeLast() }
    guard let dot = text.firstIndex(of: ".") else { return 0 }
    return min(text.distance(from: dot, to: text.endIndex) - 1, 10)
}

private func fallbackPriceDigitsForSymbol(_ symbol: String?) -> Int {
    let upper = (symbol ?? "").uppercased()
    if upper.contains("JPY") { return 3 }
    if upper.contains("XAU") || upper.contains("GOLD") { return 2 }
    if upper.contains("BTC") || upper.contains("ETH") || upper.contains("US30") || upper.contains("NAS") || upper.contains("SPX") { return 2 }
    return 5
}

func resolvePriceDigits(symbol: String?, priceDigits: [String: Int], relatedValues: [Double?]) -> Int {
    let key = normalizeSymbolKey(symbol)
    if let digits = priceDigits[key] { return min(max(digits, 0), 10) }
    let inferred = relatedValues.compactMap { decimalPlaces($0) }.max() ?? 0
    if inferred > 0 { return min(inferred, 10) }
    return fallbackPriceDigitsForSymbol(symbol)
}

func formatPrice(
    _ value: Double?,
    symbol: String? = nil,
    priceDigits: [String: Int] = [:],
    relatedValues: [Double?] = []
) -> String {
    guard let value else { return "-" }
    let digits = resolvePriceDigits(symbol: symbol, priceDigits: priceDigits, relatedValues: relatedValues + [value])
    return String(format: "%.\(digits)f", value)
}

func formatQty(_ value: Double?) -> String {
    guard let value else { return "-" }
    return String(format: "%.2f", value)
}

func formatMoney(_ value: Double) -> String {
    let prefix = value >= 0 ? "+" : ""
    return prefix + String(format: "%.2f", value)
}

func pnlForegroundColor(_ value: Double) -> Color {
    if value > 0 { return AppColors.success }
    if value < 0 { return AppColors.danger }
    return AppColors.textPrimary
}

func accountDisplayName(_ name: String) -> String {
    let trimmed = name.replacingOccurrences(of: #"\s*\([^)]*\)\s*$"#, with: "", options: .regularExpression)
    return trimmed.isEmpty ? name : trimmed
}

func formatAccountBalance(_ account: AccountRow?) -> String? {
    guard let value = account?.equityBalance, value.isFinite else { return nil }
    let code = account?.currencyCode.uppercased() ?? "USD"
    let formatter = NumberFormatter()
    formatter.numberStyle = .currency
    formatter.currencyCode = code
    formatter.locale = Locale(identifier: "en_US")
    return formatter.string(from: NSNumber(value: value)) ?? String(format: "%.2f", value)
}

func lookupAccount(_ accounts: [AccountRow], accountId: String) -> AccountRow? {
    accounts.first { $0.id == accountId }
}

func plainStatus(_ value: String) -> String {
    let words = value.trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
        .split { $0 == "_" || $0 == " " }
        .map(String.init)
        .filter { !$0.isEmpty }
    guard let first = words.first else { return "-" }
    return ([first.capitalized] + words.dropFirst()).joined(separator: " ")
}

func orderEventFailureReason(_ event: OrderEventRow) -> String? {
    if let reason = event.failureReason, !reason.isEmpty { return reason }
    guard let payloadJson = event.payloadJson,
          let data = payloadJson.data(using: .utf8),
          let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
        return nil
    }
    for key in ["error", "failure_reason", "reason"] {
        if let value = payload[key] as? String, !value.isEmpty {
            return value
        }
    }
    return nil
}

func orderEventPriceContext(_ event: OrderEventRow) -> String? {
    guard let payloadJson = event.payloadJson,
          let data = payloadJson.data(using: .utf8),
          let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
        return nil
    }
    var parts: [String] = []
    if let side = payload["side"] as? String, !side.isEmpty {
        parts.append(side.uppercased())
    }
    func appendPrice(_ keys: [String], label: String) {
        for key in keys {
            guard let value = payload[key] else { continue }
            let number: Double?
            if let doubleValue = value as? Double {
                number = doubleValue
            } else if let intValue = value as? Int {
                number = Double(intValue)
            } else if let stringValue = value as? String {
                number = Double(stringValue)
            } else {
                number = nil
            }
            guard let number, number.isFinite, number > 0 else { continue }
            let text = String(format: "%g", number)
            parts.append("\(label) \(text)")
            break
        }
    }
    appendPrice(["entry", "price"], label: "entry")
    appendPrice(["stop_loss", "sl"], label: "SL")
    appendPrice(["target", "tp"], label: "TP")
    if let quantity = payload["quantity"] as? Double, quantity > 0 {
        parts.append("qty \(quantity)")
    } else if let quantity = payload["volume"] as? Double, quantity > 0 {
        parts.append("qty \(quantity)")
    }
    let bid = (payload["bid"] as? Double)
    let ask = (payload["ask"] as? Double)
    if (bid ?? 0) > 0 || (ask ?? 0) > 0 {
        let bidText = (bid ?? 0) > 0 ? String(format: "%g", bid!) : "-"
        let askText = (ask ?? 0) > 0 ? String(format: "%g", ask!) : "-"
        parts.append("bid \(bidText) ask \(askText)")
    }
    return parts.isEmpty ? nil : parts.joined(separator: " · ")
}

func humanizeEventType(_ value: String) -> String { plainStatus(value) }

func currentWatchPrice(_ row: WatchRow, prices: [String: Double]) -> Double? {
    prices[row.symbol.uppercased()] ?? row.price
}

func symbolSubtitle(_ symbol: String) -> String {
    let upper = symbol.uppercased()
    if upper.hasPrefix("XAU") { return "Gold / USD" }
    if upper.hasPrefix("XAG") { return "Silver / USD" }
    if upper.count >= 6 {
        let base = String(upper.prefix(3))
        let quote = String(upper.dropFirst(3).prefix(3))
        return "\(base) / \(quote)"
    }
    return "International"
}

func normalizeHost(_ raw: String) -> String {
    var host = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        .replacingOccurrences(of: "https://", with: "")
        .replacingOccurrences(of: "http://", with: "")
        .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    if !host.isEmpty && !host.contains(":") {
        host += ":5173"
    }
    return host
}

func frontendBase(_ host: String) -> String {
    let trimmed = host.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.hasPrefix("http") { return String(trimmed.trimmingCharacters(in: CharacterSet(charactersIn: "/"))) }
    return "http://\(normalizeHost(trimmed))"
}

func hostIPAddress(_ host: String) -> String {
    normalizeHost(host).split(separator: ":", maxSplits: 1).first.map(String.init) ?? normalizeHost(host)
}

func isPrivateLANHost(_ host: String) -> Bool {
    let ip = hostIPAddress(host).lowercased()
    if ip == "localhost" || ip == "127.0.0.1" { return true }
    let parts = ip.split(separator: ".").compactMap { Int($0) }
    guard parts.count == 4 else { return false }
    switch parts[0] {
    case 10:
        return true
    case 172:
        return parts[1] >= 16 && parts[1] <= 31
    case 192:
        return parts[1] == 168
    default:
        return false
    }
}

func hostConnectError(_ host: String, ping: PingResult) -> String {
    if isPrivateLANHost(host) {
        var message = "Could not reach \(host) on your Wi-Fi."
        if let detail = ping.error, !detail.isEmpty {
            message += " \(detail)"
        }
        message += " Tap Save and connect, then tap Allow if iPhone asks for Local Network access. SignalBridge only appears in Settings → Privacy & Security → Local Network after that prompt."
        return message
    }

    var message = "Could not reach \(host)."
    if let detail = ping.error, !detail.isEmpty {
        message += " \(detail)"
        if detail.localizedCaseInsensitiveContains("App Transport Security") {
            message += " Delete SignalBridge, Clean Build Folder in Xcode (Shift+Cmd+K), reinstall, and try again."
        }
    } else if let status = ping.statusCode {
        message += " HTTP \(status)."
    }
    message += " This is a public internet address (\(hostIPAddress(host))), not a home Wi-Fi address like 192.168.x.x, so Local Network settings do not apply. If the PC is on the same Wi-Fi as your phone, run ipconfig on Windows and use that IPv4 address with :5173."
    return message
}

func currencyFlags(_ symbol: String) -> (String, String)? {
    let upper = symbol.uppercased()
    guard upper.count >= 6, !upper.hasPrefix("XAU"), !upper.hasPrefix("XAG") else { return nil }
    let base = String(upper.prefix(3))
    let quote = String(upper.dropFirst(3).prefix(3))
    let map: [String: String] = [
        "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵", "CHF": "🇨🇭",
        "AUD": "🇦🇺", "CAD": "🇨🇦", "NZD": "🇳🇿", "SGD": "🇸🇬", "HKD": "🇭🇰"
    ]
    guard let baseFlag = map[base], let quoteFlag = map[quote] else { return nil }
    return (baseFlag, quoteFlag)
}

func isClosedOrderStatus(_ status: String) -> Bool {
    ["CLOSED", "CANCELLED", "FAILED"].contains(status.uppercased())
}

func orderAccountId(_ row: OrderRow) -> String {
    row.accountId.isEmpty ? (row.plannerPlanAccountId ?? "") : row.accountId
}

private func isPresentNumber(_ value: Double?) -> Bool {
    guard let value, value.isFinite else { return false }
    return value > 0
}

func normalizeLiveOrders(_ rows: [OrderRow]) -> [OrderRow] {
    enum SeqEntry {
        case row(OrderRow)
        case position(String)
    }
    var positionGroups: [String: [OrderRow]] = [:]
    var sequence: [SeqEntry] = []
    for row in rows {
        let status = row.status.uppercased()
        let positionId = row.metaPositionId?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !positionId.isEmpty, ["FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"].contains(status) else {
            sequence.append(.row(row))
            continue
        }
        let key = "\(orderAccountId(row)):\(positionId)"
        if positionGroups[key] == nil {
            positionGroups[key] = []
            sequence.append(.position(key))
        }
        positionGroups[key, default: []].append(row)
    }
    func pickPrimary(_ duplicates: [OrderRow]) -> OrderRow {
        let tracked = duplicates.filter { ($0.externalSource ?? "").uppercased() != "BROKER_IMPORT" }
        let pool = tracked.isEmpty ? duplicates : tracked
        return pool.sorted { $0.id < $1.id }.first!
    }
    return sequence.map { entry in
        switch entry {
        case .row(let row):
            return row
        case .position(let key):
            let duplicates = positionGroups[key] ?? []
            if duplicates.count == 1 { return duplicates[0] }
            var merged = pickPrimary(duplicates)
            if !isPresentNumber(merged.target), let donor = duplicates.first(where: { isPresentNumber($0.target) }) {
                merged = OrderRow(
                    id: merged.id, accountId: merged.accountId, symbol: merged.symbol, side: merged.side,
                    status: merged.status, orderType: merged.orderType, entry: merged.entry, stopLoss: merged.stopLoss,
                    target: donor.target, quantity: merged.quantity, positionQuantity: merged.positionQuantity,
                    unrealizedPl: merged.unrealizedPl, realizedPl: merged.realizedPl, dryRun: merged.dryRun,
                    failureReason: merged.failureReason, placementFallbackReason: merged.placementFallbackReason,
                    comment: merged.comment, metaPositionId: merged.metaPositionId, externalSource: merged.externalSource,
                    rrRatio: merged.rrRatio, isOpenPosition: merged.isOpenPosition, plannerPlanAccountId: merged.plannerPlanAccountId,
                    brokerInfoAccountId: merged.brokerInfoAccountId, brokerInfoAccountName: merged.brokerInfoAccountName,
                    brokerInfoAvailableMargin: merged.brokerInfoAvailableMargin, createdAt: merged.createdAt,
                    openedAt: merged.openedAt, closedAt: merged.closedAt, updatedAt: merged.updatedAt
                )
            }
            if !isPresentNumber(merged.stopLoss), let donor = duplicates.first(where: { isPresentNumber($0.stopLoss) }) {
                merged = OrderRow(
                    id: merged.id, accountId: merged.accountId, symbol: merged.symbol, side: merged.side,
                    status: merged.status, orderType: merged.orderType, entry: merged.entry, stopLoss: donor.stopLoss,
                    target: merged.target, quantity: merged.quantity, positionQuantity: merged.positionQuantity,
                    unrealizedPl: merged.unrealizedPl, realizedPl: merged.realizedPl, dryRun: merged.dryRun,
                    failureReason: merged.failureReason, placementFallbackReason: merged.placementFallbackReason,
                    comment: merged.comment, metaPositionId: merged.metaPositionId, externalSource: merged.externalSource,
                    rrRatio: merged.rrRatio, isOpenPosition: merged.isOpenPosition, plannerPlanAccountId: merged.plannerPlanAccountId,
                    brokerInfoAccountId: merged.brokerInfoAccountId, brokerInfoAccountName: merged.brokerInfoAccountName,
                    brokerInfoAvailableMargin: merged.brokerInfoAvailableMargin, createdAt: merged.createdAt,
                    openedAt: merged.openedAt, closedAt: merged.closedAt, updatedAt: merged.updatedAt
                )
            }
            if !isPresentNumber(merged.entry), let donor = duplicates.first(where: { isPresentNumber($0.entry) }) {
                merged = OrderRow(
                    id: merged.id, accountId: merged.accountId, symbol: merged.symbol, side: merged.side,
                    status: merged.status, orderType: merged.orderType, entry: donor.entry, stopLoss: merged.stopLoss,
                    target: merged.target, quantity: merged.quantity, positionQuantity: merged.positionQuantity,
                    unrealizedPl: merged.unrealizedPl, realizedPl: merged.realizedPl, dryRun: merged.dryRun,
                    failureReason: merged.failureReason, placementFallbackReason: merged.placementFallbackReason,
                    comment: merged.comment, metaPositionId: merged.metaPositionId, externalSource: merged.externalSource,
                    rrRatio: merged.rrRatio, isOpenPosition: merged.isOpenPosition, plannerPlanAccountId: merged.plannerPlanAccountId,
                    brokerInfoAccountId: merged.brokerInfoAccountId, brokerInfoAccountName: merged.brokerInfoAccountName,
                    brokerInfoAvailableMargin: merged.brokerInfoAvailableMargin, createdAt: merged.createdAt,
                    openedAt: merged.openedAt, closedAt: merged.closedAt, updatedAt: merged.updatedAt
                )
            }
            if merged.side.isEmpty, let donor = duplicates.first(where: { !$0.side.isEmpty }) {
                merged = OrderRow(
                    id: merged.id, accountId: merged.accountId, symbol: merged.symbol, side: donor.side,
                    status: merged.status, orderType: merged.orderType, entry: merged.entry, stopLoss: merged.stopLoss,
                    target: merged.target, quantity: merged.quantity, positionQuantity: merged.positionQuantity,
                    unrealizedPl: merged.unrealizedPl, realizedPl: merged.realizedPl, dryRun: merged.dryRun,
                    failureReason: merged.failureReason, placementFallbackReason: merged.placementFallbackReason,
                    comment: merged.comment, metaPositionId: merged.metaPositionId, externalSource: merged.externalSource,
                    rrRatio: merged.rrRatio, isOpenPosition: merged.isOpenPosition, plannerPlanAccountId: merged.plannerPlanAccountId,
                    brokerInfoAccountId: merged.brokerInfoAccountId, brokerInfoAccountName: merged.brokerInfoAccountName,
                    brokerInfoAvailableMargin: merged.brokerInfoAvailableMargin, createdAt: merged.createdAt,
                    openedAt: merged.openedAt, closedAt: merged.closedAt, updatedAt: merged.updatedAt
                )
            }
            return merged
        }
    }
}

private func parseAppTimestamp(_ value: String?) -> TimeInterval {
    guard let value, !value.isEmpty else { return 0 }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let date = formatter.date(from: value) ?? ISO8601DateFormatter().date(from: value.hasSuffix("Z") ? value : "\(value)Z") {
        return date.timeIntervalSince1970
    }
    return 0
}

struct OrderedRows {
    let active: [OrderRow]
    let closed: [OrderRow]
}

func orderActiveAndClosed(_ rows: [OrderRow]) -> OrderedRows {
    let statusPriority = [
        "POSITION_OPEN": 0, "PARTIALLY_CLOSED": 1, "FILLED": 2, "PENDING": 3, "PLACEMENT_PENDING": 4
    ]
    func compare(_ left: OrderRow, _ right: OrderRow, active: Bool) -> Bool {
        let leftPriority = statusPriority[left.status.uppercased()] ?? 99
        let rightPriority = statusPriority[right.status.uppercased()] ?? 99
        if leftPriority != rightPriority { return leftPriority < rightPriority }
        let candidates = active ? [left.openedAt, left.createdAt] : [left.closedAt, left.updatedAt, left.createdAt]
        let rightCandidates = active ? [right.openedAt, right.createdAt] : [right.closedAt, right.updatedAt, right.createdAt]
        let leftTime = candidates.compactMap { parseAppTimestamp($0) }.filter { $0 > 0 }.max() ?? 0
        let rightTime = rightCandidates.compactMap { parseAppTimestamp($0) }.filter { $0 > 0 }.max() ?? 0
        if leftTime != rightTime { return leftTime > rightTime }
        return left.id < right.id
    }
    let activeRows = rows.filter { !isClosedOrderStatus($0.status) }.sorted { compare($0, $1, active: true) }
    let closedRows = rows.filter { isClosedOrderStatus($0.status) }.sorted { compare($0, $1, active: false) }
    return OrderedRows(active: activeRows, closed: closedRows)
}

func brokerLabel(_ row: OrderRow) -> String {
    row.brokerInfoAccountName?.isEmpty == false ? row.brokerInfoAccountName! : "Unknown broker"
}

func accountGroupLabel(_ row: OrderRow, accounts: [AccountRow]) -> String {
    let account = lookupAccount(accounts, accountId: orderAccountId(row))
    let name = account?.name ?? brokerLabel(row)
    let balance = account?.availableMargin ?? row.brokerInfoAvailableMargin
    if let balance { return "\(name) · Bal \(formatMoney(balance))" }
    return name
}

struct AccountGroup<T> {
    let key: String
    let label: String
    let sortName: String
    var rows: [T]
}

func groupRowsByAccount(_ rows: [OrderRow], accounts: [AccountRow]) -> [(String, String, [OrderRow])] {
    var groups: [String: AccountGroup<OrderRow>] = [:]
    for row in rows {
        let accountId = orderAccountId(row)
        let key = accountId.isEmpty ? "label:\(brokerLabel(row))" : accountId
        if groups[key] == nil {
            let account = lookupAccount(accounts, accountId: accountId)
            groups[key] = AccountGroup(
                key: key,
                label: accountGroupLabel(row, accounts: accounts),
                sortName: (account?.name ?? brokerLabel(row)).lowercased(),
                rows: []
            )
        }
        groups[key]?.rows.append(row)
    }
    return groups.values
        .sorted { ($0.sortName, $0.key) < ($1.sortName, $1.key) }
        .map { ($0.key, $0.label, $0.rows.sorted { ($0.symbol, $0.id) < ($1.symbol, $1.id) }) }
}

func inferPositionDirection(_ row: OrderRow) -> String {
    if let entry = row.entry, entry > 0, let sl = row.stopLoss, isPresentNumber(sl) {
        return sl < entry ? "LONG" : "SHORT"
    }
    if let entry = row.entry, entry > 0, let tp = row.target, isPresentNumber(tp) {
        return tp > entry ? "LONG" : "SHORT"
    }
    switch row.side.uppercased() {
    case "BUY": return "LONG"
    case "SELL": return "SHORT"
    default: return ""
    }
}

func buildDerivedOrders(positionRows: [OrderRow], pendingRows: [OrderRow]) -> (open: [OrdersTabRow], stop: [OrdersTabRow]) {
    var open: [OrdersTabRow] = []
    var stop: [OrdersTabRow] = []
    for row in pendingRows {
        let tabRow = OrdersTabRow(
            id: row.id, symbol: row.symbol, side: row.side,
            orderTypeLabel: ordersTabTypeLabel(row.orderType), price: row.entry, quantity: row.quantity,
            status: row.status, derived: false, editable: true, sourceOrder: row,
            accountId: orderAccountId(row), brokerInfoAccountName: row.brokerInfoAccountName
        )
        if row.orderType.uppercased() == "LIMIT" { open.append(tabRow) } else { stop.append(tabRow) }
    }
    for row in positionRows {
        let direction = inferPositionDirection(row)
        let exitSide = direction == "LONG" ? "SELL" : direction == "SHORT" ? "BUY" : ""
        let quantity = row.positionQuantity ?? row.quantity
        if isPresentNumber(row.target) {
            open.append(OrdersTabRow(
                id: "\(row.id)-tp", symbol: row.symbol, side: exitSide, orderTypeLabel: "Take Profit",
                price: row.target, quantity: quantity, status: "WORKING", derived: true, editable: false,
                sourceOrder: nil, accountId: orderAccountId(row), brokerInfoAccountName: row.brokerInfoAccountName
            ))
        }
        if isPresentNumber(row.stopLoss) {
            stop.append(OrdersTabRow(
                id: "\(row.id)-sl", symbol: row.symbol, side: exitSide, orderTypeLabel: "Stop Loss",
                price: row.stopLoss, quantity: quantity, status: "WORKING", derived: true, editable: false,
                sourceOrder: nil, accountId: orderAccountId(row), brokerInfoAccountName: row.brokerInfoAccountName
            ))
        }
    }
    return (open, stop)
}

func ordersTabTypeLabel(_ orderType: String) -> String {
    switch orderType.uppercased() {
    case "LIMIT": return "Limit"
    case "SL": return "Stop"
    case "MARKET": return "Market"
    default: return plainStatus(orderType)
    }
}

func groupOrdersTabRows(_ rows: [OrdersTabRow], accounts: [AccountRow]) -> [(String, [OrdersTabRow])] {
    var groups: [String: AccountGroup<OrdersTabRow>] = [:]
    for row in rows {
        let key = row.accountId.isEmpty ? "label:\(row.brokerInfoAccountName ?? "Unknown broker")" : row.accountId
        if groups[key] == nil {
            let account = lookupAccount(accounts, accountId: row.accountId)
            let name = account?.name ?? row.brokerInfoAccountName ?? "Unknown broker"
            let label = account?.availableMargin.map { "\(name) · Bal \(formatMoney($0))" } ?? name
            groups[key] = AccountGroup(key: key, label: label, sortName: name.lowercased(), rows: [])
        }
        groups[key]?.rows.append(row)
    }
    return groups.values
        .sorted { ($0.sortName, $0.label) < ($1.sortName, $1.label) }
        .map { ($0.label, $0.rows.sorted { ($0.symbol, $0.id) < ($1.symbol, $1.id) }) }
}

func closedQuantitySubtext(_ order: OrderRow) -> String? {
    guard let total = order.quantity, let remaining = order.positionQuantity else { return nil }
    let closed = total - remaining
    guard closed > 0.0001 else { return nil }
    return "Closed \(formatQty(closed))"
}

func continuationFailureActiveStatuses() -> Set<String> {
    ["WAITING_PIVOT_BREACH", "PIVOT_BREACHED_WAITING_SETUP", "ORDER_PENDING", "ORDER_OPEN"]
}

func normalizeCfSelection(_ currentIds: [String], accounts: [AccountRow], activeAccountId: String) -> [String] {
    let unique = Array(Set(currentIds.filter { !$0.isEmpty }))
    let activeAccount = accounts.first { $0.id == activeAccountId }
    let activeScope = activeAccount?.brokerScope() ?? ""
    let scoped = unique.filter { id in
        guard let account = accounts.first(where: { $0.id == id }) else { return false }
        return account.brokerScope() == activeScope
    }
    var withActive = scoped
    if !activeAccountId.isEmpty, !withActive.contains(activeAccountId) {
        withActive.insert(activeAccountId, at: 0)
    }
    return Array(withActive.prefix(2))
}

func isCfAccountDisabled(_ account: AccountRow, selectedIds: [String], accounts: [AccountRow], activeAccountId: String) -> Bool {
    if account.id == activeAccountId { return true }
    if let active = accounts.first(where: { $0.id == activeAccountId }), account.brokerScope() != active.brokerScope() {
        return true
    }
    return selectedIds.count >= 2 && !selectedIds.contains(account.id)
}

func internationalAccounts(_ accounts: [AccountRow]) -> [AccountRow] {
    accounts.filter { ($0.marketType ?? "INTERNATIONAL").uppercased() == "INTERNATIONAL" }
}

func trendPilotRunMatchesSymbol(_ run: TrendPilotRunRow, symbol: String) -> Bool {
    let key = symbol.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
    return [run.symbol, run.displaySymbol].contains { $0.uppercased() == key }
}

func trendPilotRunStatusKey(_ run: TrendPilotRunRow) -> String {
    switch run.state.uppercased() {
    case "ARMED": return "armed"
    case "LONG": return "long"
    case "SHORT": return "short"
    case "REVERSING": return "reversing"
    default: return run.lastError.isEmpty ? "running" : "error"
    }
}
