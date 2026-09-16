import SwiftUI

struct DashboardView: View {
    @EnvironmentObject private var vm: AppViewModel

    var body: some View {
        VStack(spacing: 0) {
            if vm.state.dashboardSyncing || vm.state.actionBusy {
                ProgressView().tint(AppColors.accent)
                Text(vm.state.actionBusy ? vm.state.actionMessage : vm.state.syncMessage)
                    .font(.caption2)
                    .foregroundStyle(AppColors.textSecondary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 6)
                    .background(AppColors.surfaceMuted)
            }
            DashboardTopBar()
            if !vm.state.error.isEmpty {
                ErrorBanner(text: vm.state.error).padding(.horizontal, 16).padding(.top, 8)
            }
            TabView(selection: Binding(
                get: { vm.state.page },
                set: { newPage in
                    guard newPage != vm.state.page else { return }
                    vm.changePage(newPage)
                }
            )) {
                ForEach(AppPage.allCases) { page in
                    ScrollView {
                        VStack(spacing: 12) {
                            switch page {
                            case .watchlist: WatchlistScreen()
                            case .trading: TradingScreen()
                            case .positions: PositionsScreen()
                            case .strategies: StrategiesScreen()
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                    }
                    .tag(page)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .never))
            DashboardBottomBar()
        }
        .background(
            LinearGradient(
                colors: [AppColors.background, AppColors.backgroundBottom],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()
        )
        .sheet(isPresented: Binding(get: { vm.state.showTradeSheet }, set: { if !$0 { vm.closeTradeSheet() } })) {
            TradeOrderSheet().presentationDetents([.large])
        }
        .sheet(isPresented: Binding(get: { vm.state.showOrderEditSheet }, set: { if !$0 { vm.closeOrderEditSheet() } })) {
            if let order = vm.state.orderEditTarget {
                OrderEditSheet(order: order).presentationDetents([.medium, .large])
            }
        }
    }
}

struct DashboardTopBar: View {
    @EnvironmentObject private var vm: AppViewModel
    @State private var menuOpen = false

    var body: some View {
        HStack {
            AppBrandIcon(size: 46)
            VStack(alignment: .leading, spacing: 2) {
                Text(vm.state.fullName.isEmpty ? vm.state.username : vm.state.fullName)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(AppColors.textPrimary)
                    .lineLimit(1)
                Text("SignalBridge")
                    .font(.caption)
                    .foregroundStyle(AppColors.textSecondary)
            }
            Spacer()
            HStack(spacing: 6) {
                Circle()
                    .fill(vm.state.liveStatus == "CONNECTED" ? AppColors.success : AppColors.textMuted)
                    .frame(width: 8, height: 8)
                Text(vm.state.liveStatus == "CONNECTED" ? "Live" : vm.state.liveStatus.capitalized)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(vm.state.liveStatus == "CONNECTED" ? AppColors.success : AppColors.textMuted)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(vm.state.liveStatus == "CONNECTED" ? AppColors.successSoft : AppColors.surfaceMuted)
            .clipShape(Capsule())
            Menu {
                Button("Refresh") { vm.refresh() }
                Divider()
                ForEach([AppAppearance.system, .automatic, .light, .dark], id: \.rawValue) { appearance in
                    Button {
                        vm.setAppearance(appearance)
                    } label: {
                        if vm.state.appearance == appearance {
                            Label(appearance.label, systemImage: "checkmark")
                        } else {
                            Text(appearance.label)
                        }
                    }
                }
                Button("Logout", role: .destructive) { vm.logout() }
            } label: {
                Text("Menu")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AppColors.accent)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(AppColors.accentSoft)
                    .clipShape(Capsule())
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(AppColors.surface)
        .overlay(Rectangle().frame(height: 1).foregroundStyle(AppColors.skyBorder), alignment: .bottom)
    }
}

struct DashboardBottomBar: View {
    @EnvironmentObject private var vm: AppViewModel

    var body: some View {
        HStack {
            ForEach(AppPage.allCases) { page in
                Button {
                    withAnimation(.easeInOut(duration: 0.22)) {
                        vm.changePage(page)
                    }
                } label: {
                    VStack(spacing: 4) {
                        Image(systemName: page.systemImage)
                            .font(.system(size: 18, weight: vm.state.page == page ? .semibold : .regular))
                        Text(page.rawValue).font(.caption2)
                    }
                    .frame(maxWidth: .infinity)
                    .foregroundStyle(vm.state.page == page ? AppColors.accentDeep : AppColors.textMuted)
                    .padding(.vertical, 8)
                    .background(vm.state.page == page ? AppColors.accentSoft : Color.clear)
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(vm.state.page == page ? AppColors.skyBorder : Color.clear, lineWidth: 1)
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                }
            }
        }
        .padding(.horizontal, 8)
        .padding(.top, 6)
        .padding(.bottom, 4)
        .background(AppColors.surface)
        .overlay(Rectangle().frame(height: 1).foregroundStyle(AppColors.skyBorder), alignment: .top)
    }
}

struct WatchlistScreen: View {
    @EnvironmentObject private var vm: AppViewModel
    @State private var expandedSymbol = ""
    @State private var showAddSymbol = false
    @State private var previousPrices: [String: Double] = [:]
    @State private var directions: [String: String] = [:]

    var body: some View {
        VStack(spacing: 12) {
            ScreenHeader(title: "Watchlist", subtitle: "Live symbols from your platform", actionLabel: showAddSymbol ? "Done" : "+ Add") {
                showAddSymbol.toggle()
            }
            SummaryStrip()
            if showAddSymbol {
                CompactInlineForm(label: "Symbol", placeholder: "XAUUSD") { vm.addWatchSymbol($0); showAddSymbol = false }
            }
            if vm.state.watchlist.isEmpty {
                EmptyText(text: vm.state.dashboardSyncing ? "Loading watchlist..." : "No symbols yet. Tap + Add to subscribe.")
            }
            ForEach(vm.state.watchlist) { row in
                let symbol = row.symbol.uppercased()
                let livePrice = currentWatchPrice(row, prices: vm.state.prices)
                let expanded = expandedSymbol == symbol
                DataCard {
                    VStack(spacing: 8) {
                        HStack {
                            InstrumentBadge(symbol: symbol)
                            VStack(alignment: .leading) {
                                Text(symbol)
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(AppColors.textPrimary)
                                Text(symbolSubtitle(symbol)).font(.caption2).foregroundStyle(AppColors.textSecondary)
                            }
                            Spacer()
                            PriceMovement(
                                price: livePrice,
                                direction: directions[symbol] ?? "flat",
                                symbol: symbol,
                                priceDigits: vm.state.priceDigits
                            )
                        }
                        .contentShape(Rectangle())
                        .onTapGesture { expandedSymbol = expanded ? "" : symbol }
                        if expanded {
                            Divider()
                            HStack(spacing: 8) {
                                SecondaryButton(title: "Trade", compact: true) { vm.openTrade(symbol: symbol) }
                                SecondaryButton(title: "Remove", danger: true, compact: true) { vm.removeWatchSymbol(symbol) }
                                Spacer(minLength: 0)
                            }
                        }
                    }
                }
            }
        }
        .onChange(of: vm.state.prices) { _ in updateDirections() }
        .onAppear { updateDirections() }
    }

    private func updateDirections() {
        var latest: [String: Double] = [:]
        for row in vm.state.watchlist {
            if let price = currentWatchPrice(row, prices: vm.state.prices) {
                latest[row.symbol.uppercased()] = price
            }
        }
        guard !latest.isEmpty else { return }
        var next = directions
        for (symbol, price) in latest {
            if let previous = previousPrices[symbol] {
                if price > previous { next[symbol] = "up" }
                else if price < previous { next[symbol] = "down" }
            } else {
                next[symbol] = next[symbol] ?? "flat"
            }
        }
        previousPrices = latest
        directions = next
    }
}

struct TradingScreen: View {
    @EnvironmentObject private var vm: AppViewModel

    var body: some View {
        VStack(spacing: 12) {
            ScreenHeader(title: "Trade", subtitle: "Place manual orders on your MT5 account", actionLabel: "+ New order") {
                vm.showTradeForm()
            }
            SummaryStrip()
            DataCard {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Quick actions")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(AppColors.textPrimary)
                    Text("Open a new order sheet or trade directly from Watchlist.").font(.caption).foregroundStyle(AppColors.textSecondary)
                    PrimaryButton(title: "New order") { vm.showTradeForm() }
                }
            }
            if !vm.state.orders.isEmpty {
                Text("Recent activity").font(.caption.weight(.semibold)).foregroundStyle(AppColors.textSecondary)
                ForEach(vm.state.orders.prefix(3)) { order in
                    DataCard {
                        HStack {
                            VStack(alignment: .leading) {
                                Text("\(order.symbol) \(order.side)")
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(AppColors.textPrimary)
                                Text(plainStatus(order.status)).font(.caption).foregroundStyle(AppColors.textSecondary)
                            }
                            Spacer()
                            Text(formatMoney(order.unrealizedPl ?? 0))
                                .foregroundStyle((order.unrealizedPl ?? 0) >= 0 ? AppColors.success : AppColors.danger)
                                .fontWeight(.semibold)
                        }
                    }
                }
            }
        }
    }
}

struct TradeOrderSheet: View {
    @EnvironmentObject private var vm: AppViewModel
    @State private var symbol = ""
    @State private var orderType = "SL"
    @State private var side = "BUY"
    @State private var entry = ""
    @State private var stopLoss = ""
    @State private var target = ""
    @State private var retryableOrder = true
    @State private var automaticTradeManagement = true

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Defaults match the web trading ticket.").font(.caption).foregroundStyle(AppColors.textSecondary)
                    FormTextField(placeholder: "Symbol", text: $symbol, autocapitalization: .characters)
                    ChipRow(values: ["MARKET", "LIMIT", "SL"], selected: orderType) { orderType = $0 }
                    ChipRow(values: ["BUY", "SELL"], selected: side) { side = $0 }
                    FormTextField(placeholder: "Entry", text: $entry, keyboardType: .decimalPad, disabled: orderType == "MARKET")
                    FormTextField(placeholder: "Stop loss", text: $stopLoss, keyboardType: .decimalPad)
                    FormTextField(placeholder: "Target (optional)", text: $target, keyboardType: .decimalPad)
                    CompactToggle(title: "Automatic trade management", subtitle: "Book 50% at 4R; exit remainder at target.", checked: $automaticTradeManagement)
                    if orderType == "LIMIT" || orderType == "SL" {
                        CompactToggle(title: "Retryable order", subtitle: "Re-place once as SL after a clean stop hit.", checked: $retryableOrder)
                    }
                    PrimaryButton(title: "Place order") {
                        vm.placeOrder(symbol: symbol, orderType: orderType, side: side, entry: entry, stopLoss: stopLoss, target: target, retryableOrder: retryableOrder, automaticTradeManagement: automaticTradeManagement)
                    }
                }
                .padding(20)
            }
            .navigationTitle("New order")
            .onAppear { symbol = vm.state.tradeDraftSymbol }
        }
    }
}

