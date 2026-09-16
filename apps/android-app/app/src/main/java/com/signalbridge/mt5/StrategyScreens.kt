package com.signalbridge.mt5

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate
import java.time.format.DateTimeFormatter

private const val TREND_PILOT_BUFFER_USD = 10.0

data class TrendPilotRunRow(
    val runId: String,
    val accountId: String,
    val accountName: String,
    val symbol: String,
    val displaySymbol: String,
    val state: String,
    val currentSide: String,
    val rollCount: Int,
    val quantity: Double,
    val windowHigh: Double?,
    val windowLow: Double?,
    val cumulativePnl: Double,
    val lossCapEnabled: Boolean,
    val lossCapPct: Double,
    val lastError: String,
)

data class TrendPilotHistoryRow(
    val runId: String,
    val accountId: String,
    val accountName: String,
    val symbol: String,
    val displaySymbol: String,
    val status: String,
    val rollCount: Int,
    val startedAt: String,
    val totalPnl: Double?,
    val closedTrades: Int?,
    val maxDrawdown: Double?,
)

data class TrendPilotBacktestRow(
    val resultId: String,
    val symbol: String,
    val displaySymbol: String,
    val fromDate: String,
    val toDate: String,
    val quantity: Double,
    val totalPnl: Double?,
    val closedTrades: Int?,
    val rollCount: Int,
    val maxDrawdown: Double?,
)

data class TrendPilotBacktestPage(
    val results: List<TrendPilotBacktestRow>,
    val hasNextPage: Boolean,
    val endCursor: String?,
)

data class TrendPilotRollRow(
    val eventType: String,
    val eventTime: String,
    val fromSide: String,
    val toSide: String,
    val pnlUpdate: Double,
    val cumulativePnl: Double,
    val message: String,
)

data class TrapReversalRunRow(
    val symbol: String,
    val displaySymbol: String,
    val state: String,
    val riskAmount: Double,
)

data class TrapReversalLevels(
    val symbol: String,
    val displaySymbol: String,
    val supports: List<Double>,
    val resistances: List<Double>,
    val priceDigits: Int?,
)

fun internationalAccounts(state: AppState): List<AccountRow> =
    state.accounts.filter { (it.marketType ?: "INTERNATIONAL").uppercase() == "INTERNATIONAL" }

fun trendPilotRunMatchesSymbol(run: TrendPilotRunRow, symbolInput: String): Boolean {
    val key = symbolInput.trim().uppercase()
    return listOf(run.symbol, run.displaySymbol).any { it.trim().uppercase() == key }
}

fun trendPilotRunStatusKey(run: TrendPilotRunRow): String {
    return when (run.state.uppercase()) {
        "ARMED" -> "armed"
        "LONG" -> "long"
        "SHORT" -> "short"
        "REVERSING" -> "reversing"
        else -> if (run.lastError.isNotBlank()) "error" else "running"
    }
}

fun parseTrendPilotRuns(array: JSONArray): List<TrendPilotRunRow> = buildList {
    for (index in 0 until array.length()) {
        val item = array.optJSONObject(index) ?: continue
        add(
            TrendPilotRunRow(
                runId = item.optString("run_id"),
                accountId = item.optString("account_id"),
                accountName = item.optString("account_name"),
                symbol = item.optString("requested_symbol", item.optString("symbol")),
                displaySymbol = item.optString("display_symbol", item.optString("symbol")),
                state = item.optString("state"),
                currentSide = item.optString("current_side"),
                rollCount = item.optInt("roll_count"),
                quantity = item.optDouble("quantity", 0.01),
                windowHigh = item.optDouble("window_high").takeIf { !it.isNaN() },
                windowLow = item.optDouble("window_low").takeIf { !it.isNaN() },
                cumulativePnl = item.optDouble("cumulative_pnl"),
                lossCapEnabled = item.optBoolean("funded_loss_cap_enabled"),
                lossCapPct = item.optDouble("loss_cap_exit_pct", 0.95),
                lastError = item.optString("last_error"),
            )
        )
    }
}

