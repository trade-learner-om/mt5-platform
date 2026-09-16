import SwiftUI

private let trendPilotBufferUsd = 10.0

struct TrapReversalScreen: View {
    @EnvironmentObject private var vm: AppViewModel
    @State private var symbol = "GOLD"
    @State private var riskAmount = "100"
    @State private var levels: TrapReversalLevels?
    @State private var runs: [TrapReversalRunRow] = []
    @State private var actionBusy = false
    @State private var error = ""

    private var normalized: String { symbol.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() }
    private var symbolRunning: Bool {
        runs.contains { $0.symbol.uppercased() == normalized || $0.displaySymbol.uppercased() == normalized }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("H1 support/resistance trap engine with live FSM monitoring.")
                    .font(.subheadline)
                    .foregroundStyle(AppColors.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)

                DataCard {
                    VStack(spacing: 10) {
                        TextField("Symbol", text: $symbol)
                            .textInputAutocapitalization(.characters)
                            .padding(12)
                            .background(AppColors.surfaceMuted)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                            .overlay(RoundedRectangle(cornerRadius: 12).stroke(AppColors.border))
                        TextField("Risk amount", text: $riskAmount)
                            .keyboardType(.decimalPad)
                            .padding(12)
                            .background(AppColors.surfaceMuted)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                            .overlay(RoundedRectangle(cornerRadius: 12).stroke(AppColors.border))
                        HStack(spacing: 8) {
                            if !symbolRunning {
                                PrimaryButton(title: actionBusy ? "Starting..." : "Start engine", fullWidth: true) {
                                    Task { await startEngine() }
                                }
                                .disabled(actionBusy)
                            }
                            if symbolRunning {
                                SecondaryButton(title: actionBusy ? "Stopping..." : "Stop engine", danger: true) {
                                    Task { await stopEngine() }
                                }
                                .disabled(actionBusy)
                            }
                        }
                    }
                }

                if !error.isEmpty {
                    Text(error).font(.caption.weight(.semibold)).foregroundStyle(AppColors.danger)
                }

                if let levels {
                    DataCard {
                        VStack(alignment: .leading, spacing: 10) {
                            HStack {
                                Text("H1 Levels").appHeadline()
                                Spacer()
                                Text(levels.displaySymbol.isEmpty ? levels.symbol : levels.displaySymbol)
                                    .font(.caption)
                                    .foregroundStyle(AppColors.textMuted)
                            }
                            HStack(alignment: .top, spacing: 10) {
                                levelColumn(title: "Supports", prices: levels.supports, tone: AppColors.success, background: AppColors.successSoft, digits: levels.priceDigits)
                                levelColumn(title: "Resistances", prices: levels.resistances, tone: AppColors.danger, background: AppColors.dangerSoft, digits: levels.priceDigits)
                            }
                        }
                    }
                }

                DataCard {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Active engines").appHeadline()
                        if runs.isEmpty {
                            Text("No active trap reversal engines.").font(.caption).foregroundStyle(AppColors.textMuted)
                        } else {
                            ForEach(runs) { run in
                                HStack {
                                    VStack(alignment: .leading) {
                                        Text(run.displaySymbol.isEmpty ? run.symbol : run.displaySymbol)
                                            .font(.subheadline.weight(.semibold))
                                            .foregroundStyle(AppColors.textPrimary)
                                        Text("Risk \(formatMoney(run.riskAmount))")
                                            .font(.caption)
                                            .foregroundStyle(AppColors.textSecondary)
                                    }
                                    Spacer()
                                    StrategyStatusPill(status: run.state.isEmpty ? "running" : run.state, pulse: true)
                                }
                            }
                        }
                    }
                }
            }
        }
        .task(id: normalized) {
            while !Task.isCancelled {
                await refresh(silent: true)
                try? await Task.sleep(nanoseconds: 3_000_000_000)
            }
        }
    }

    @ViewBuilder
    private func levelColumn(title: String, prices: [Double], tone: Color, background: Color, digits: Int?) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption2.weight(.bold))
                .tracking(0.5)
                .foregroundStyle(tone)
            ForEach(Array(prices.enumerated()), id: \.offset) { _, price in
                Text(formatPilotPrice(price, digits: digits))
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(tone)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 6)
                    .background(background)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(tone.opacity(0.25)))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func refresh(silent: Bool) async {
        do {
            runs = try await vm.fetchTrapReversalActive()
            levels = try await vm.fetchTrapReversalLevels(symbol: normalized)
            error = ""
        } catch {
            if !silent { self.error = error.localizedDescription }
        }
    }

    private func startEngine() async {
        actionBusy = true
        defer { actionBusy = false }
        do {
            try await vm.startTrapReversal(symbol: normalized, riskAmount: Double(riskAmount) ?? 0)
            await refresh(silent: true)
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func stopEngine() async {
        actionBusy = true
        defer { actionBusy = false }
        do {
            try await vm.stopTrapReversal(symbol: normalized)
            await refresh(silent: true)
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct TrendPilotScreen: View {
    @EnvironmentObject private var vm: AppViewModel
    @State private var mode = "Live"
    @State private var symbol = "XAUUSD"
    @State private var quantity = "0.01"
    @State private var fromDate = Calendar.current.date(byAdding: .day, value: -7, to: Date()) ?? Date()
    @State private var toDate = Date()
    @State private var activeRuns: [TrendPilotRunRow] = []
    @State private var historyRuns: [TrendPilotHistoryRow] = []
    @State private var backtests: [TrendPilotBacktestRow] = []
    @State private var backtestPage = 1
    @State private var backtestPageSize = 10
    @State private var backtestTotalCount = 0
    @State private var backtestTotalPages = 1
    @State private var backtestPageCursors: [Int: String?] = [:]
    @State private var backtestsLoading = false
    @State private var selectedAccountIds: [String] = []
    @State private var selectionInitialized = false
    @State private var expandedRunId = ""
    @State private var expandedBacktestId = ""
    @State private var expandedRolls: [TrendPilotRollRow] = []
    @State private var expandedSummary: [String: Any]?
    @State private var actionBusy = false
    @State private var error = ""
    @State private var settingsOpen = false
    @State private var backtestFormOpen = false
    @State private var partialAtPct = "0"
    @State private var partialQtyPct = "0"
    @State private var moveSlToBreakeven = false
    @State private var settingsSaving = false

    private var accounts: [AccountRow] { internationalAccounts(vm.state.accounts) }
    private var runningByAccount: [String: TrendPilotRunRow] {
        Dictionary(uniqueKeysWithValues: activeRuns.filter { trendPilotRunMatchesSymbol($0, symbol: symbol) }.map { ($0.accountId, $0) })
    }
    private var startableIds: [String] { selectedAccountIds.filter { runningByAccount[$0] == nil } }
    private var stoppableIds: [String] { selectedAccountIds.filter { runningByAccount[$0] != nil } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("H4 breakout engine with always-in reversal stops and optional funded loss cap.")
                    .font(.subheadline)
                    .foregroundStyle(AppColors.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)

                ChipRow(values: ["Live", "Backtest"], selected: mode) { mode = $0 }

                if mode == "Live" {
                    DataCard {
                        VStack(spacing: 10) {
                            pilotField("Symbol", text: $symbol)
                            pilotField("Quantity", text: $quantity)
                            HStack(spacing: 8) {
                                if !startableIds.isEmpty {
                                    PrimaryButton(title: actionBusy ? "Starting..." : "Start", fullWidth: true) {
                                        Task { await startPilot() }
                                    }
                                    .disabled(actionBusy)
                                }
                                if !stoppableIds.isEmpty {
                                    SecondaryButton(title: actionBusy ? "Stopping..." : "Stop", danger: true) {
                                        Task { await stopPilot() }
                                    }
                                    .disabled(actionBusy)
                                }
                            }
                        }
                    }

                    accountPicker
                    activeRunsSection
                    historySection
                } else {
                    backtestSection
                }

                if !error.isEmpty {
                    Text(error).font(.caption.weight(.semibold)).foregroundStyle(AppColors.danger)
                }
            }
        }
        .onAppear { syncAccountSelection() }
        .onChange(of: vm.state.accounts) { _, _ in syncAccountSelection() }
        .onChange(of: mode) { _, newMode in
            if newMode != "Backtest" {
                backtestFormOpen = false
            }
        }
        .task(id: mode) {
            if mode == "Live" {
                while !Task.isCancelled {
                    await refreshLive(silent: true)
                    try? await Task.sleep(nanoseconds: 3_000_000_000)
                }
            } else {
                await loadBacktestSettings()
                await refreshBacktests()
            }
        }
        .task(id: expandedRunId) { await loadRunDetail() }
        .task(id: expandedBacktestId) { await loadBacktestDetail() }
        .sheet(isPresented: $settingsOpen) {
            NavigationStack {
                Form {
                    Section("Partial booking") {
                        pilotField("Book partial at (% price move)", text: $partialAtPct)
                        pilotField("Partial quantity (%)", text: $partialQtyPct)
                        Toggle("Move SL to breakeven after partial", isOn: $moveSlToBreakeven)
                    }
                }
                .navigationTitle("Backtest settings")
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Cancel") { settingsOpen = false }
                    }
                    ToolbarItem(placement: .confirmationAction) {
                        Button(settingsSaving ? "Saving..." : "Save") {
                            Task { await saveBacktestSettings() }
                        }
                        .disabled(settingsSaving)
                    }
                }
            }
        }
    }

    private var accountPicker: some View {
        DataCard {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("Accounts").appHeadline()
                    Spacer()
                    Button("All") { selectedAccountIds = accounts.map(\.id) }
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(AppColors.accent)
                    Button("Clear") { selectedAccountIds = [] }
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(AppColors.accent)
                }
                ForEach(accounts) { account in
                    let checked = selectedAccountIds.contains(account.id)
                    let activeRun = runningByAccount[account.id]
                    Button {
                        toggleAccount(account.id)
                    } label: {
                        HStack {
                            Image(systemName: checked ? "checkmark.square.fill" : "square")
                                .foregroundStyle(checked ? AppColors.accent : AppColors.textMuted)
                            VStack(alignment: .leading) {
                                Text(account.name).font(.subheadline.weight(.semibold)).foregroundStyle(AppColors.textPrimary)
                                if account.id == vm.state.selectedAccountId {
                                    Text("Selected in terminal")
                                        .font(.system(size: 10, weight: .bold))
                                        .foregroundStyle(AppColors.success)
                                }
                            }
                            Spacer()
                            if let activeRun {
                                StrategyStatusPill(status: trendPilotRunStatusKey(activeRun), pulse: true)
                            }
                        }
                        .padding(10)
                        .background(checked ? AppColors.accentSoft : AppColors.surfaceMuted)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(checked ? AppColors.accent.opacity(0.35) : AppColors.border))
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private var activeRunsSection: some View {
        DataCard {
            VStack(alignment: .leading, spacing: 10) {
                Text("Active runs").appHeadline()
                if activeRuns.isEmpty {
                    Text("No active Trend Pilot runs.").font(.caption).foregroundStyle(AppColors.textMuted)
                } else {
                    ForEach(activeRuns) { run in
                        VStack(alignment: .leading, spacing: 6) {
                            HStack(spacing: 6) {
                                Text(run.displaySymbol.isEmpty ? run.symbol : run.displaySymbol)
                                    .font(.subheadline.weight(.semibold))
                                Text(run.accountName.isEmpty ? run.accountId : run.accountName)
                                    .font(.caption)
                                    .foregroundStyle(AppColors.textSecondary)
                                StrategyStatusPill(status: trendPilotRunStatusKey(run), pulse: true)
                                if !run.currentSide.isEmpty {
                                    StrategyStatusPill(status: run.currentSide.lowercased())
                                }
                            }
                            HStack(spacing: 4) {
                                Text("Rolls \(run.rollCount) ·")
                                    .font(.caption)
                                    .foregroundStyle(AppColors.textSecondary)
                                Text("Qty \(formatQty(run.quantity)) ·")
                                    .font(.caption)
                                    .foregroundStyle(AppColors.textSecondary)
                                Text("P/L \(formatMoney(run.cumulativePnl))")
                                    .font(.subheadline.weight(.bold))
                                    .foregroundStyle(pnlForegroundColor(run.cumulativePnl))
                            }
                            if let high = run.windowHigh, let low = run.windowLow {
                                Text("Window \(formatPilotPrice(high)) / \(formatPilotPrice(low))")
                                    .font(.system(.caption2, design: .monospaced))
                                    .foregroundStyle(AppColors.textMuted)
                                Text("Long \(formatPilotPrice(high + trendPilotBufferUsd)) · Short \(formatPilotPrice(low - trendPilotBufferUsd))")
                                    .font(.caption2)
                                    .foregroundStyle(AppColors.textMuted)
                            }
                            if !run.lastError.isEmpty {
                                Text(run.lastError).font(.caption).foregroundStyle(AppColors.danger)
                            }
                        }
                        .padding(10)
                        .background(AppColors.surfaceMuted)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                }
            }
        }
    }

    private var historySection: some View {
        DataCard {
            VStack(alignment: .leading, spacing: 8) {
                Text("Run history").appHeadline()
                if historyRuns.isEmpty {
                    EmptyText(text: "No run history yet.")
                }
                ForEach(historyRuns) { run in
                    let expanded = expandedRunId == run.runId
                    Button {
                        expandedRunId = expanded ? "" : run.runId
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack(spacing: 6) {
                                Text(run.displaySymbol.isEmpty ? run.symbol : run.displaySymbol)
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(AppColors.textPrimary)
                                if !run.accountName.isEmpty {
                                    Text(run.accountName).font(.caption).foregroundStyle(AppColors.textSecondary)
                                }
                                StrategyStatusPill(status: run.status.lowercased() == "stopped" ? "stopped" : "running")
                            }
                            Text("\(run.closedTrades ?? 0) trades · \(run.rollCount) rolls")
                                .font(.caption)
                                .foregroundStyle(AppColors.textMuted)
                            Text("P/L \(formatMoney(run.totalPnl ?? 0))")
                                .font(.headline.weight(.bold))
                                .foregroundStyle(pnlForegroundColor(run.totalPnl ?? 0))
                            if expanded {
                                if let summary = expandedSummary {
                                    Text("Max DD \(formatMoney(summary["max_drawdown"] as? Double ?? 0))")
                                        .font(.caption)
                                        .foregroundStyle(AppColors.textSecondary)
                                }
                                ForEach(expandedRolls.prefix(8)) { roll in
                                    Text("\(roll.eventType) \(roll.fromSide)→\(roll.toSide) \(formatMoney(roll.pnlUpdate))")
                                        .font(.caption2)
                                        .foregroundStyle(AppColors.textMuted)
                                }
                            }
                        }
                        .padding(10)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(AppColors.border))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private var backtestSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            if backtestFormOpen {
                backtestFormCard
            }

            DataCard {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text("Backtest results").appHeadline()
                        Spacer()
                        if !backtestFormOpen {
                            SecondaryButton(title: "Run backtest", compact: true) {
                                backtestFormOpen = true
                            }
                        }
                    }
                if backtestsLoading && backtests.isEmpty {
                    Text("Loading backtest history...")
                        .font(.caption)
                        .foregroundStyle(AppColors.textSecondary)
                } else if backtests.isEmpty {
                    EmptyText(text: "No backtest results yet.")
                } else {
                    ScrollView {
                        VStack(spacing: 8) {
                            ForEach(backtests) { result in
                                let expanded = expandedBacktestId == result.resultId
                                VStack(alignment: .leading, spacing: 6) {
                                    Text("\(result.displaySymbol.isEmpty ? result.symbol : result.displaySymbol) · \(result.fromDate) – \(result.toDate)")
                                        .font(.subheadline.weight(.semibold))
                                        .foregroundStyle(AppColors.textPrimary)
                                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                                        Text("P/L \(formatMoney(result.totalPnl ?? 0))")
                                            .font(.headline.weight(.bold))
                                            .foregroundStyle(pnlForegroundColor(result.totalPnl ?? 0))
                                        Text("· \(result.closedTrades ?? 0) trades")
                                            .font(.caption)
                                            .foregroundStyle(AppColors.textSecondary)
                                        Text("· Qty \(formatQty(result.quantity))")
                                            .font(.caption)
                                            .foregroundStyle(AppColors.textSecondary)
                                    }
                                    HStack {
                                        SecondaryButton(title: expanded ? "Hide" : "Details", compact: true) {
                                            expandedBacktestId = expanded ? "" : result.resultId
                                        }
                                        SecondaryButton(title: "Delete", danger: true, compact: true) {
                                            Task {
                                                try? await vm.deleteTrendPilotBacktest(resultId: result.resultId)
                                                if expandedBacktestId == result.resultId { expandedBacktestId = "" }
                                                await loadBacktestPage(page: backtestPage, resetCursors: true)
                                            }
                                        }
                                    }
                                    if expanded {
                                        ForEach(expandedRolls.prefix(8)) { roll in
                                            Text("\(roll.eventType) \(formatMoney(roll.pnlUpdate))")
                                                .font(.caption2)
                                                .foregroundStyle(AppColors.textMuted)
                                        }
                                    }
                                }
                                .padding(10)
                                .overlay(RoundedRectangle(cornerRadius: 12).stroke(AppColors.border))
                            }
                        }
                    }
                    .frame(maxHeight: 360)
                }
                BacktestResultsPaginationView(
                    page: backtestPage,
                    pageSize: backtestPageSize,
                    totalCount: backtestTotalCount,
                    totalPages: backtestTotalPages,
                    disabled: backtestsLoading
                ) { page in
                    Task { await loadBacktestPage(page: page) }
                } onPageSizeChange: { pageSize in
                    backtestPageSize = pageSize
                    Task { await loadBacktestPage(page: 1, resetCursors: true) }
                }
                }
            }
        }
    }

    private var backtestFormCard: some View {
        DataCard {
            VStack(spacing: 10) {
                HStack {
                    Text("New backtest").appHeadline()
                    Spacer()
                    Button("Close") {
                        backtestFormOpen = false
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AppColors.accent)
                }
                pilotField("Symbol", text: $symbol)
                pilotField("Quantity", text: $quantity)
                pilotDateField("From", selection: $fromDate)
                pilotDateField("To", selection: $toDate)
                HStack(spacing: 8) {
                    SecondaryButton(title: "Settings") { settingsOpen = true }
                    SecondaryButton(title: "Cancel") { backtestFormOpen = false }
                    PrimaryButton(title: actionBusy ? "Running..." : "Run backtest", fullWidth: true) {
                        Task { await runBacktest() }
                    }
                    .disabled(actionBusy)
                }
            }
        }
    }

    private func pilotField(_ label: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.caption.weight(.semibold)).foregroundStyle(AppColors.textMuted)
            TextField(label, text: text)
                .textInputAutocapitalization(label == "Symbol" ? .characters : .never)
                .padding(12)
                .background(AppColors.surfaceMuted)
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(AppColors.border))
        }
    }

    private func pilotDateField(_ label: String, selection: Binding<Date>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.caption.weight(.semibold)).foregroundStyle(AppColors.textMuted)
            DatePicker("", selection: selection, displayedComponents: .date)
                .datePickerStyle(.compact)
                .labelsHidden()
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(12)
                .background(AppColors.surfaceMuted)
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(AppColors.border))
        }
    }

    private func syncAccountSelection() {
        guard !accounts.isEmpty else {
            selectedAccountIds = []
            selectionInitialized = false
            return
        }
        if !selectionInitialized {
            let defaultId = accounts.first(where: { $0.id == vm.state.selectedAccountId })?.id ?? accounts[0].id
            selectedAccountIds = [defaultId]
            selectionInitialized = true
        } else {
            selectedAccountIds = selectedAccountIds.filter { id in accounts.contains { $0.id == id } }
        }
    }

    private func toggleAccount(_ id: String) {
        if let index = selectedAccountIds.firstIndex(of: id) {
            selectedAccountIds.remove(at: index)
        } else {
            selectedAccountIds.append(id)
        }
    }

    private func refreshLive(silent: Bool) async {
        do {
            activeRuns = try await vm.fetchTrendPilotActive()
            historyRuns = try await vm.fetchTrendPilotHistoryList()
            error = ""
        } catch {
            if !silent { self.error = error.localizedDescription }
        }
    }

    private func refreshBacktests() async {
        await loadBacktestPage(page: 1, resetCursors: true)
    }

    private func loadBacktestPage(page: Int? = nil, resetCursors: Bool = false) async {
        if resetCursors {
            backtestPageCursors = [:]
        }
        let targetPage = page ?? backtestPage
        if let page {
            backtestPage = page
        }
        backtestsLoading = true
        defer { backtestsLoading = false }
        do {
            var cursors = backtestPageCursors
            let response = try await vm.fetchTrendPilotBacktestsPage(
                targetPage: targetPage,
                pageSize: backtestPageSize,
                cursors: &cursors
            )
            backtestPageCursors = cursors
            backtests = response.results
            backtestTotalCount = response.totalCount
            backtestTotalPages = max(1, response.totalPages)
            if targetPage > backtestTotalPages {
                backtestPage = backtestTotalPages
            } else {
                backtestPage = targetPage
            }
            error = ""
        } catch {
            backtests = []
            self.error = error.localizedDescription
        }
    }

    private func loadBacktestSettings() async {
        do {
            let settings = try await vm.fetchTrendPilotBacktestSettings()
            partialAtPct = String(settings["partial_at_pct"] as? Double ?? 0)
            partialQtyPct = String(settings["partial_qty_pct"] as? Double ?? 0)
            moveSlToBreakeven = settings["move_sl_to_breakeven"] as? Bool ?? false
        } catch {
            if self.error.isEmpty { self.error = error.localizedDescription }
        }
    }

    private func saveBacktestSettings() async {
        settingsSaving = true
        defer { settingsSaving = false }
        do {
            try await vm.saveTrendPilotBacktestSettings(
                partialAtPct: Double(partialAtPct) ?? 0,
                partialQtyPct: Double(partialQtyPct) ?? 0,
                moveSlToBreakeven: moveSlToBreakeven
            )
            settingsOpen = false
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func loadRunDetail() async {
        guard !expandedRunId.isEmpty else {
            expandedRolls = []
            expandedSummary = nil
            return
        }
        do {
            let detail = try await vm.fetchTrendPilotHistoryDetail(runId: expandedRunId)
            expandedRolls = JsonParsers.parseTrendPilotRolls(detail["trade_rolls"] as? [[String: Any]])
            expandedSummary = detail["summary"] as? [String: Any]
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func loadBacktestDetail() async {
        guard !expandedBacktestId.isEmpty else {
            expandedRolls = []
            expandedSummary = nil
            return
        }
        do {
            let detail = try await vm.fetchTrendPilotBacktestDetail(resultId: expandedBacktestId)
            expandedRolls = JsonParsers.parseTrendPilotRolls(detail["rolls"] as? [[String: Any]])
            expandedSummary = detail["summary"] as? [String: Any]
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func startPilot() async {
        actionBusy = true
        defer { actionBusy = false }
        do {
            try await vm.startTrendPilot(symbol: symbol, quantity: Double(quantity) ?? 0.01, accountIds: startableIds)
            await refreshLive(silent: true)
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func stopPilot() async {
        actionBusy = true
        defer { actionBusy = false }
        do {
            try await vm.stopTrendPilot(symbol: symbol, accountIds: stoppableIds)
            await refreshLive(silent: true)
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func runBacktest() async {
        actionBusy = true
        defer { actionBusy = false }
        do {
            try await vm.runTrendPilotBacktest(
                symbol: symbol,
                quantity: Double(quantity) ?? 0.01,
                fromDate: isoDate(fromDate),
                toDate: isoDate(toDate)
            )
            backtestFormOpen = false
            await refreshBacktests()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

private func formatPilotPrice(_ value: Double, digits: Int? = 2) -> String {
    guard value.isFinite else { return "-" }
    return String(format: "%.\(digits ?? 2)f", value)
}

private func isoDate(_ date: Date) -> String {
    let formatter = DateFormatter()
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter.string(from: date)
}