struct OrderEditSheet: View {
    @EnvironmentObject private var vm: AppViewModel
    let order: OrderRow
    @State private var entry = ""
    @State private var stopLoss = ""
    @State private var target = ""
    @State private var quantity = ""

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    Text("\(order.symbol) \(order.side) · \(order.orderType)")
                        .font(.caption)
                        .foregroundStyle(AppColors.textSecondary)
                    Text("Changing quantity cancels the broker order and places a new one. Other changes update the pending order at the broker when quantity stays the same.")
                        .font(.caption)
                        .foregroundStyle(AppColors.textSecondary)
                    FormTextField(placeholder: "Entry", text: $entry, keyboardType: .decimalPad, disabled: order.orderType.uppercased() == "MARKET")
                    FormTextField(placeholder: "Stop loss", text: $stopLoss, keyboardType: .decimalPad)
                    FormTextField(placeholder: "Target (optional)", text: $target, keyboardType: .decimalPad)
                    FormTextField(placeholder: "Quantity", text: $quantity, keyboardType: .decimalPad)
                    PrimaryButton(title: "Save changes") {
                        vm.modifyOrder(order, entry: entry, stopLoss: stopLoss, target: target, quantity: quantity)
                    }
                }
                .padding(20)
            }
            .navigationTitle("Edit pending order")
            .onAppear {
                entry = order.entry.map { String($0) } ?? ""
                stopLoss = order.stopLoss.map { String($0) } ?? ""
                target = order.target.map { String($0) } ?? ""
                quantity = formatQty(order.quantity)
            }
        }
    }
}