fun parseTrendPilotHistoryRows(array: JSONArray): List<TrendPilotHistoryRow> = buildList {
    for (index in 0 until array.length()) {
        val item = array.optJSONObject(index) ?: continue
        add(
            TrendPilotHistoryRow(
                runId = item.optString("run_id"),
                accountId = item.optString("account_id"),
                accountName = item.optString("account_name"),
                symbol = item.optString("symbol"),
                displaySymbol = item.optString("display_symbol", item.optString("symbol")),
                status = item.optString("status"),
                rollCount = item.optInt("roll_count"),
                startedAt = item.optString("started_at"),
                totalPnl = item.optDouble("total_pnl").takeIf { !it.isNaN() },
                closedTrades = item.optInt("closed_trades").takeIf { item.has("closed_trades") },
                maxDrawdown = item.optDouble("max_drawdown").takeIf { !it.isNaN() },
            )
        )
    }
}

fun parseTrendPilotBacktests(array: JSONArray): List<TrendPilotBacktestRow> = buildList {
    for (index in 0 until array.length()) {
        val item = array.optJSONObject(index) ?: continue
        add(
            TrendPilotBacktestRow(
                resultId = item.optString("result_id"),
                symbol = item.optString("symbol"),
                displaySymbol = item.optString("display_symbol", item.optString("symbol")),
                fromDate = item.optString("from_date"),
                toDate = item.optString("to_date"),
                quantity = item.optDouble("quantity", 0.01),
                totalPnl = item.optDouble("total_pnl").takeIf { !it.isNaN() },
                closedTrades = item.optInt("closed_trades").takeIf { item.has("closed_trades") },
                rollCount = item.optInt("roll_count"),
                maxDrawdown = item.optDouble("max_drawdown").takeIf { !it.isNaN() },
            )
        )
    }
}

fun parseTrendPilotRolls(array: JSONArray): List<TrendPilotRollRow> = buildList {
    for (index in 0 until array.length()) {
        val item = array.optJSONObject(index) ?: continue
        add(
            TrendPilotRollRow(
                eventType = item.optString("event_type"),
                eventTime = item.optString("event_time"),
                fromSide = item.optString("from_side"),
                toSide = item.optString("to_side"),
                pnlUpdate = item.optDouble("pnl_update"),
                cumulativePnl = item.optDouble("cumulative_pnl"),
                message = item.optString("message"),
            )
        )
    }
}

fun parseTrapReversalRuns(array: JSONArray): List<TrapReversalRunRow> = buildList {
    for (index in 0 until array.length()) {
        val item = array.optJSONObject(index) ?: continue
        add(
            TrapReversalRunRow(
                symbol = item.optString("symbol"),
                displaySymbol = item.optString("display_symbol", item.optString("symbol")),
                state = item.optString("state"),
                riskAmount = item.optDouble("risk_amount"),
            )
        )
    }
}

fun parseTrapReversalLevels(payload: JSONObject): TrapReversalLevels {
    val supports = payload.optJSONArray("active_h1_supports") ?: payload.optJSONArray("supports") ?: JSONArray()
    val resistances = payload.optJSONArray("active_h1_resistances") ?: payload.optJSONArray("resistances") ?: JSONArray()
    return TrapReversalLevels(
        symbol = payload.optString("symbol"),
        displaySymbol = payload.optString("display_symbol", payload.optString("symbol")),
        supports = buildList { for (i in 0 until supports.length()) add(supports.optDouble(i)) },
        resistances = buildList { for (i in 0 until resistances.length()) add(resistances.optDouble(i)) },
        priceDigits = payload.optInt("price_digits").takeIf { payload.has("price_digits") },
    )
}