struct CompactInlineForm: View {
    let label: String
    let placeholder: String
    let onSubmit: (String) -> Void
    @State private var value = ""

    var body: some View {
        DataCard {
            HStack {
                FormTextField(placeholder: placeholder, text: $value, autocapitalization: .characters)
                PrimaryButton(title: "Add", fullWidth: false) {
                    if !value.isEmpty { onSubmit(value.uppercased()); value = "" }
                }
            }
        }
    }
}


private struct PlPill: View {
    let amount: Double

    var body: some View {
        TinyPill(
            label: formatMoney(amount),
            background: amount >= 0 ? AppColors.successSoft : AppColors.dangerSoft,
            foreground: amount >= 0 ? AppColors.success : AppColors.danger
        )
    }
}

private struct AccountFilter: View {
    let accounts: [AccountRow]
    @Binding var selected: String

    private var label: String {
        if selected == "ALL" { return "All" }
        return accounts.first(where: { $0.id == selected })?.name ?? "Account"
    }

    var body: some View {
        Menu {
            ForEach(accounts) { account in
                Button(account.name) { selected = account.id }
            }
            Button("All") { selected = "ALL" }
        } label: {
            Text(label)
                .font(.caption.weight(.semibold))
                .foregroundStyle(AppColors.textSecondary)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .overlay(Capsule().stroke(AppColors.border))
        }
    }
}

private struct ClosedStatusFilter: View {
    @Binding var selected: String
    private let options = ["CLOSED", "CANCELLED", "FAILED", "ALL"]

    var body: some View {
        Menu {
            ForEach(options, id: \.self) { option in
                Button(plainStatus(option)) { selected = option }
            }
        } label: {
            Text(plainStatus(selected))
                .font(.caption.weight(.semibold))
                .foregroundStyle(AppColors.textSecondary)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .overlay(Capsule().stroke(AppColors.border))
        }
    }
}

private struct PositionsSectionHeader<Trailing: View>: View {
    let title: String
    let count: Int
    @ViewBuilder var trailing: () -> Trailing

    init(title: String, count: Int, @ViewBuilder trailing: @escaping () -> Trailing = { EmptyView() }) {
        self.title = title
        self.count = count
        self.trailing = trailing
    }

    var body: some View {
        HStack {
            Text(title.uppercased())
                .appSectionLabel()
            Spacer()
            HStack(spacing: 8) {
                trailing()
                Text("\(count)")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(AppColors.skyDeep)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(AppColors.skySoft)
                    .overlay(Capsule().stroke(AppColors.skyBorder))
                    .clipShape(Capsule())
            }
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 2)
    }
}

private struct PositionOrderCard: View {
    @EnvironmentObject private var vm: AppViewModel
    let order: OrderRow
    let expanded: Bool
    let showClosedPl: Bool
    let onToggleExpanded: () -> Void

    var body: some View {
        DataCard {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("\(order.symbol) \(order.side)").appHeadline()
                    Spacer()
                    StatusPill(label: order.status, positive: ["POSITION_OPEN", "FILLED", "PARTIALLY_CLOSED"].contains(order.status))
                }
                .contentShape(Rectangle())
                .onTapGesture { onToggleExpanded() }
                Text("Entry \(formatPrice(order.entry, symbol: order.symbol, priceDigits: vm.state.priceDigits, relatedValues: [order.stopLoss, order.target]))  SL \(formatPrice(order.stopLoss, symbol: order.symbol, priceDigits: vm.state.priceDigits, relatedValues: [order.entry, order.target]))  Target \(formatPrice(order.target, symbol: order.symbol, priceDigits: vm.state.priceDigits, relatedValues: [order.entry, order.stopLoss]))")
                    .font(.caption).foregroundStyle(AppColors.textSecondary)
                Text("Qty \(formatQty(order.positionQuantity ?? order.quantity))").font(.caption).foregroundStyle(AppColors.textSecondary)
                if let closedText = closedQuantitySubtext(order) {
                    Text(closedText).font(.caption2).foregroundStyle(AppColors.textMuted)
                }
                if let failureReason = order.failureReason, !failureReason.isEmpty {
                    Text("Failure: \(failureReason)")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(AppColors.danger)
                }
                if let placementReason = order.placementFallbackReason, !placementReason.isEmpty {
                    Text("Placement: \(placementReason)")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(AppColors.trap)
                }
                if showClosedPl {
                    Text(formatMoney(order.realizedPl ?? 0))
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle((order.realizedPl ?? 0) >= 0 ? AppColors.success : AppColors.danger)
                } else {
                    Text("Running P/L \(formatMoney(order.unrealizedPl ?? 0))  Booked P/L \(formatMoney(order.realizedPl ?? 0))")
                        .font(.caption).foregroundStyle(AppColors.textSecondary)
                }
                if order.dryRun {
                    Text("Forward Test - No Broker Order").font(.caption.weight(.semibold)).foregroundStyle(AppColors.trap)
                }
                HStack {
                    if ["PLACEMENT_PENDING", "PENDING"].contains(order.status) {
                        SecondaryButton(title: "Edit", compact: true) { vm.openOrderEditor(order) }
                        SecondaryButton(title: "Cancel", compact: true) { vm.cancelOrder(order.id) }
                    }
                    if ["FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"].contains(order.status) {
                        PrimaryButton(title: "Full Exit", fullWidth: false, compact: true) { vm.closeOrder(order) }
                    }
                    Spacer(minLength: 0)
                }
                if expanded {
                    OrderActivityTimeline(orderId: order.id)
                } else {
                    Text("Tap row to view trade activity").font(.caption2).foregroundStyle(AppColors.textSecondary)
                }
            }
        }
    }
}