@Composable
fun StrategyStatusPill(status: String, pulse: Boolean = false, modifier: Modifier = Modifier) {
    val key = status.trim().lowercase()
    val (background, foreground, border) = when (key) {
        "armed" -> Triple(AppColors.warningSoft, AppColors.warning, AppColors.warning.copy(alpha = 0.35f))
        "long", "running" -> Triple(AppColors.successSoft, AppColors.success, AppColors.success.copy(alpha = 0.35f))
        "short", "error" -> Triple(AppColors.dangerSoft, AppColors.danger, AppColors.danger.copy(alpha = 0.35f))
        "reversing" -> Triple(AppColors.accentSoft, AppColors.accent, AppColors.accent.copy(alpha = 0.35f))
        "stopped" -> Triple(AppColors.surfaceMuted, AppColors.textMuted, AppColors.border)
        else -> Triple(AppColors.surfaceMuted, AppColors.textSecondary, AppColors.border)
    }
    val label = key.replace("_", " ").uppercase().ifBlank { "UNKNOWN" }
    Row(
        modifier = modifier
            .clip(RoundedCornerShape(999.dp))
            .background(background)
            .border(1.dp, border, RoundedCornerShape(999.dp))
            .padding(horizontal = 10.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        if (pulse) {
            Box(
                Modifier
                    .size(7.dp)
                    .clip(CircleShape)
                    .background(foreground.copy(alpha = 0.85f))
            )
        }
        Text(label, color = foreground, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 0.4.sp)
    }
}

@Composable
private fun ModeChipRow(selected: String, onSelect: (String) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        listOf("Live", "Backtest").forEach { mode ->
            val active = selected == mode
            Text(
                mode,
                modifier = Modifier
                    .clip(RoundedCornerShape(999.dp))
                    .background(if (active) AppColors.accentSoft else AppColors.surfaceMuted)
                    .border(1.dp, if (active) AppColors.accent.copy(alpha = 0.45f) else AppColors.border, RoundedCornerShape(999.dp))
                    .clickable { onSelect(mode) }
                    .padding(horizontal = 14.dp, vertical = 8.dp),
                color = if (active) AppColors.accent else AppColors.textSecondary,
                fontSize = 13.sp,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

@Composable
fun TrapReversalScreen(state: AppState, vm: MainViewModel) {
    var symbol by remember { mutableStateOf("GOLD") }
    var riskAmount by remember { mutableStateOf("100") }
    var levels by remember { mutableStateOf<TrapReversalLevels?>(null) }
    var runs by remember { mutableStateOf<List<TrapReversalRunRow>>(emptyList()) }
    var loading by remember { mutableStateOf(false) }
    var actionBusy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    val normalized = symbol.trim().uppercase()
    val symbolRunning = runs.any { it.symbol.uppercase() == normalized || it.displaySymbol.uppercase() == normalized }

    suspend fun refresh(silent: Boolean = false) {
        if (!silent) loading = true
        try {
            runs = vm.fetchTrapReversalActive()
            levels = vm.fetchTrapReversalLevels(normalized)
            error = ""
        } catch (exc: Exception) {
            if (!silent) error = exc.message.orEmpty()
        } finally {
            if (!silent) loading = false
        }
    }

    LaunchedEffect(normalized, state.selectedAccountId) {
        while (isActive) {
            refresh(silent = true)
            delay(3000)
        }
    }

    Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(
            "H1 support/resistance trap engine with live FSM monitoring.",
            color = AppColors.textSecondary,
            fontSize = 13.sp,
            lineHeight = 18.sp,
        )
        DataCard {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(symbol, { symbol = it.uppercase() }, label = { Text("Symbol") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(riskAmount, { riskAmount = it }, label = { Text("Risk amount") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (!symbolRunning) {
                        PrimaryButton(if (actionBusy) "Starting..." else "Start engine", onClick = {
                            scope.launch {
                                actionBusy = true
                                try {
                                    vm.startTrapReversal(normalized, riskAmount.toDoubleOrNull() ?: 0.0)
                                    refresh(true)
                                } catch (exc: Exception) {
                                    error = exc.message.orEmpty()
                                } finally {
                                    actionBusy = false
                                }
                            }
                        }, modifier = Modifier.weight(1f), enabled = !actionBusy && normalized.isNotBlank())
                    }
                    if (symbolRunning) {
                        SecondaryButton("Stop engine", onClick = {
                            scope.launch {
                                actionBusy = true
                                try {
                                    vm.stopTrapReversal(normalized)
                                    refresh(true)
                                } catch (exc: Exception) {
                                    error = exc.message.orEmpty()
                                } finally {
                                    actionBusy = false
                                }
                            }
                        }, danger = true, modifier = Modifier.weight(1f), enabled = !actionBusy)
                    }
                }
            }
        }
        ErrorText(error)
        if (loading && levels == null) EmptyText("Loading H1 levels...")
        levels?.let { levelData ->
            DataCard {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Text("H1 Levels", fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary)
                        Text(levelData.displaySymbol.ifBlank { levelData.symbol }, color = AppColors.textMuted, fontSize = 12.sp)
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("Supports", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = AppColors.success, letterSpacing = 0.5.sp)
                            levelData.supports.forEach { price ->
                                Text(
                                    formatPrice(price, levelData.priceDigits),
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clip(RoundedCornerShape(8.dp))
                                        .background(AppColors.successSoft)
                                        .border(1.dp, AppColors.success.copy(alpha = 0.25f), RoundedCornerShape(8.dp))
                                        .padding(horizontal = 8.dp, vertical = 6.dp),
                                    color = AppColors.success,
                                    fontFamily = FontFamily.Monospace,
                                    fontSize = 12.sp,
                                )
                            }
                        }
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("Resistances", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = AppColors.danger, letterSpacing = 0.5.sp)
                            levelData.resistances.forEach { price ->
                                Text(
                                    formatPrice(price, levelData.priceDigits),
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clip(RoundedCornerShape(8.dp))
                                        .background(AppColors.dangerSoft)
                                        .border(1.dp, AppColors.danger.copy(alpha = 0.25f), RoundedCornerShape(8.dp))
                                        .padding(horizontal = 8.dp, vertical = 6.dp),
                                    color = AppColors.danger,
                                    fontFamily = FontFamily.Monospace,
                                    fontSize = 12.sp,
                                )
                            }
                        }
                    }
                }
            }
        }
        DataCard {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Active engines", fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary)
                if (runs.isEmpty()) {
                    Text("No active trap reversal engines.", color = AppColors.textMuted, fontSize = 13.sp)
                } else {
                    runs.forEach { run ->
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                            Column {
                                Text(run.displaySymbol.ifBlank { run.symbol }, fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary)
                                Text("Risk ${formatMoney(run.riskAmount)}", fontSize = 12.sp, color = AppColors.textSecondary)
                            }
                            StrategyStatusPill(run.state.ifBlank { "running" }, pulse = true)
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun TrendPilotScreen(state: AppState, vm: MainViewModel) {
    var mode by remember { mutableStateOf("Live") }
    var symbol by remember { mutableStateOf("XAUUSD") }
    var quantity by remember { mutableStateOf("0.01") }
    var fromDate by remember { mutableStateOf(LocalDate.now().minusDays(7).format(DateTimeFormatter.ISO_DATE)) }
    var toDate by remember { mutableStateOf(LocalDate.now().format(DateTimeFormatter.ISO_DATE)) }
    var activeRuns by remember { mutableStateOf<List<TrendPilotRunRow>>(emptyList()) }
    var historyRuns by remember { mutableStateOf<List<TrendPilotHistoryRow>>(emptyList()) }
    var backtests by remember { mutableStateOf<List<TrendPilotBacktestRow>>(emptyList()) }
    var backtestHasNextPage by remember { mutableStateOf(false) }
    var backtestEndCursor by remember { mutableStateOf<String?>(null) }
    var backtestsLoadingMore by remember { mutableStateOf(false) }
    var expandedRunId by remember { mutableStateOf("") }
    var expandedBacktestId by remember { mutableStateOf("") }
    var expandedRolls by remember { mutableStateOf<List<TrendPilotRollRow>>(emptyList()) }
    var expandedSummary by remember { mutableStateOf<JSONObject?>(null) }
    var actionBusy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var settingsOpen by remember { mutableStateOf(false) }
    var partialAtPct by remember { mutableStateOf("0") }
    var partialQtyPct by remember { mutableStateOf("0") }
    var moveSlToBreakeven by remember { mutableStateOf(false) }
    var settingsSaving by remember { mutableStateOf(false) }
    val accounts = remember(state.accounts) { internationalAccounts(state) }
    val selectedAccountIds = remember { mutableStateListOf<String>() }
    val selectionInitialized = remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(accounts, state.selectedAccountId) {
        if (accounts.isEmpty()) {
            selectedAccountIds.clear()
            selectionInitialized.value = false
            return@LaunchedEffect
        }
        if (!selectionInitialized.value) {
            val defaultId = accounts.firstOrNull { it.id == state.selectedAccountId }?.id ?: accounts.first().id
            selectedAccountIds.clear()
            selectedAccountIds.add(defaultId)
            selectionInitialized.value = true
        } else {
            selectedAccountIds.removeAll { id -> accounts.none { it.id == id } }
        }
    }

    val runningByAccount = remember(activeRuns, symbol) {
        activeRuns.filter { trendPilotRunMatchesSymbol(it, symbol) }.associateBy { it.accountId }
    }
    val startableIds = selectedAccountIds.filter { !runningByAccount.containsKey(it) }
    val stoppableIds = selectedAccountIds.filter { runningByAccount.containsKey(it) }
    val showStart = startableIds.isNotEmpty()
    val showStop = stoppableIds.isNotEmpty()

    suspend fun refreshLive(silent: Boolean = false) {
        try {
            activeRuns = vm.fetchTrendPilotActive()
            historyRuns = vm.fetchTrendPilotHistoryList()
            error = ""
        } catch (exc: Exception) {
            if (!silent) error = exc.message.orEmpty()
        }
    }

    suspend fun refreshBacktests(reset: Boolean = true) {
        try {
            val page = vm.fetchTrendPilotBacktests(cursor = null)
            backtests = page.results
            backtestHasNextPage = page.hasNextPage
            backtestEndCursor = page.endCursor
            error = ""
        } catch (exc: Exception) {
            if (reset) backtests = emptyList()
            error = exc.message.orEmpty()
        }
    }

    suspend fun loadMoreBacktests() {
        val cursor = backtestEndCursor ?: return
        if (!backtestHasNextPage || backtestsLoadingMore) return
        backtestsLoadingMore = true
        try {
            val page = vm.fetchTrendPilotBacktests(cursor = cursor)
            backtests = backtests + page.results
            backtestHasNextPage = page.hasNextPage
            backtestEndCursor = page.endCursor
        } catch (exc: Exception) {
            error = exc.message.orEmpty()
        } finally {
            backtestsLoadingMore = false
        }
    }

    suspend fun loadBacktestSettings() {
        try {
            val settings = vm.fetchTrendPilotBacktestSettings()
            partialAtPct = settings.optDouble("partial_at_pct", 0.0).toString()
            partialQtyPct = settings.optDouble("partial_qty_pct", 0.0).toString()
            moveSlToBreakeven = settings.optBoolean("move_sl_to_breakeven", false)
        } catch (exc: Exception) {
            if (error.isBlank()) error = exc.message.orEmpty()
        }
    }

    LaunchedEffect(mode) {
        if (mode == "Live") {
            while (isActive) {
                refreshLive(silent = true)
                delay(3000)
            }
        } else {
            loadBacktestSettings()
            refreshBacktests()
        }
    }

    LaunchedEffect(expandedRunId) {
        if (expandedRunId.isBlank()) {
            expandedRolls = emptyList()
            expandedSummary = null
            return@LaunchedEffect
        }
        try {
            val detail = vm.fetchTrendPilotHistoryDetail(expandedRunId)
            expandedRolls = parseTrendPilotRolls(detail.optJSONArray("trade_rolls") ?: JSONArray())
            expandedSummary = detail.optJSONObject("summary")
        } catch (exc: Exception) {
            error = exc.message.orEmpty()
        }
    }

    LaunchedEffect(expandedBacktestId) {
        if (expandedBacktestId.isBlank()) {
            expandedRolls = emptyList()
            expandedSummary = null
            return@LaunchedEffect
        }
        try {
            val detail = vm.fetchTrendPilotBacktestDetail(expandedBacktestId)
            expandedRolls = parseTrendPilotRolls(detail.optJSONArray("rolls") ?: JSONArray())
            expandedSummary = detail.optJSONObject("summary")
        } catch (exc: Exception) {
            error = exc.message.orEmpty()
        }
    }

    Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(
            "H4 breakout engine with always-in reversal stops and optional funded loss cap.",
            color = AppColors.textSecondary,
            fontSize = 13.sp,
            lineHeight = 18.sp,
        )
        ModeChipRow(mode) { mode = it }
        DataCard {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(symbol, { symbol = it.uppercase() }, label = { Text("Symbol") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(quantity, { quantity = it }, label = { Text("Quantity") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                if (mode == "Backtest") {
                    OutlinedTextField(fromDate, { fromDate = it }, label = { Text("From") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(toDate, { toDate = it }, label = { Text("To") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = { settingsOpen = true }, modifier = Modifier.weight(1f)) {
                            Text("Settings")
                        }
                        PrimaryButton(if (actionBusy) "Running..." else "Run backtest", onClick = {
                            scope.launch {
                                actionBusy = true
                                try {
                                    vm.runTrendPilotBacktest(symbol, quantity.toDoubleOrNull() ?: 0.01, fromDate, toDate)
                                    refreshBacktests()
                                } catch (exc: Exception) {
                                    error = exc.message.orEmpty()
                                } finally {
                                    actionBusy = false
                                }
                            }
                        }, modifier = Modifier.weight(1f), enabled = !actionBusy)
                    }
                } else {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (showStart) {
                            PrimaryButton(if (actionBusy) "Starting..." else "Start", onClick = {
                                scope.launch {
                                    actionBusy = true
                                    try {
                                        vm.startTrendPilot(symbol, quantity.toDoubleOrNull() ?: 0.01, startableIds)
                                        refreshLive(true)
                                    } catch (exc: Exception) {
                                        error = exc.message.orEmpty()
                                    } finally {
                                        actionBusy = false
                                    }
                                }
                            }, modifier = Modifier.weight(1f), enabled = !actionBusy)
                        }
                        if (showStop) {
                            SecondaryButton(if (actionBusy) "Stopping..." else "Stop", onClick = {
                                scope.launch {
                                    actionBusy = true
                                    try {
                                        vm.stopTrendPilot(symbol, stoppableIds)
                                        refreshLive(true)
                                    } catch (exc: Exception) {
                                        error = exc.message.orEmpty()
                                    } finally {
                                        actionBusy = false
                                    }
                                }
                            }, danger = true, modifier = Modifier.weight(1f), enabled = !actionBusy)
                        }
                    }
                }
            }
        }
        if (mode == "Live") {
            DataCard {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Text("Accounts", fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            TextButton(onClick = { selectedAccountIds.clear(); selectedAccountIds.addAll(accounts.map { it.id }) }, enabled = accounts.isNotEmpty()) {
                                Text("All", color = AppColors.accent, fontSize = 12.sp)
                            }
                            TextButton(onClick = { selectedAccountIds.clear() }, enabled = selectedAccountIds.isNotEmpty()) {
                                Text("Clear", color = AppColors.accent, fontSize = 12.sp)
                            }
                        }
                    }
                    accounts.forEach { account ->
                        val checked = selectedAccountIds.contains(account.id)
                        val activeRun = runningByAccount[account.id]
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(12.dp))
                                .background(if (checked) AppColors.accentSoft else AppColors.surfaceMuted)
                                .border(1.dp, if (checked) AppColors.accent.copy(alpha = 0.35f) else AppColors.border, RoundedCornerShape(12.dp))
                                .clickable {
                                    if (checked) selectedAccountIds.remove(account.id) else selectedAccountIds.add(account.id)
                                }
                                .padding(horizontal = 8.dp, vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Checkbox(
                                checked = checked,
                                onCheckedChange = { value ->
                                    if (value) selectedAccountIds.add(account.id) else selectedAccountIds.remove(account.id)
                                },
                                colors = CheckboxDefaults.colors(checkedColor = AppColors.accent),
                            )
                            Column(Modifier.weight(1f)) {
                                Text(account.name, fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary, fontSize = 14.sp)
                                if (account.id == state.selectedAccountId) {
                                    Text("Selected in terminal", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = AppColors.success, letterSpacing = 0.4.sp)
                                }
                            }
                            if (activeRun != null) StrategyStatusPill(trendPilotRunStatusKey(activeRun), pulse = true)
                        }
                    }
                }
            }
            DataCard {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Active runs", fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary)
                    if (activeRuns.isEmpty()) {
                        Text("No active Trend Pilot runs.", color = AppColors.textMuted, fontSize = 13.sp)
                    } else {
                        activeRuns.forEach { run ->
                            Column(
                                Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(12.dp))
                                    .background(AppColors.surfaceMuted)
                                    .padding(10.dp),
                                verticalArrangement = Arrangement.spacedBy(6.dp),
                            ) {
                                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                    Text(run.displaySymbol.ifBlank { run.symbol }, fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary)
                                    Text(run.accountName.ifBlank { run.accountId }, color = AppColors.textSecondary, fontSize = 12.sp)
                                    StrategyStatusPill(trendPilotRunStatusKey(run), pulse = true)
                                    if (run.currentSide.isNotBlank()) StrategyStatusPill(run.currentSide.lowercase())
                                }
                                Text("Rolls ${run.rollCount} · Qty ${formatQty(run.quantity)} · P/L ${formatMoney(run.cumulativePnl)}", color = AppColors.textSecondary, fontSize = 12.sp)
                                if (run.windowHigh != null && run.windowLow != null) {
                                    Text(
                                        "Window ${formatPrice(run.windowHigh)} / ${formatPrice(run.windowLow)}",
                                        color = AppColors.textMuted,
                                        fontSize = 12.sp,
                                        fontFamily = FontFamily.Monospace,
                                    )
                                    Text(
                                        "Long ${formatPrice(run.windowHigh + TREND_PILOT_BUFFER_USD)} · Short ${formatPrice(run.windowLow - TREND_PILOT_BUFFER_USD)}",
                                        color = AppColors.textMuted,
                                        fontSize = 11.sp,
                                    )
                                }
                                if (run.lastError.isNotBlank()) Text(run.lastError, color = AppColors.danger, fontSize = 12.sp)
                            }
                        }
                    }
                }
            }
            DataCard {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Run history", fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary)
                    if (historyRuns.isEmpty()) EmptyText("No run history yet.")
                    historyRuns.forEach { run ->
                        val expanded = expandedRunId == run.runId
                        Column(
                            Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(12.dp))
                                .border(1.dp, AppColors.border, RoundedCornerShape(12.dp))
                                .clickable { expandedRunId = if (expanded) "" else run.runId }
                                .padding(10.dp),
                        ) {
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text(run.displaySymbol.ifBlank { run.symbol }, fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary)
                                if (run.accountName.isNotBlank()) Text(run.accountName, color = AppColors.textSecondary, fontSize = 12.sp)
                                StrategyStatusPill(if (run.status.equals("stopped", true)) "stopped" else "running")
                            }
                            Text("${run.closedTrades ?: 0} trades · ${run.rollCount} rolls", color = AppColors.textMuted, fontSize = 12.sp)
                            Text("P/L ${formatMoney(run.totalPnl ?: 0.0)}", color = AppColors.textPrimary, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                            if (expanded) {
                                Spacer(Modifier.height(6.dp))
                                expandedSummary?.let { summary ->
                                    Text(
                                        "Max DD ${formatMoney(summary.optDouble("max_drawdown"))} · Streak ${summary.optInt("max_profit_streak")}/${summary.optInt("max_loss_streak")}",
                                        color = AppColors.textSecondary,
                                        fontSize = 12.sp,
                                    )
                                }
                                expandedRolls.take(8).forEach { roll ->
                                    Text(
                                        "${roll.eventType} ${roll.fromSide}→${roll.toSide} ${formatMoney(roll.pnlUpdate)}",
                                        color = AppColors.textMuted,
                                        fontSize = 11.sp,
                                    )
                                }
                            }
                        }
                    }
                }
            }
        } else {
            DataCard {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Backtest results", fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary)
                    if (backtests.isEmpty()) EmptyText("No backtest results yet.")
                    backtests.forEach { result ->
                        val expanded = expandedBacktestId == result.resultId
                        Column(
                            Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(12.dp))
                                .border(1.dp, AppColors.border, RoundedCornerShape(12.dp))
                                .clickable { expandedBacktestId = if (expanded) "" else result.resultId }
                                .padding(10.dp),
                        ) {
                            Text("${result.displaySymbol.ifBlank { result.symbol }} · ${result.fromDate} – ${result.toDate}", fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary)
                            Text("P/L ${formatMoney(result.totalPnl ?: 0.0)} · ${result.closedTrades ?: 0} trades · Qty ${formatQty(result.quantity)}", color = AppColors.textSecondary, fontSize = 12.sp)
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                OutlinedButton(onClick = { expandedBacktestId = if (expanded) "" else result.resultId }) {
                                    Text(if (expanded) "Hide" else "Details", fontSize = 12.sp)
                                }
                                OutlinedButton(
                                    onClick = {
                                        scope.launch {
                                            vm.deleteTrendPilotBacktest(result.resultId)
                                            if (expandedBacktestId == result.resultId) expandedBacktestId = ""
                                            refreshBacktests()
                                        }
                                    },
                                    border = BorderStroke(1.dp, AppColors.danger.copy(alpha = 0.35f)),
                                ) {
                                    Text("Delete", color = AppColors.danger, fontSize = 12.sp)
                                }
                            }
                            if (expanded) {
                                expandedRolls.take(8).forEach { roll ->
                                    Text("${roll.eventType} ${formatMoney(roll.pnlUpdate)}", color = AppColors.textMuted, fontSize = 11.sp)
                                }
                            }
                        }
                    }
                    if (backtestHasNextPage) {
                        OutlinedButton(
                            onClick = { scope.launch { loadMoreBacktests() } },
                            modifier = Modifier.fillMaxWidth(),
                            enabled = !backtestsLoadingMore,
                        ) {
                            Text(if (backtestsLoadingMore) "Loading..." else "Load more", fontSize = 12.sp)
                        }
                    }
                }
            }
        }
        ErrorText(error)
    }

    if (settingsOpen) {
        AlertDialog(
            onDismissRequest = { if (!settingsSaving) settingsOpen = false },
            title = { Text("Backtest settings") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        partialAtPct,
                        { partialAtPct = it },
                        label = { Text("Book partial at (% price move)") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    OutlinedTextField(
                        partialQtyPct,
                        { partialQtyPct = it },
                        label = { Text("Partial quantity (%)") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(
                            checked = moveSlToBreakeven,
                            onCheckedChange = { moveSlToBreakeven = it },
                            colors = CheckboxDefaults.colors(checkedColor = AppColors.accent),
                        )
                        Text("Move SL to breakeven after partial", color = AppColors.textPrimary, fontSize = 13.sp)
                    }
                }
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        scope.launch {
                            settingsSaving = true
                            try {
                                vm.saveTrendPilotBacktestSettings(
                                    partialAtPct.toDoubleOrNull() ?: 0.0,
                                    partialQtyPct.toDoubleOrNull() ?: 0.0,
                                    moveSlToBreakeven,
                                )
                                settingsOpen = false
                            } catch (exc: Exception) {
                                error = exc.message.orEmpty()
                            } finally {
                                settingsSaving = false
                            }
                        }
                    },
                    enabled = !settingsSaving,
                ) { Text(if (settingsSaving) "Saving..." else "Save") }
            },
            dismissButton = {
                TextButton(onClick = { if (!settingsSaving) settingsOpen = false }) { Text("Cancel") }
            },
        )
    }
}

private fun formatPrice(value: Double?, digits: Int? = 2): String {
    if (value == null || value.isNaN()) return "-"
    return "%.${digits ?: 2}f".format(value)
}