private struct BrokerClosedTradeCard: View {
    @EnvironmentObject private var vm: AppViewModel
    let row: BrokerTradeHistoryRow

    var body: some View {
        DataCard {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text("\(row.symbol) \(row.type)").appHeadline()
                    Spacer()
                    StatusPill(label: "CLOSED", positive: false)
                }
                Text("Open \(formatPrice(row.openPrice, symbol: row.symbol, priceDigits: vm.state.priceDigits, relatedValues: [row.closePrice]))  Close \(formatPrice(row.closePrice, symbol: row.symbol, priceDigits: vm.state.priceDigits, relatedValues: [row.openPrice]))")
                    .font(.caption).foregroundStyle(AppColors.textSecondary)
                Text(formatMoney(row.netProfit))
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(row.netProfit >= 0 ? AppColors.success : AppColors.danger)
            }
        }
    }
}

private struct AccountGroupHeader: View {
    let label: String
    let count: Int

    var body: some View {
        HStack(spacing: 8) {
            Text(label.uppercased())
                .font(.caption2.weight(.bold))
                .foregroundStyle(AppColors.textSecondary)
            Text("\(count)")
                .font(.caption2.weight(.bold))
                .foregroundStyle(AppColors.textMuted)
                .padding(.horizontal, 8)
                .padding(.vertical, 2)
                .background(AppColors.surfaceMuted)
                .clipShape(Capsule())
        }
        .padding(.vertical, 4)
    }
}

private struct OrdersTabCard: View {
    @EnvironmentObject private var vm: AppViewModel
    let row: OrdersTabRow

    var body: some View {
        DataCard {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text("\(row.symbol) \(row.side)").appHeadline()
                    Spacer()
                    StatusPill(
                        label: row.derived ? "WORKING" : row.status,
                        positive: row.derived || ["PENDING", "PLACEMENT_PENDING"].contains(row.status.uppercased())
                    )
                }
                Text("\(row.orderTypeLabel)  Price \(formatPrice(row.price, symbol: row.symbol, priceDigits: vm.state.priceDigits))  Qty \(formatQty(row.quantity))")
                    .font(.caption).foregroundStyle(AppColors.textSecondary)
                if row.editable, let source = row.sourceOrder {
                    HStack(spacing: 8) {
                        SecondaryButton(title: "Edit", compact: true) { vm.openOrderEditor(source) }
                        SecondaryButton(title: "Cancel", compact: true) { vm.cancelOrder(source.id) }
                    }
                } else if row.derived {
                    Text("From position").font(.caption2).foregroundStyle(AppColors.textMuted)
                }
            }
        }
    }
}

struct PositionsScreen: View {
    @EnvironmentObject private var vm: AppViewModel
    @State private var expandedOrderId = ""
    @State private var closedStatusFilter = "CLOSED"
    @State private var closedAccountFilter = ""
    @State private var historyAccountFilter = ""
    @State private var historyTypeFilter = "all"
    @State private var historyPage = 1
    @State private var closedBrokerRows: [BrokerTradeHistoryRow] = []
    @State private var closedBrokerLoading = false
    @State private var closedBrokerError = ""
    @State private var brokerHistory: [BrokerTradeHistoryRow] = []
    @State private var historyLoading = false
    @State private var historyError = ""

    private var ordered: OrderedRows { orderActiveAndClosed(vm.state.orders) }
    private var positionRows: [OrderRow] {
        ordered.active.filter { ["FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"].contains($0.status.uppercased()) }
    }
    private var pendingRows: [OrderRow] {
        ordered.active.filter { ["PENDING", "PLACEMENT_PENDING"].contains($0.status.uppercased()) }
    }
    private var derivedOrders: (open: [OrdersTabRow], stop: [OrdersTabRow]) {
        buildDerivedOrders(positionRows: positionRows, pendingRows: pendingRows)
    }
    private var positionGroups: [(String, String, [OrderRow])] {
        groupRowsByAccount(positionRows, accounts: vm.state.accounts)
    }
    private var openOrderGroups: [(String, [OrdersTabRow])] {
        groupOrdersTabRows(derivedOrders.open, accounts: vm.state.accounts)
    }
    private var stopOrderGroups: [(String, [OrdersTabRow])] {
        groupOrdersTabRows(derivedOrders.stop, accounts: vm.state.accounts)
    }
    private var accountFilteredClosedOrders: [OrderRow] {
        if closedAccountFilter == "ALL" || closedAccountFilter.isEmpty { return ordered.closed }
        return ordered.closed.filter { orderAccountId($0) == closedAccountFilter }
    }
    private var usesBrokerClosedToday: Bool {
        closedStatusFilter == "CLOSED" || closedStatusFilter == "ALL"
    }
    private var localNonBrokerClosedOrders: [OrderRow] {
        if closedStatusFilter == "CLOSED" { return [] }
        return accountFilteredClosedOrders.filter { order in
            let status = order.status.uppercased()
            if status == "CLOSED" { return false }
            if closedStatusFilter == "ALL" { return status == "CANCELLED" || status == "FAILED" }
            return status == closedStatusFilter
        }
    }
    private var closedDisplayCount: Int {
        (usesBrokerClosedToday ? closedBrokerRows.count : 0) + localNonBrokerClosedOrders.count
    }
    private var totalClosedPl: Double {
        let brokerPl = usesBrokerClosedToday ? closedBrokerRows.reduce(0) { $0 + $1.netProfit } : 0
        let localPl = localNonBrokerClosedOrders.reduce(0) { $0 + ($1.realizedPl ?? 0) }
        return brokerPl + localPl
    }

    var body: some View {
        VStack(spacing: 12) {
            ScreenHeader(title: "Positions", subtitle: "Open positions, working orders, and history")
            SummaryStrip()
            ChipRow(values: ["Positions", "Orders", "History"], selected: vm.state.positionsTab) { vm.setPositionsTab($0) }
            switch vm.state.positionsTab {
            case "Orders":
                PositionsSectionHeader(title: "Open Orders", count: derivedOrders.open.count)
                if derivedOrders.open.isEmpty {
                    EmptyText(text: "No open orders for today yet.")
                } else {
                    ForEach(openOrderGroups, id: \.0) { label, rows in
                        AccountGroupHeader(label: label, count: rows.count)
                        ForEach(rows) { row in OrdersTabCard(row: row) }
                    }
                }
                PositionsSectionHeader(title: "Stop Orders", count: derivedOrders.stop.count)
                if derivedOrders.stop.isEmpty {
                    EmptyText(text: "No stop orders for today yet.")
                } else {
                    ForEach(stopOrderGroups, id: \.0) { label, rows in
                        AccountGroupHeader(label: label, count: rows.count)
                        ForEach(rows) { row in OrdersTabCard(row: row) }
                    }
                }
            case "History":
                HStack(spacing: 8) {
                    AccountFilter(accounts: vm.state.accounts, selected: $historyAccountFilter)
                    Menu {
                        ForEach(["all", "closed", "open"], id: \.self) { option in
                            Button(option.uppercased()) { historyTypeFilter = option; historyPage = 1 }
                        }
                    } label: {
                        Text(historyTypeFilter.uppercased())
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(AppColors.textSecondary)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .overlay(Capsule().stroke(AppColors.border))
                    }
                }
                if historyLoading {
                    EmptyText(text: "Loading broker trade history...")
                } else if !historyError.isEmpty {
                    EmptyText(text: historyError)
                } else if brokerHistory.isEmpty {
                    EmptyText(text: "No broker trade history found.")
                } else {
                    ForEach(brokerHistory) { row in BrokerClosedTradeCard(row: row) }
                    HStack(spacing: 8) {
                        SecondaryButton(title: "Previous", compact: true) { if historyPage > 1 { historyPage -= 1 } }
                            .disabled(historyPage <= 1)
                        Text("Page \(historyPage)").font(.caption).foregroundStyle(AppColors.textMuted)
                        SecondaryButton(title: "Next", compact: true) { historyPage += 1 }
                            .disabled(brokerHistory.count < 20)
                    }
                }
            default:
                PositionsSectionHeader(title: "Open Positions", count: positionRows.count)
                if positionRows.isEmpty {
                    EmptyText(text: "No open positions for today yet.")
                } else {
                    ForEach(positionGroups, id: \.0) { _, label, rows in
                        AccountGroupHeader(label: label, count: rows.count)
                        ForEach(rows) { order in
                            PositionOrderCard(
                                order: order,
                                expanded: expandedOrderId == order.id,
                                showClosedPl: false,
                                onToggleExpanded: { expandedOrderId = expandedOrderId == order.id ? "" : order.id }
                            )
                        }
                    }
                }
                PositionsSectionHeader(title: "Closed Today", count: closedDisplayCount) {
                    AccountFilter(accounts: vm.state.accounts, selected: $closedAccountFilter)
                    ClosedStatusFilter(selected: $closedStatusFilter)
                    PlPill(amount: totalClosedPl)
                }
                if !closedBrokerError.isEmpty {
                    EmptyText(text: closedBrokerError)
                } else if closedBrokerLoading && usesBrokerClosedToday {
                    EmptyText(text: "Loading today's closed broker trades...")
                } else if closedDisplayCount == 0 {
                    EmptyText(
                        text: closedStatusFilter == "ALL"
                            ? "No closed trades for today yet."
                            : closedStatusFilter == "CLOSED"
                                ? "No closed broker trades for today yet."
                                : "No \(plainStatus(closedStatusFilter).lowercased()) orders for today yet."
                    )
                } else {
                    if usesBrokerClosedToday {
                        ForEach(closedBrokerRows) { row in BrokerClosedTradeCard(row: row) }
                    }
                    ForEach(localNonBrokerClosedOrders) { order in
                        PositionOrderCard(
                            order: order,
                            expanded: expandedOrderId == order.id,
                            showClosedPl: true,
                            onToggleExpanded: { expandedOrderId = expandedOrderId == order.id ? "" : order.id }
                        )
                    }
                }
            }
        }
        .task(id: "\(vm.state.positionsTab)-\(closedAccountFilter)-\(closedStatusFilter)-\(vm.state.accounts.count)") {
            guard vm.state.positionsTab == "Positions", usesBrokerClosedToday else { return }
            closedBrokerLoading = true
            closedBrokerError = ""
            do {
                closedBrokerRows = try await vm.fetchClosedTodayBrokerTrades(
                    accountFilter: closedAccountFilter,
                    accounts: vm.state.accounts
                )
            } catch {
                closedBrokerRows = []
                closedBrokerError = error.localizedDescription
            }
            closedBrokerLoading = false
        }
        .task(id: "\(vm.state.positionsTab)-\(historyAccountFilter)-\(historyTypeFilter)-\(historyPage)") {
            guard vm.state.positionsTab == "History" else { return }
            historyLoading = true
            historyError = ""
            do {
                brokerHistory = try await vm.fetchBrokerTradeHistory(
                    accountId: historyAccountFilter == "ALL" ? nil : historyAccountFilter,
                    page: historyPage,
                    pageSize: 20,
                    type: historyTypeFilter
                )
            } catch {
                brokerHistory = []
                historyError = error.localizedDescription
            }
            historyLoading = false
        }
        .onAppear {
            if closedAccountFilter.isEmpty {
                closedAccountFilter = vm.state.selectedAccountId.isEmpty
                    ? (vm.state.accounts.first?.id ?? "")
                    : vm.state.selectedAccountId
            }
            if historyAccountFilter.isEmpty {
                historyAccountFilter = closedAccountFilter
            }
        }
        .onChange(of: vm.state.selectedAccountId) { next in
            guard closedAccountFilter != "ALL" else { return }
            if closedAccountFilter.isEmpty || !vm.state.accounts.contains(where: { $0.id == closedAccountFilter }) {
                closedAccountFilter = next.isEmpty ? (vm.state.accounts.first?.id ?? "") : next
            }
        }
        .onChange(of: vm.state.accounts.count) { _ in
            guard closedAccountFilter != "ALL" else { return }
            if closedAccountFilter.isEmpty || !vm.state.accounts.contains(where: { $0.id == closedAccountFilter }) {
                closedAccountFilter = vm.state.selectedAccountId.isEmpty
                    ? (vm.state.accounts.first?.id ?? "")
                    : vm.state.selectedAccountId
            }
        }
    }
}

struct OrderActivityTimeline: View {	
    @EnvironmentObject private var vm: AppViewModel
    let orderId: String
    @State private var events: [OrderEventRow] = []
    @State private var loading = true
    @State private var error = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Divider()
            Text("Trade Activity").font(.caption2.weight(.bold)).foregroundStyle(AppColors.textSecondary)
            if loading {
                Text("Loading activity...").font(.caption).foregroundStyle(AppColors.textSecondary)
            } else if !error.isEmpty {
                Text(error).font(.caption).foregroundStyle(AppColors.danger)
            } else if events.isEmpty {
                Text("No saved activity yet.").font(.caption).foregroundStyle(AppColors.textSecondary)
            } else {
                ForEach(events) { event in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(humanizeEventType(event.eventType)).font(.footnote.weight(.semibold))
                            Spacer()
                            Text(event.eventTsIst.isEmpty ? "-" : event.eventTsIst).font(.caption2).foregroundStyle(AppColors.textSecondary)
                        }
                        Text(event.message).font(.caption).foregroundStyle(AppColors.textSecondary)
                        if let prices = orderEventPriceContext(event) {
                            Text("Prices: \(prices)")
                                .font(.caption.weight(.medium))
                                .foregroundStyle(AppColors.textMuted)
                        }
                        if let failureReason = orderEventFailureReason(event) {
                            Text("Failure: \(failureReason)")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(AppColors.danger)
                        }
                        if !event.status.isEmpty {
                            Text("Status: \(plainStatus(event.status))").font(.caption2).foregroundStyle(AppColors.textMuted)
                        }
                    }
                    .padding(10)
                    .overlay(RoundedRectangle(cornerRadius: 10).stroke(AppColors.border))
                }
            }
        }
        .task(id: orderId) {
            loading = true
            error = ""
            do {
                events = try await vm.fetchOrderEvents(orderId: orderId)
            } catch let loadError {
                events = []
                error = loadError.localizedDescription
            }
            loading = false
        }
    }
}

struct StrategiesScreen: View {
    @EnvironmentObject private var vm: AppViewModel

    var body: some View {
        VStack(spacing: 12) {
            if vm.state.strategySection == nil {
                ScreenHeader(title: "Strategies", subtitle: "FSM engines, Trend Pilot, and trade planner")
                StrategyTile(title: "FSM Engines", subtitle: "Trap reversal automation", active: false) {
                    vm.openStrategy(.trapReversal)
                }
                StrategyTile(title: "Trend Pilot", subtitle: "H4 breakout engine", active: false) {
                    vm.openStrategy(.trendPilot)
                }
                StrategyTile(title: "Trade Planner", subtitle: "\(vm.state.plans.filter { $0.status == "RUNNING" }.count) running plans", active: false) {
                    vm.openStrategy(.planner)
                }
            } else {
                HStack {
                    Button("← Back") { vm.closeStrategy() }.foregroundStyle(AppColors.accent)
                    Text(strategyTitle).appHeadline()
                }
                switch vm.state.strategySection! {
                case .trapReversal: TrapReversalScreen()
                case .trendPilot: TrendPilotScreen()
                case .planner: PlannerScreen()
                }
            }
        }
    }

    private var strategyTitle: String {
        switch vm.state.strategySection {
        case .trapReversal: return "FSM Engines"
        case .trendPilot: return "Trend Pilot"
        case .planner: return "Trade Planner"
        case .none: return ""
        }
    }
}

struct StrategyTile: View {
    let title: String
    let subtitle: String
    let active: Bool
    let action: () -> Void

    var body: some View {
        DataCard {
            Button(action: action) {
                HStack {
                    VStack(alignment: .leading) {
                        Text(title)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(AppColors.textPrimary)
                        Text(subtitle).font(.caption).foregroundStyle(AppColors.textSecondary)
                    }
                    Spacer()
                    if active { StatusPill(label: "RUNNING", positive: true) }
                    else { Text("›").font(.title2).foregroundStyle(AppColors.textMuted) }
                }
            }
            .buttonStyle(.plain)
        }
    }
}

struct PlannerScreen: View {
    @EnvironmentObject private var vm: AppViewModel

    var body: some View {
        VStack(spacing: 12) {
            Text("Monitor and control saved plans. Create detailed plans on web.").font(.caption).foregroundStyle(AppColors.textSecondary)
            if vm.state.plans.isEmpty {
                EmptyText(text: "No trade plans found.")
            }
            ForEach(vm.state.plans) { plan in
                DataCard {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(plan.symbol).appHeadline()
                            Spacer()
                            StatusPill(label: plan.status, positive: plan.status == "RUNNING")
                        }
                        Text("Runtime \(plan.runtime)  Entry \(formatPrice(plan.entry, symbol: plan.symbol, priceDigits: vm.state.priceDigits, relatedValues: [plan.stopLoss]))  SL \(formatPrice(plan.stopLoss, symbol: plan.symbol, priceDigits: vm.state.priceDigits, relatedValues: [plan.entry]))")
                            .font(.caption).foregroundStyle(AppColors.textSecondary)
                        HStack(spacing: 8) {
                            SecondaryButton(title: plan.status == "RUNNING" ? "Deactivate" : "Run", compact: true) {
                                vm.togglePlan(plan, running: plan.status != "RUNNING")
                            }
                            SecondaryButton(title: "Delete", compact: true) { vm.deletePlan(plan.id) }
                            Spacer(minLength: 0)
                        }
                    }
                }
            }
        }
    }
}

struct GoldScreen: View {
    @EnvironmentObject private var vm: AppViewModel
    @State private var activeTab = "Active"

    var body: some View {
        if let gold = vm.state.goldStrategy {
            goldContent(gold)
        } else {
            EmptyText(text: "GOLD strategy data is not available yet.")
        }
    }

    @ViewBuilder
    private func goldContent(_ gold: GoldStrategyState) -> some View {
        let activeStatuses = Set(["WAITING_BREAK", "ARMED", "ORDER_OPEN"])
        let activeRuns = gold.running.filter { activeStatuses.contains($0.status.uppercased()) }
        let inactiveRuns = gold.running.filter { !activeStatuses.contains($0.status.uppercased()) } + gold.history
        let displayed = activeTab == "Active" ? activeRuns : inactiveRuns
        let livePrice = vm.state.prices[gold.config.symbol.uppercased()]

        VStack(spacing: 12) {
            DataCard {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        VStack(alignment: .leading) {
                            Text(gold.config.symbol)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(AppColors.textPrimary)
                            Text(gold.config.triggerSource == "user_selected"
                                 ? "User trigger \(formatPrice(gold.config.userTriggerPrice, symbol: gold.config.symbol, priceDigits: vm.state.priceDigits))"
                                 : "PDH \(formatPrice(gold.config.pdHigh, symbol: gold.config.symbol, priceDigits: vm.state.priceDigits)) · PDL \(formatPrice(gold.config.pdLow, symbol: gold.config.symbol, priceDigits: vm.state.priceDigits))")
                                .font(.caption).foregroundStyle(AppColors.textSecondary)
                        }
                        Spacer()
                        StatusPill(label: gold.config.running ? "RUNNING" : "STOPPED", positive: gold.config.running)
                    }
                    Text("Live \(formatPrice(livePrice, symbol: gold.config.symbol, priceDigits: vm.state.priceDigits))").font(.caption).foregroundStyle(AppColors.textSecondary)
                    if gold.config.running {
                        SecondaryButton(title: "Stop GOLD strategy", danger: true, compact: true) { vm.stopGoldStrategy() }
                    } else {
                        Text("Start and full configuration stay on web.").font(.caption).foregroundStyle(AppColors.textSecondary)
                    }
                }
            }
            ChipRow(values: ["Active", "History"], selected: activeTab) { activeTab = $0 }
            if displayed.isEmpty {
                EmptyText(text: "No \(activeTab.lowercased()) GOLD strategy runs found.")
            }
            ForEach(displayed) { run in
                DataCard {
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text(run.symbol)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(AppColors.textPrimary)
                            Spacer()
                            StatusPill(label: run.status, positive: activeStatuses.contains(run.status.uppercased()))
                        }
                        Text("Running \(formatMoney(run.runningPl)) · Booked \(formatMoney(run.bookedPl)) · Qty \(formatQty(run.quantity))")
                            .font(.caption).foregroundStyle(AppColors.textSecondary)
                    }
                }
            }
        }
    }
}

struct ContinuationFailureScreen: View {
    @EnvironmentObject private var vm: AppViewModel
    @State private var activeTab = "Running"
    @State private var showCreateSheet = false

    var body: some View {
        if let cf = vm.state.continuationFailure {
            cfContent(cf)
        } else {
            EmptyText(text: "Continuation Failure data is not available yet.")
        }
    }

    @ViewBuilder
    private func cfContent(_ cf: ContinuationFailureState) -> some View {
        let activeStatuses = continuationFailureActiveStatuses()
        let runningRuns = cf.running.filter { activeStatuses.contains($0.status.uppercased()) }
        let displayed = activeTab == "Running" ? runningRuns : cf.history

        VStack(spacing: 12) {
            HStack {
                ChipRow(values: ["Running", "History"], selected: activeTab) { activeTab = $0 }
                Spacer()
                PrimaryButton(title: "Create", fullWidth: false, compact: true) { showCreateSheet = true }
            }
            if displayed.isEmpty {
                EmptyText(text: "No \(activeTab.lowercased()) Continuation Failure runs found.")
            }
            ForEach(displayed) { run in
                DataCard {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(alignment: .top) {
                            VStack(alignment: .leading) {
                                Text(run.symbol).font(.subheadline.weight(.semibold)).foregroundStyle(AppColors.textPrimary)
                                Text("\(run.direction) · Pivot \(formatPrice(run.pivotPrice, symbol: run.symbol, priceDigits: vm.state.priceDigits))")
                                    .font(.caption).foregroundStyle(AppColors.textSecondary)
                            }
                            Spacer()
                            VStack(alignment: .trailing) {
                                Text("Running \(formatMoney(run.runningPl))").font(.caption).foregroundStyle(AppColors.textSecondary)
                                Text("Booked \(formatMoney(run.bookedPl))").font(.caption).foregroundStyle(AppColors.textSecondary)
                            }
                        }
                        if activeTab == "Running" {
                            SecondaryButton(title: "Stop", danger: true, compact: true) {
                                vm.stopContinuationFailure(symbol: run.symbol)
                            }
                        }
                        if !run.events.isEmpty {
                            Divider()
                            Text("Events").font(.caption2.weight(.bold)).foregroundStyle(AppColors.textMuted)
                            ForEach(run.events) { event in
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(event.createdAtIst.isEmpty ? event.createdAt : event.createdAtIst)
                                        .font(.caption2).foregroundStyle(AppColors.textMuted)
                                    Text(event.message).font(.caption).foregroundStyle(AppColors.textSecondary)
                                }
                                .padding(10)
                                .overlay(RoundedRectangle(cornerRadius: 10).stroke(AppColors.border))
                            }
                        }
                    }
                }
            }
        }
        .sheet(isPresented: $showCreateSheet) {
            ContinuationFailureCreateSheet(snapshot: cf, onStarted: {
                showCreateSheet = false
                activeTab = "Running"
            })
        }
    }
}

struct ContinuationFailureCreateSheet: View {
    @EnvironmentObject private var vm: AppViewModel
    @Environment(\.dismiss) private var dismiss
    let snapshot: ContinuationFailureState
    let onStarted: () -> Void

    @State private var symbolSearch = ""
    @State private var selectedSymbol = ""
    @State private var suggestions: [String] = []
    @State private var pivotPrice = ""
    @State private var selectedIds: [String] = []
    @State private var riskInputs: [String: String] = [:]
    @State private var exitTargets: [(String, String)] = [("", "")]
    @State private var displaySymbol = ""
    @State private var suggestTask: Task<Void, Never>?

    private var resolvedSymbol: String { selectedSymbol.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() }
    private var livePrice: Double? { vm.state.prices[resolvedSymbol] }
    private var inferredDirection: String? {
        guard let pivot = Double(pivotPrice), pivot > 0, let price = livePrice else { return nil }
        if pivot > price { return "SHORT" }
        if pivot < price { return "LONG" }
        return "invalid"
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    TextField("Search instrument", text: $symbolSearch)
                        .textInputAutocapitalization(.characters)
                        .onChange(of: symbolSearch) { value in
                            symbolSearch = value.uppercased()
                            suggestTask?.cancel()
                            suggestTask = Task {
                                try? await Task.sleep(nanoseconds: 180_000_000)
                                guard !Task.isCancelled else { return }
                                if value.trimmingCharacters(in: .whitespacesAndNewlines).count < 1 {
                                    suggestions = []
                                    return
                                }
                                suggestions = (try? await vm.suggestInstruments(query: value)) ?? []
                            }
                        }
                    if !suggestions.isEmpty, !symbolSearch.isEmpty {
                        ForEach(suggestions, id: \.self) { suggestion in
                            Button(suggestion) { selectSymbol(suggestion) }
                                .foregroundStyle(AppColors.textPrimary)
                        }
                    }
                    if !resolvedSymbol.isEmpty {
                        Text(displaySymbol.isEmpty ? resolvedSymbol : displaySymbol)
                            .font(.title2.weight(.bold))
                        Text("Live \(formatPrice(livePrice, symbol: resolvedSymbol, priceDigits: vm.state.priceDigits))")
                            .font(.caption).foregroundStyle(AppColors.textSecondary)
                    }
                    TextField("Pivot price", text: $pivotPrice)
                        .keyboardType(.decimalPad)
                    if inferredDirection == "SHORT" || inferredDirection == "LONG" {
                        Text(inferredDirection!).font(.caption.weight(.semibold))
                    }
                    if inferredDirection == "invalid" {
                        Text("Pivot cannot equal market price").font(.caption).foregroundStyle(AppColors.danger)
                    }
                    Text("Accounts").font(.caption2.weight(.bold)).foregroundStyle(AppColors.textMuted)
                    ForEach(vm.state.accounts) { account in
                        let checked = selectedIds.contains(account.id)
                        let disabled = isCfAccountDisabled(account, selectedIds: selectedIds, accounts: vm.state.accounts, activeAccountId: vm.state.selectedAccountId)
                        HStack {
                            Toggle(isOn: Binding(
                                get: { checked },
                                set: { next in
                                    var updated = selectedIds
                                    if next { updated.append(account.id) } else { updated.removeAll { $0 == account.id } }
                                    selectedIds = normalizeCfSelection(updated, accounts: vm.state.accounts, activeAccountId: vm.state.selectedAccountId)
                                }
                            )) {
                                VStack(alignment: .leading) {
                                    Text(account.name)
                                    if account.id == vm.state.selectedAccountId {
                                        Text("Feed").font(.caption2.weight(.bold)).foregroundStyle(AppColors.accent)
                                    }
                                }
                            }
                            .disabled(disabled && !checked)
                            TextField("Risk", text: Binding(
                                get: { riskInputs[account.id] ?? String(account.risk) },
                                set: { riskInputs[account.id] = $0 }
                            ))
                            .keyboardType(.decimalPad)
                            .frame(width: 90)
                            .disabled(!checked)
                        }
                    }
                    Text("Exit targets").font(.caption2.weight(.bold)).foregroundStyle(AppColors.textMuted)
                    ForEach(Array(exitTargets.enumerated()), id: \.offset) { index, target in
                        HStack {
                            TextField("Price", text: Binding(
                                get: { exitTargets[index].0 },
                                set: { exitTargets[index].0 = $0 }
                            ))
                            .keyboardType(.decimalPad)
                            TextField("Qty", text: Binding(
                                get: { exitTargets[index].1 },
                                set: { exitTargets[index].1 = $0 }
                            ))
                            .keyboardType(.decimalPad)
                            .frame(width: 90)
                            if exitTargets.count > 1 {
                                Button("Remove") { exitTargets.remove(at: index) }
                                    .font(.caption).foregroundStyle(AppColors.danger)
                            }
                        }
                    }
                    SecondaryButton(title: "Add target", compact: true) {
                        exitTargets.append(("", ""))
                    }
                    let canStart = !resolvedSymbol.isEmpty && !pivotPrice.isEmpty && livePrice != nil && inferredDirection != nil && inferredDirection != "invalid"
                    PrimaryButton(title: "Start", compact: false) {
                        let targets = selectedIds.compactMap { accountId -> (String, Double)? in
                            guard let account = vm.state.accounts.first(where: { $0.id == accountId }) else { return nil }
                            let risk = Double(riskInputs[accountId] ?? "") ?? account.risk
                            return (accountId, risk)
                        }
                        let exits = exitTargets.compactMap { row -> (Double, Double?)? in
                            guard let price = Double(row.0) else { return nil }
                            let qty = row.1.isEmpty ? nil : Double(row.1)
                            return (price, qty)
                        }
                        vm.startContinuationFailure(
                            symbol: resolvedSymbol,
                            pivotPrice: Double(pivotPrice) ?? 0,
                            startReferencePrice: livePrice ?? 0,
                            targets: targets,
                            exitTargets: exits
                        )
                        onStarted()
                        dismiss()
                    }
                    .disabled(!canStart)
                }
                .padding()
            }
            .navigationTitle("Create strategy")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
            .onAppear {
                selectedIds = normalizeCfSelection(
                    vm.state.selectedAccountId.isEmpty ? [] : [vm.state.selectedAccountId],
                    accounts: vm.state.accounts,
                    activeAccountId: vm.state.selectedAccountId
                )
            }
        }
    }

    private func selectSymbol(_ symbol: String) {
        let normalized = symbol.uppercased()
        selectedSymbol = normalized
        symbolSearch = normalized
        suggestions = []
        if let config = snapshot.symbols.first(where: { $0.symbol.uppercased() == normalized }) {
            pivotPrice = config.pivotPrice.map { String($0) } ?? ""
        } else {
            pivotPrice = ""
        }
        Task {
            if let info = try? await vm.resolveContinuationFailureSymbol(normalized) {
                displaySymbol = info["display_symbol"] as? String ?? normalized
            }
        }
    }
}
