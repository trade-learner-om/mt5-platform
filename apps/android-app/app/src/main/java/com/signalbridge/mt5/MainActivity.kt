package com.signalbridge.mt5

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Application
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color as AndroidColor
import android.os.Build
import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.wrapContentWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material.icons.filled.CandlestickChart
import androidx.compose.material.icons.filled.Layers
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.outlined.Apps
import androidx.compose.material.icons.outlined.CandlestickChart
import androidx.compose.material.icons.outlined.Layers
import androidx.compose.material.icons.outlined.StarOutline
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Typography
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.fragment.app.FragmentActivity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import androidx.compose.ui.text.TextStyle
import androidx.compose.foundation.layout.PaddingValues
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.util.concurrent.TimeUnit
import kotlin.math.min

private val Application.hostDataStore by preferencesDataStore("signalbridge_android")
private val jsonMediaType = "application/json; charset=utf-8".toMediaType()
private const val strategyNotificationChannelId = "gold_strategy_status"

private object AppConfig {
    const val directApiBase = "https://api.signalbridge.in"
}

class MainActivity : FragmentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        createStrategyNotificationChannel()
        requestStrategyNotificationPermission()
        setContent {
            SignalBridgeAndroidApp()
        }
    }

    private fun createStrategyNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel(strategyNotificationChannelId, "Gold strategy status", NotificationManager.IMPORTANCE_DEFAULT)
        channel.description = "Status changes for GOLD strategy runs"
        manager.createNotificationChannel(channel)
    }

    private fun requestStrategyNotificationPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) return
        requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 2026)
    }
}

enum class BootStatus {
    CheckingHost,
    HostRequired,
    BiometricRequired,
    AuthRequired,
    Ready
}

enum class AppPage(val label: String) {
    Watchlist("Watch"),
    Trading("Trade"),
    Positions("Positions"),
    Strategies("More");

    fun navigationIcon(selected: Boolean) = when (this) {
        Watchlist -> if (selected) Icons.Filled.Star else Icons.Outlined.StarOutline
        Trading -> if (selected) Icons.Filled.CandlestickChart else Icons.Outlined.CandlestickChart
        Positions -> if (selected) Icons.Filled.Layers else Icons.Outlined.Layers
        Strategies -> if (selected) Icons.Filled.Apps else Icons.Outlined.Apps
    }
}

enum class StrategySection { TrapReversal, TrendPilot, Planner }

enum class AppAppearance(val rawValue: String) {
    System("system"),
    Automatic("automatic"),
    Light("light"),
    Dark("dark");

    val label: String
        get() = when (this) {
            System -> "Follow system"
            Automatic -> "Auto 6am/6pm"
            Light -> "Light"
            Dark -> "Dark"
        }

    companion object {
        fun fromRaw(value: String?): AppAppearance = entries.firstOrNull { it.rawValue == value } ?: System
    }
}

private data class AppPalette(
    val background: Color,
    val surface: Color,
    val surfaceMuted: Color,
    val border: Color,
    val textPrimary: Color,
    val textSecondary: Color,
    val textMuted: Color,
    val accent: Color,
    val accentSoft: Color,
    val danger: Color,
    val dangerSoft: Color,
    val success: Color,
    val successSoft: Color,
    val warning: Color,
    val warningSoft: Color,
    val skySoft: Color,
    val skyDeep: Color,
    val trap: Color,
    val trapSoft: Color,
    val cardShadow: Color,
)

private val lightPalette = AppPalette(
    background = Color(0xFFF3F5F9),
    surface = Color.White,
    surfaceMuted = Color(0xFFF8FAFC),
    border = Color(0xFFE5EAF2),
    textPrimary = Color(0xFF0F172A),
    textSecondary = Color(0xFF64748B),
    textMuted = Color(0xFF94A3B8),
    accent = Color(0xFF4F46E5),
    accentSoft = Color(0xFFEEF2FF),
    danger = Color(0xFFE11D48),
    dangerSoft = Color(0xFFFFF1F2),
    success = Color(0xFF059669),
    successSoft = Color(0xFFECFDF5),
    warning = Color(0xFFB45309),
    warningSoft = Color(0xFFFFFBEB),
    skySoft = Color(0xFFE0F2FE),
    skyDeep = Color(0xFF0369A1),
    trap = Color(0xFF6D28D9),
    trapSoft = Color(0xFFEDE9FE),
    cardShadow = Color(0x141E3A8A),
)

private val darkPalette = AppPalette(
    background = Color(0xFF020617),
    surface = Color(0xFF0F172A),
    surfaceMuted = Color(0xFF172033),
    border = Color(0xFF334155),
    textPrimary = Color(0xFFE5EEF9),
    textSecondary = Color(0xFFBFDBFE),
    textMuted = Color(0xFF94A3B8),
    accent = Color(0xFFA5B4FC),
    accentSoft = Color(0xFF1E1B4B),
    danger = Color(0xFFFB7185),
    dangerSoft = Color(0xFF4C0519),
    success = Color(0xFF34D399),
    successSoft = Color(0xFF052E2B),
    warning = Color(0xFFFBBF24),
    warningSoft = Color(0xFF422006),
    skySoft = Color(0xFF082F49),
    skyDeep = Color(0xFF7DD3FC),
    trap = Color(0xFFC4B5FD),
    trapSoft = Color(0xFF2E1065),
    cardShadow = Color(0x5C020617),
)

private object AppColors {
    var background = lightPalette.background
    var surface = lightPalette.surface
    var surfaceMuted = lightPalette.surfaceMuted
    var border = lightPalette.border
    var textPrimary = lightPalette.textPrimary
    var textSecondary = lightPalette.textSecondary
    var textMuted = lightPalette.textMuted
    var accent = lightPalette.accent
    var accentSoft = lightPalette.accentSoft
    var danger = lightPalette.danger
    var dangerSoft = lightPalette.dangerSoft
    var success = lightPalette.success
    var successSoft = lightPalette.successSoft
    var warning = lightPalette.warning
    var warningSoft = lightPalette.warningSoft
    var skySoft = lightPalette.skySoft
    var skyDeep = lightPalette.skyDeep
    var trap = lightPalette.trap
    var trapSoft = lightPalette.trapSoft
    var cardShadow = lightPalette.cardShadow

    fun apply(palette: AppPalette) {
        background = palette.background
        surface = palette.surface
        surfaceMuted = palette.surfaceMuted
        border = palette.border
        textPrimary = palette.textPrimary
        textSecondary = palette.textSecondary
        textMuted = palette.textMuted
        accent = palette.accent
        accentSoft = palette.accentSoft
        danger = palette.danger
        dangerSoft = palette.dangerSoft
        success = palette.success
        successSoft = palette.successSoft
        warning = palette.warning
        warningSoft = palette.warningSoft
        skySoft = palette.skySoft
        skyDeep = palette.skyDeep
        trap = palette.trap
        trapSoft = palette.trapSoft
        cardShadow = palette.cardShadow
    }
}

private object LoaderColors {
    val background = Color(0xFF0B1220)
    val surface = Color(0xFF151F33)
    val accent = Color(0xFF818CF8)
    val accentGlow = Color(0xFF6366F1)
    val text = Color(0xFFE2E8F0)
    val muted = Color(0xFF94A3B8)
}

data class AppState(
    val bootStatus: BootStatus = BootStatus.CheckingHost,
    val apiBase: String = "",
    val wsBase: String = "",
    val token: String = "",
    val fullName: String = "",
    val username: String = "",
    val selectedMarket: String = "INTERNATIONAL",
    val selectedAccountId: String = "",
    val liveStatus: String = "CONNECTING",
    val bootLoading: Boolean = true,
    val dashboardSyncing: Boolean = false,
    val syncMessage: String = "",
    val actionBusy: Boolean = false,
    val actionMessage: String = "",
    val message: String = "Connecting securely...",
    val error: String = "",
    val appearance: AppAppearance = AppAppearance.System,
    val page: AppPage = AppPage.Watchlist,
    val strategySection: StrategySection? = null,
    val positionsTab: String = "Positions",
    val tradeDraftSymbol: String = "",
    val showTradeSheet: Boolean = false,
    val showOrderEditSheet: Boolean = false,
    val orderEditTarget: OrderRow? = null,
    val accounts: List<AccountRow> = emptyList(),
    val watchlist: List<WatchRow> = emptyList(),
    val prices: Map<String, Double> = emptyMap(),
    val priceDigits: Map<String, Int> = emptyMap(),
    val orders: List<OrderRow> = emptyList(),
    val plans: List<PlannerRow> = emptyList(),
    val goldStrategy: GoldStrategyState? = null,
    val continuationFailure: ContinuationFailureState? = null,
) {
    val runningPl: Double
        get() = orders.filter { it.status in setOf("FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED") }.sumOf { it.unrealizedPl ?: 0.0 }
}

data class AccountRow(
    val id: String,
    val name: String,
    val number: String,
    val risk: Double,
    val equityBalance: Double? = null,
    val availableMargin: Double? = null,
    val currencyCode: String = "USD",
    val brokerScopeKey: String? = null,
    val marketType: String? = null,
    val brokerType: String? = null,
    val brokerServer: String? = null,
) {
    fun brokerScope(): String =
        brokerScopeKey?.takeIf { it.isNotBlank() }
            ?: "${marketType.orEmpty().ifBlank { "INTERNATIONAL" }.uppercase()}|${brokerType.orEmpty().ifBlank { "MT5" }.uppercase()}|${brokerServer.orEmpty().uppercase()}"
}
data class WatchRow(val symbol: String, val price: Double?)
data class OrderRow(
    val id: String,
    val accountId: String = "",
    val symbol: String,
    val side: String,
    val status: String,
    val orderType: String,
    val entry: Double?,
    val stopLoss: Double?,
    val target: Double?,
    val quantity: Double?,
    val positionQuantity: Double?,
    val unrealizedPl: Double?,
    val realizedPl: Double?,
    val dryRun: Boolean,
    val failureReason: String? = null,
    val placementFallbackReason: String? = null,
    val comment: String? = null,
    val metaPositionId: String? = null,
    val externalSource: String? = null,
    val rrRatio: Double? = null,
    val isOpenPosition: Boolean = false,
    val plannerPlanAccountId: String? = null,
    val brokerInfoAccountId: String? = null,
    val brokerInfoAccountName: String? = null,
    val brokerInfoAvailableMargin: Double? = null,
    val createdAt: String? = null,
    val openedAt: String? = null,
    val closedAt: String? = null,
    val updatedAt: String? = null,
)
data class OrdersTabRow(
    val id: String,
    val symbol: String,
    val side: String,
    val orderTypeLabel: String,
    val price: Double?,
    val quantity: Double?,
    val status: String,
    val derived: Boolean = false,
    val editable: Boolean = false,
    val sourceOrder: OrderRow? = null,
    val accountId: String = "",
    val brokerInfoAccountName: String? = null,
)
data class OrderEventRow(
    val id: String,
    val eventType: String,
    val status: String,
    val message: String,
    val eventTsIst: String,
    val failureReason: String? = null,
    val payloadJson: String? = null
)
data class BrokerTradeHistoryRow(
    val id: String,
    val symbol: String,
    val type: String,
    val status: String,
    val openPrice: Double?,
    val closePrice: Double?,
    val profit: Double,
    val netProfit: Double,
    val isRunning: Boolean
)
data class GoldConfigRow(
    val symbol: String,
    val running: Boolean,
    val triggerSource: String,
    val pdHigh: Double?,
    val pdLow: Double?,
    val userTriggerPrice: Double?
)
data class GoldRunRow(
    val id: String,
    val symbol: String,
    val status: String,
    val runningPl: Double,
    val bookedPl: Double,
    val quantity: Double
)
data class GoldStrategyState(
    val config: GoldConfigRow,
    val running: List<GoldRunRow>,
    val history: List<GoldRunRow>
)
data class ContinuationFailureEventRow(
    val id: String,
    val eventType: String,
    val status: String,
    val message: String,
    val createdAt: String,
    val createdAtIst: String,
)
data class ContinuationFailureRunRow(
    val id: String,
    val symbol: String,
    val status: String,
    val direction: String,
    val pivotPrice: Double?,
    val runningPl: Double,
    val bookedPl: Double,
    val events: List<ContinuationFailureEventRow>,
)
data class ContinuationFailureSymbolConfig(
    val symbol: String,
    val pivotPrice: Double?,
)
data class ContinuationFailureState(
    val symbols: List<ContinuationFailureSymbolConfig>,
    val running: List<ContinuationFailureRunRow>,
    val history: List<ContinuationFailureRunRow>,
)
data class PlannerRow(val id: String, val symbol: String, val status: String, val runtime: String, val entry: Double?, val stopLoss: Double?)
data class NotificationRow(
    val id: String,
    val category: String,
    val symbol: String,
    val status: String,
    val activity: String,
    val failureReason: String? = null,
    val placementFallbackReason: String? = null
)
class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val tokenKey = stringPreferencesKey("jwt_token")
    private val appearanceKey = stringPreferencesKey("appearance_mode")
    private val client = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .callTimeout(120, TimeUnit.SECONDS)
        .pingInterval(20, TimeUnit.SECONDS)
        .build()
    private var liveSocket: WebSocket? = null
    private var socketGeneration = 0
    private var reconnectAttempts = 0
    private var reconnectJob: Job? = null
    private var liveHeartbeatJob: Job? = null
    private var liveStaleWatchdogJob: Job? = null
    private var lastLiveDataAt = 0L
    private val liveStaleMs = 45_000L
    private val seenStrategyNotificationIds = mutableSetOf<String>()
    private var strategyNotificationsPrimed = false
    private var subscribedLiveSymbols = emptySet<String>()

    private val _state = MutableStateFlow(AppState())
    val state: StateFlow<AppState> = _state

    init {
        viewModelScope.launch { bootstrap() }
    }

    fun changePage(page: AppPage) = _state.update { it.copy(page = page, strategySection = null, error = "") }
    fun stepPage(offset: Int) {
        val pages = AppPage.entries
        val currentIndex = pages.indexOf(_state.value.page)
        if (currentIndex == -1) return
        val nextIndex = (currentIndex + offset).coerceIn(0, pages.lastIndex)
        if (nextIndex != currentIndex) {
            changePage(pages[nextIndex])
        }
    }
    fun openStrategy(section: StrategySection) = _state.update { it.copy(page = AppPage.Strategies, strategySection = section) }
    fun openPositionsFromSummary() = _state.update { it.copy(page = AppPage.Positions, positionsTab = "Positions", strategySection = null, error = "") }
    fun openOrderHistoryFromSummary() = _state.update { it.copy(page = AppPage.Positions, positionsTab = "History", strategySection = null, error = "") }
    fun setPositionsTab(tab: String) = _state.update { it.copy(positionsTab = tab) }
    fun closeStrategy() = _state.update { it.copy(strategySection = null) }
    fun openTrade(symbol: String = "") = _state.update {
        it.copy(page = AppPage.Trading, tradeDraftSymbol = symbol.trim().uppercase(), showTradeSheet = true)
    }
    fun showTradeForm() = _state.update { it.copy(page = AppPage.Trading, showTradeSheet = true) }
    fun closeTradeSheet() = _state.update { it.copy(showTradeSheet = false) }
    fun openOrderEditor(order: OrderRow) = _state.update { it.copy(orderEditTarget = order, showOrderEditSheet = true) }
    fun closeOrderEditSheet() = _state.update { it.copy(showOrderEditSheet = false, orderEditTarget = null) }

    fun saveHostAndConnect() {
        viewModelScope.launch { bootstrap() }
    }

    fun login(username: String, password: String, register: Boolean, fullName: String) {
        viewModelScope.launch {
            val path = if (register) "/auth/register" else "/auth/login"
            val body = JSONObject()
                .put("username", username.trim())
                .put("password", password)
            if (register) body.put("full_name", fullName.trim())
            _state.update { it.copy(bootLoading = true, error = "", message = "Signing in...") }
            try {
                val data = request(path, "POST", body)
                val token = data.optString("access_token")
                getApplication<Application>().hostDataStore.edit { it[tokenKey] = token }
                _state.update {
                    it.copy(
                        token = token,
                        fullName = data.optString("full_name", username),
                        username = data.optString("username", username),
                        bootStatus = BootStatus.Ready,
                        bootLoading = false,
                        dashboardSyncing = true,
                        syncMessage = "Opening dashboard..."
                    )
                }
                syncDashboard()
            } catch (exc: Exception) {
                _state.update { it.copy(bootLoading = false, bootStatus = BootStatus.AuthRequired, error = exc.message ?: "Login failed") }
            }
        }
    }

    fun logout() {
        viewModelScope.launch {
            reconnectJob?.cancel()
            socketGeneration += 1
            liveSocket?.cancel()
            getApplication<Application>().hostDataStore.edit { it.remove(tokenKey) }
            _state.update {
                it.copy(
                    token = "",
                    bootStatus = BootStatus.AuthRequired,
                    fullName = "",
                    username = "",
                    liveStatus = "DISCONNECTED",
                    orders = emptyList(),
                    plans = emptyList(),
                    goldStrategy = null,
                )
            }
        }
    }

    fun unlockSavedLogin() {
        _state.update {
            it.copy(
                bootStatus = BootStatus.Ready,
                bootLoading = false,
                dashboardSyncing = true,
                syncMessage = "Opening dashboard..."
            )
        }
        syncDashboard()
    }

    fun usePasswordLogin(message: String = "Please login again.") {
        viewModelScope.launch { requireLogin(message) }
    }

    fun refresh() {
        syncDashboard()
    }

    fun setAppearance(appearance: AppAppearance) {
        _state.update { it.copy(appearance = appearance) }
        viewModelScope.launch {
            getApplication<Application>().hostDataStore.edit { it[appearanceKey] = appearance.rawValue }
        }
    }

    fun onAppForegrounded() {
        val current = _state.value
        if (current.bootStatus != BootStatus.Ready || current.token.isBlank()) return
        viewModelScope.launch {
            reconnectJob?.cancel()
            reconnectAttempts = 0
            _state.update { it.copy(liveStatus = "RECONNECTING") }
            syncDashboard(showIndicator = true)
        }
    }

    fun addWatchSymbol(symbol: String) {
        viewModelScope.launch {
            runAction("Adding $symbol...") {
                val response = request("/watchlist", "POST", JSONObject().put("symbol", symbol.uppercase()))
                val digits = response.optNullableInt("price_digits")
                val brokerSymbol = response.optString("broker_symbol")
                if (digits != null) {
                    _state.update { current ->
                        current.copy(priceDigits = current.priceDigits + symbolPriceDigitEntries(brokerSymbol, symbol, digits))
                    }
                }
            }
        }
    }

    fun removeWatchSymbol(symbol: String) {
        viewModelScope.launch {
            runAction("Removing $symbol...") {
                request("/watchlist?symbol=${symbol.uppercase()}", "DELETE")
            }
        }
    }

    fun placeOrder(
        symbol: String,
        orderType: String,
        side: String,
        entry: String,
        stopLoss: String,
        target: String,
        retryableOrder: Boolean,
        automaticTradeManagement: Boolean
    ) {
        viewModelScope.launch {
            runAction("Placing order...") {
                val body = JSONObject()
                    .put("symbol", symbol.uppercase())
                    .put("order_type", orderType)
                    .put("side", side)
                    .put("entry", entry.toDoubleOrNull() ?: 0.0)
                    .put("stop_loss", stopLoss.toDoubleOrNull() ?: 0.0)
                    .put("target", target.toDoubleOrNull())
                    .put("retryable_order", (orderType == "LIMIT" || orderType == "SL") && retryableOrder)
                    .put("automatic_trade_management", automaticTradeManagement)
                request("/orders", "POST", body)
                closeTradeSheet()
            }
        }
    }

    suspend fun fetchOrderEvents(orderId: String): List<OrderEventRow> = parseOrderEvents(requestArray("/orders/$orderId/events"))

    suspend fun fetchBrokerTradeHistory(
        accountId: String? = null,
        page: Int = 1,
        pageSize: Int = 20,
        type: String = "all",
        today: Boolean = false,
    ): List<BrokerTradeHistoryRow> {
        val resolvedAccountId = accountId?.takeIf { it.isNotBlank() }
            ?: _state.value.selectedAccountId.takeIf { it.isNotBlank() }
            ?: _state.value.accounts.firstOrNull()?.id.orEmpty()
        val query = buildString {
            append("/broker/trade-history?page=$page&page_size=$pageSize&type=$type")
            if (today) append("&today=true")
            if (resolvedAccountId.isNotBlank()) append("&account_id=").append(resolvedAccountId)
        }
        return parseBrokerTradeHistory(request(query, "GET"))
    }

    suspend fun fetchClosedTodayBrokerTrades(accountFilter: String, accounts: List<AccountRow>): List<BrokerTradeHistoryRow> {
        val accountIds = if (accountFilter == "ALL") accounts.map { it.id }.filter { it.isNotBlank() }
        else listOfNotNull(accountFilter.takeIf { it.isNotBlank() })
        return accountIds.flatMap { accountId ->
            fetchBrokerTradeHistory(accountId = accountId, pageSize = 500, type = "closed", today = true)
        }
    }

    fun cancelOrder(orderId: String) {
        viewModelScope.launch {
            runAction("Cancelling order...") {
                request("/orders/$orderId/cancel", "POST")
            }
        }
    }

    fun modifyOrder(order: OrderRow, entry: String, stopLoss: String, target: String, quantity: String) {
        viewModelScope.launch {
            runAction("Updating order...") {
                val body = JSONObject()
                    .put("entry", entry.toDoubleOrNull() ?: 0.0)
                    .put("stop_loss", stopLoss.toDoubleOrNull() ?: 0.0)
                    .put("quantity", quantity.toDoubleOrNull() ?: 0.0)
                val targetValue = target.toDoubleOrNull()
                if (targetValue != null) body.put("target", targetValue)
                request("/orders/${order.id}/modify", "POST", body)
                closeOrderEditSheet()
            }
        }
    }

    fun closeOrder(order: OrderRow) {
        val qty = order.positionQuantity ?: order.quantity ?: 0.0
        viewModelScope.launch {
            runAction("Closing position...") {
                request("/orders/${order.id}/close", "POST", JSONObject().put("quantity", qty))
            }
        }
    }

    fun togglePlan(plan: PlannerRow, running: Boolean) {
        viewModelScope.launch {
            runAction(if (running) "Activating plan..." else "Deactivating plan...") {
                request("/trade-planner/plans/${plan.id}", "PATCH", JSONObject().put("auto_execution_enabled", running))
            }
        }
    }

    fun deletePlan(planId: String) {
        viewModelScope.launch {
            runAction("Deleting plan...") {
                request("/trade-planner/plans/$planId", "DELETE")
            }
        }
    }

    fun stopGoldStrategy() {
        viewModelScope.launch {
            runAction("Stopping GOLD strategy...") {
                request("/gold-strategy/stop", "POST")
            }
        }
    }

    fun stopContinuationFailure(symbol: String) {
        viewModelScope.launch {
            runAction("Stopping Continuation Failure...") {
                request("/continuation-failure/stop", "POST", JSONObject().put("symbol", symbol.uppercase()))
                refreshContinuationFailure()
            }
        }
    }

    fun startContinuationFailure(
        symbol: String,
        pivotPrice: Double,
        startReferencePrice: Double,
        targets: List<Pair<String, Double>>,
        exitTargets: List<Pair<Double, Double?>>,
    ) {
        viewModelScope.launch {
            runAction("Starting Continuation Failure...") {
                val targetsArray = JSONArray()
                targets.forEach { (accountId, risk) ->
                    targetsArray.put(JSONObject().put("account_db_id", accountId).put("risk_amount", risk))
                }
                val exitArray = JSONArray()
                exitTargets.forEach { (price, qty) ->
                    val row = JSONObject().put("price", price)
                    if (qty != null) row.put("quantity", qty)
                    else row.put("quantity", JSONObject.NULL)
                    exitArray.put(row)
                }
                val body = JSONObject()
                    .put("symbol", symbol.uppercase())
                    .put("pivot_price", pivotPrice)
                    .put("start_reference_price", startReferencePrice)
                    .put("targets", targetsArray)
                    .put("exit_targets", exitArray)
                request("/continuation-failure/start", "POST", body)
                refreshContinuationFailure()
            }
        }
    }

    suspend fun suggestInstruments(query: String): List<String> {
        val payload = request("/instruments/suggest?q=${java.net.URLEncoder.encode(query, "UTF-8")}&limit=8", "GET")
        val array = payload.optJSONArray("symbols") ?: JSONArray()
        return buildList {
            for (index in 0 until array.length()) {
                val value = array.optString(index).takeIf { it.isNotBlank() } ?: continue
                add(value)
            }
        }
    }

    suspend fun resolveContinuationFailureSymbol(symbol: String): JSONObject =
        request("/continuation-failure/symbol?symbol=${java.net.URLEncoder.encode(symbol.uppercase(), "UTF-8")}", "GET")

    private suspend fun refreshContinuationFailure() {
        val payload = request("/continuation-failure", "GET")
        _state.update { it.copy(continuationFailure = parseContinuationFailure(payload)) }
    }

    suspend fun fetchTrapReversalActive(): List<TrapReversalRunRow> {
        val payload = request("/trap-reversal/active", "GET")
        return parseTrapReversalRuns(payload.optJSONArray("runs") ?: JSONArray())
    }

    suspend fun fetchTrapReversalLevels(symbol: String): TrapReversalLevels {
        val payload = request("/trap-reversal/levels/${java.net.URLEncoder.encode(symbol.uppercase(), "UTF-8")}", "GET")
        return parseTrapReversalLevels(payload)
    }

    suspend fun startTrapReversal(symbol: String, riskAmount: Double) {
        request("/trap-reversal/start", "POST", JSONObject().put("symbol", symbol.uppercase()).put("risk_amount", riskAmount))
    }

    suspend fun stopTrapReversal(symbol: String) {
        request("/trap-reversal/stop", "POST", JSONObject().put("symbol", symbol.uppercase()))
    }

    suspend fun fetchTrendPilotActive(): List<TrendPilotRunRow> {
        val payload = request("/trend-pilot/active", "GET")
        return parseTrendPilotRuns(payload.optJSONArray("runs") ?: JSONArray())
    }

    suspend fun fetchTrendPilotHistoryList(): List<TrendPilotHistoryRow> {
        val payload = request("/trend-pilot/runs?limit=20", "GET")
        return parseTrendPilotHistoryRows(payload.optJSONArray("runs") ?: JSONArray())
    }

    suspend fun fetchTrendPilotHistoryDetail(runId: String): JSONObject =
        request("/trend-pilot/history/${java.net.URLEncoder.encode(runId, "UTF-8")}", "GET")

    suspend fun startTrendPilot(symbol: String, quantity: Double, accountIds: List<String>) {
        val body = JSONObject()
            .put("symbol", symbol.uppercase())
            .put("quantity", quantity)
            .put("account_ids", JSONArray(accountIds))
        val payload = request("/trend-pilot/start", "POST", body)
        val started = payload.optInt("started_count", payload.optJSONArray("runs")?.length() ?: 0)
        if (started <= 0) {
            val errors = payload.optJSONArray("errors")
            val message = errors?.optJSONObject(0)?.optString("error").orEmpty().ifBlank { "Trend Pilot could not be started." }
            throw IllegalStateException(message)
        }
    }

    suspend fun stopTrendPilot(symbol: String, accountIds: List<String>) {
        request(
            "/trend-pilot/stop",
            "POST",
            JSONObject()
                .put("symbol", symbol.uppercase())
                .put("close_position", true)
                .put("account_ids", JSONArray(accountIds)),
        )
    }

    suspend fun fetchTrendPilotBacktests(cursor: String? = null): TrendPilotBacktestPage {
        val path = buildString {
            append("/trend-pilot/backtests?limit=20")
            if (!cursor.isNullOrBlank()) {
                append("&cursor=")
                append(java.net.URLEncoder.encode(cursor, "UTF-8"))
            }
        }
        val payload = request(path, "GET")
        val pageInfo = payload.optJSONObject("page_info")
        return TrendPilotBacktestPage(
            results = parseTrendPilotBacktests(payload.optJSONArray("results") ?: JSONArray()),
            hasNextPage = pageInfo?.optBoolean("has_next_page") == true,
            endCursor = pageInfo?.optString("end_cursor")?.takeIf { it.isNotBlank() },
        )
    }

    suspend fun fetchTrendPilotBacktestDetail(resultId: String): JSONObject =
        request("/trend-pilot/backtest/${java.net.URLEncoder.encode(resultId, "UTF-8")}", "GET")

    suspend fun runTrendPilotBacktest(symbol: String, quantity: Double, fromDate: String, toDate: String) {
        request(
            "/trend-pilot/backtest",
            "POST",
            JSONObject()
                .put("symbol", symbol.uppercase())
                .put("quantity", quantity)
                .put("from_date", fromDate)
                .put("to_date", toDate),
        )
    }

    suspend fun deleteTrendPilotBacktest(resultId: String) {
        request("/trend-pilot/backtest/${java.net.URLEncoder.encode(resultId, "UTF-8")}", "DELETE")
    }

    suspend fun fetchTrendPilotBacktestSettings(): JSONObject =
        request("/trend-pilot/backtest/settings", "GET")

    suspend fun saveTrendPilotBacktestSettings(
        partialAtPct: Double,
        partialQtyPct: Double,
        moveSlToBreakeven: Boolean,
    ) {
        request(
            "/trend-pilot/backtest/settings",
            "PUT",
            JSONObject()
                .put("partial_at_pct", partialAtPct)
                .put("partial_qty_pct", partialQtyPct)
                .put("move_sl_to_breakeven", moveSlToBreakeven),
        )
    }

    private suspend fun bootstrap() {
        val prefs = getApplication<Application>().hostDataStore.data.first()
        val token = prefs[tokenKey].orEmpty()
        val appearance = AppAppearance.fromRaw(prefs[appearanceKey])
        configureHost()
        _state.update {
            it.copy(
                bootLoading = true,
                message = "Connecting securely...",
                error = "",
                appearance = appearance
            )
        }
        if (!pingApi()) {
            _state.update {
                it.copy(
                    bootStatus = BootStatus.HostRequired,
                    bootLoading = false,
                    error = "SignalBridge Cloud is unavailable right now. Retry when the service is available again."
                )
            }
            return
        }
        if (token.isBlank()) {
            _state.update { it.copy(bootStatus = BootStatus.AuthRequired, bootLoading = false, message = "Ready to sign in.") }
            return
        }
        _state.update { it.copy(token = token, bootStatus = BootStatus.BiometricRequired, bootLoading = false, message = "Unlock saved login.") }
    }

    fun syncDashboard(showIndicator: Boolean = true) {
        viewModelScope.launch { refreshDashboardInternal(showIndicator) }
    }

    private suspend fun refreshDashboardInternal(showIndicator: Boolean = true) {
        val token = _state.value.token
        if (token.isBlank()) return
        if (showIndicator) {
            _state.update { it.copy(dashboardSyncing = true, syncMessage = "Syncing dashboard...", error = "") }
        }
        try {
            coroutineScope {
                val meDeferred = async { request("/auth/me", "GET") }
                val watchDeferred = async { requestArray("/watchlist") }
                val plansDeferred = async { requestArray("/trade-planner/plans") }
                val me = meDeferred.await()
                val watchlistRows = watchDeferred.await()
                val plans = plansDeferred.await()
                _state.update {
                    it.copy(
                        bootStatus = BootStatus.Ready,
                        bootLoading = false,
                        dashboardSyncing = false,
                        syncMessage = "",
                        fullName = me.optString("full_name", me.optString("username")),
                        username = me.optString("username"),
                        selectedMarket = me.optString("selected_market", "INTERNATIONAL"),
                        selectedAccountId = me.optString("selected_account_id"),
                        accounts = parseAccounts(me.optJSONArray("accounts")),
                        watchlist = parseWatchlist(watchlistRows),
                        priceDigits = it.priceDigits + parseWatchlistPriceDigits(watchlistRows),
                        plans = parsePlans(plans)
                    )
                }
            }
            connectLiveSocket()
            loadStrategySnapshots()
        } catch (exc: Exception) {
            if (isAuthFailure(exc)) {
                requireLogin("Saved login expired. Please login again.")
                return
            }
            _state.update {
                it.copy(
                    bootLoading = false,
                    dashboardSyncing = false,
                    syncMessage = "",
                    error = formatRequestError(exc)
                )
            }
        }
    }

    private fun loadStrategySnapshots() {
        viewModelScope.launch {
            try {
                val gold = async { request("/gold-strategy", "GET") }.await()
                val continuationFailure = async { request("/continuation-failure", "GET") }.await()
                _state.update {
                    it.copy(
                        goldStrategy = parseGoldStrategy(gold),
                        continuationFailure = parseContinuationFailure(continuationFailure),
                    )
                }
            } catch (_: Exception) {
                // Strategy endpoints can be slow; core dashboard should still work.
            }
        }
    }

    private fun formatRequestError(exc: Exception): String {
        return when (exc) {
            is SocketTimeoutException -> "SignalBridge Cloud is taking too long to respond. Gold strategy sync can still take a moment; retry shortly."
            is ConnectException -> "SignalBridge Cloud is unavailable right now. Please try again shortly."
            else -> {
                val message = exc.message.orEmpty()
                when {
                    "timeout" in message.lowercase() -> "SignalBridge Cloud is taking too long to respond. Retry when the service is ready."
                    "failed to connect" in message.lowercase() -> "SignalBridge Cloud is unavailable right now. Please try again shortly."
                    else -> message.ifBlank { "Could not load dashboard" }
                }
            }
        }
    }

    private suspend fun requireLogin(message: String) {
        reconnectJob?.cancel()
        socketGeneration += 1
        liveSocket?.cancel()
        getApplication<Application>().hostDataStore.edit { it.remove(tokenKey) }
        _state.update {
            it.copy(
                token = "",
                bootStatus = BootStatus.AuthRequired,
                bootLoading = false,
                dashboardSyncing = false,
                message = message,
                error = message,
                liveStatus = "DISCONNECTED"
            )
        }
    }

    private fun isAuthFailure(exc: Exception): Boolean {
        val message = exc.message.orEmpty().lowercase()
        return "401" in message || "invalid token" in message || "session expired" in message || "user not found" in message
    }

    private suspend fun runAction(message: String, block: suspend () -> Unit) {
        val onDashboard = _state.value.bootStatus == BootStatus.Ready
        if (onDashboard) {
            _state.update { it.copy(actionBusy = true, actionMessage = message, error = "") }
        } else {
            _state.update { it.copy(bootLoading = true, message = message, error = "") }
        }
        try {
            block()
            _state.update {
                it.copy(
                    bootLoading = false,
                    actionBusy = false,
                    actionMessage = "",
                    message = if (onDashboard) it.message else "Done"
                )
            }
        } catch (exc: Exception) {
            _state.update {
                it.copy(
                    bootLoading = false,
                    actionBusy = false,
                    actionMessage = "",
                    error = formatRequestError(exc)
                )
            }
        }
    }

    private fun configureHost() {
        _state.update {
            it.copy(
                apiBase = AppConfig.directApiBase,
                wsBase = AppConfig.directApiBase.replaceFirst("https://", "wss://").replaceFirst("http://", "ws://")
            )
        }
    }

    private suspend fun pingApi(): Boolean = withContext(Dispatchers.IO) {
        val apiBase = _state.value.apiBase
        if (apiBase.isBlank()) return@withContext false
        try {
            val request = Request.Builder().url("$apiBase/health").get().build()
            client.newCall(request).execute().use { it.isSuccessful }
        } catch (_: Exception) {
            false
        }
    }

    private suspend fun requestArray(path: String): JSONArray = request(path, "GET").optJSONArray("__array") ?: JSONArray()

    private suspend fun request(path: String, method: String, body: JSONObject? = null): JSONObject = withContext(Dispatchers.IO) {
        val token = _state.value.token
        val builder = Request.Builder().url("${_state.value.apiBase}$path")
        if (token.isNotBlank()) builder.addHeader("Authorization", "Bearer $token")
        when (method.uppercase()) {
            "POST", "PATCH", "PUT" -> builder.method(method.uppercase(), (body ?: JSONObject()).toString().toRequestBody(jsonMediaType))
            "DELETE" -> builder.delete()
            else -> builder.get()
        }
        val response = client.newCall(builder.build()).execute()
        val text = response.body?.string().orEmpty()
        if (!response.isSuccessful) {
            val detail = runCatching { JSONObject(text).opt("detail")?.toString() }.getOrNull()
            val message = "HTTP ${response.code}: ${detail ?: response.message}"
            throw IOException(message)
        }
        if (text.trim().startsWith("[")) JSONObject().put("__array", JSONArray(text)) else JSONObject(text.ifBlank { "{}" })
    }

    private fun connectLiveSocket() {
        val token = _state.value.token
        val wsBase = _state.value.wsBase
        if (token.isBlank() || wsBase.isBlank()) return
        reconnectJob?.cancel()
        liveHeartbeatJob?.cancel()
        liveStaleWatchdogJob?.cancel()
        socketGeneration += 1
        val generation = socketGeneration
        liveSocket?.cancel()
        subscribedLiveSymbols = emptySet()
        _state.update { it.copy(liveStatus = "CONNECTING") }
        val request = Request.Builder().url("$wsBase/ws/live?token=$token").build()
        liveSocket = client.newWebSocket(
            request,
            object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    if (generation != socketGeneration) return
                    reconnectAttempts = 0
                    lastLiveDataAt = System.currentTimeMillis()
                    webSocket.send("ready")
                    startLiveHeartbeat(webSocket, generation)
                    startLiveStaleWatchdog(generation)
                    _state.update { it.copy(liveStatus = "CONNECTED") }
                    maybeSubscribeLiveSymbols(webSocket, _state.value)
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    if (generation != socketGeneration) return
                    runCatching {
                        val payload = JSONObject(text)
                        if (payload.optString("type").equals("ping", ignoreCase = true)) {
                            webSocket.send(JSONObject().put("type", "pong").toString())
                            return@runCatching
                        }
                        if (payload.optString("type").equals("pong", ignoreCase = true)) {
                            return@runCatching
                        }
                        val socketError = payload.optString("error")
                        if (socketError.contains("Invalid token", ignoreCase = true) || socketError.contains("Session expired", ignoreCase = true)) {
                            viewModelScope.launch { requireLogin("Saved login expired. Please login again.") }
                            return@runCatching
                        }
                        if (snapshotHasFreshPrices(payload)) {
                            lastLiveDataAt = System.currentTimeMillis()
                        }
                        val prices = parsePrices(payload.optJSONObject("prices") ?: payload.optJSONObject("livePrices"))
                        val incomingDigits = parsePriceDigitsFromPrices(payload.optJSONObject("prices") ?: payload.optJSONObject("livePrices")) +
                            parsePriceDigitsFromWatchlist(payload.optJSONArray("watchlist"))
                        val orders = payload.optJSONArray("orders")?.let { normalizeLiveOrders(parseOrders(it)) }
                        val goldStrategy = payload.optJSONObject("gold_strategy")?.let { parseGoldStrategy(it) }
                        val continuationFailure = payload.optJSONObject("continuation_failure")?.let { parseContinuationFailure(it) }
                        payload.optJSONArray("notifications")?.let {
                            handleStrategyNotifications(parseNotifications(it))
                        }
                        _state.update {
                            it.copy(
                                prices = if (prices.isNotEmpty()) it.prices + prices else it.prices,
                                priceDigits = if (incomingDigits.isNotEmpty()) it.priceDigits + incomingDigits else it.priceDigits,
                                orders = orders ?: it.orders,
                                goldStrategy = goldStrategy ?: it.goldStrategy,
                                continuationFailure = continuationFailure ?: it.continuationFailure,
                                liveStatus = "CONNECTED"
                            )
                        }
                        maybeSubscribeLiveSymbols(webSocket, _state.value)
                    }
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    if (generation != socketGeneration) return
                    liveHeartbeatJob?.cancel()
                    liveStaleWatchdogJob?.cancel()
                    _state.update { it.copy(liveStatus = "DISCONNECTED") }
                    scheduleLiveReconnect(generation)
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    if (generation != socketGeneration) return
                    liveHeartbeatJob?.cancel()
                    liveStaleWatchdogJob?.cancel()
                    _state.update { it.copy(liveStatus = "DISCONNECTED") }
                    scheduleLiveReconnect(generation)
                }
            }
        )
    }

    private fun startLiveHeartbeat(webSocket: WebSocket, generation: Int) {
        liveHeartbeatJob?.cancel()
        liveHeartbeatJob = viewModelScope.launch {
            while (generation == socketGeneration) {
                delay(20_000)
                if (generation != socketGeneration) return@launch
                runCatching {
                    webSocket.send(JSONObject().put("type", "ping").toString())
                }
            }
        }
    }

    private fun startLiveStaleWatchdog(generation: Int) {
        liveStaleWatchdogJob?.cancel()
        liveStaleWatchdogJob = viewModelScope.launch {
            while (generation == socketGeneration) {
                delay(10_000)
                if (generation != socketGeneration) return@launch
                if (_state.value.liveStatus != "CONNECTED") continue
                if (System.currentTimeMillis() - lastLiveDataAt > liveStaleMs) {
                    liveSocket?.cancel()
                }
            }
        }
    }

    private fun snapshotHasFreshPrices(payload: JSONObject, staleMs: Long = liveStaleMs): Boolean {
        val now = System.currentTimeMillis()
        fun freshTime(raw: String?): Boolean {
            if (raw.isNullOrBlank()) return false
            val parsed = runCatching { Instant.parse(raw).toEpochMilli() }.getOrNull() ?: return false
            return now - parsed < staleMs
        }
        payload.optJSONObject("prices")?.let { prices ->
            val keys = prices.keys()
            while (keys.hasNext()) {
                val tick = prices.optJSONObject(keys.next()) ?: continue
                if (freshTime(tick.optString("time"))) return true
            }
        }
        payload.optJSONArray("watchlist")?.let { watchlist ->
            for (index in 0 until watchlist.length()) {
                val item = watchlist.optJSONObject(index) ?: continue
                if (freshTime(item.optString("time"))) return true
            }
        }
        return false
    }

    private fun liveSymbolsForState(state: AppState): Set<String> {
        val watchSymbols = state.watchlist.map { it.symbol.uppercase() }
        val goldSymbol = state.goldStrategy?.config?.symbol?.uppercase()?.takeIf { it.isNotBlank() }
        val cfSymbols = state.continuationFailure?.running?.map { it.symbol.uppercase() }.orEmpty()
        return (watchSymbols + listOfNotNull(goldSymbol) + cfSymbols).filter { it.isNotBlank() }.toSet()
    }

    private fun maybeSubscribeLiveSymbols(webSocket: WebSocket, state: AppState) {
        val symbols = liveSymbolsForState(state)
        if (symbols.isEmpty() || symbols == subscribedLiveSymbols) return
        subscribedLiveSymbols = symbols
        webSocket.send(JSONObject().put("type", "subscribe_symbols").put("symbols", JSONArray(symbols.toList())).toString())
    }

    private fun scheduleLiveReconnect(generation: Int) {
        val current = _state.value
        if (generation != socketGeneration || current.token.isBlank() || current.bootStatus != BootStatus.Ready) return
        if (reconnectJob?.isActive == true) return
        val delayMs = min(30_000L, 1_000L * (1L shl reconnectAttempts.coerceAtMost(5)))
        reconnectAttempts += 1
        _state.update { it.copy(liveStatus = "RECONNECTING") }
        reconnectJob = viewModelScope.launch {
            delay(delayMs)
            if (generation == socketGeneration && _state.value.token.isNotBlank()) {
                connectLiveSocket()
            }
        }
    }

    private fun handleStrategyNotifications(notifications: List<NotificationRow>) {
        val strategyNotifications = notifications.filter { it.category in setOf("gold_strategy", "strategy", "continuation_failure") }
        if (!strategyNotificationsPrimed) {
            seenStrategyNotificationIds.addAll(strategyNotifications.map { it.id })
            strategyNotificationsPrimed = true
            return
        }
        strategyNotifications
            .filter { seenStrategyNotificationIds.add(it.id) }
            .asReversed()
            .forEach { showStrategyNotification(it) }
    }

    private fun showStrategyNotification(notification: NotificationRow) {
        val context = getApplication<Application>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            return
        }
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(context, 0, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            android.app.Notification.Builder(context, strategyNotificationChannelId)
        } else {
            android.app.Notification.Builder(context)
        }
        val title = "${notification.symbol} strategy ${plainStatus(notification.status)}"
        val systemNotification = builder
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(notification.activity)
            .setStyle(android.app.Notification.BigTextStyle().bigText(notification.activity))
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .build()
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(notification.id.hashCode(), systemNotification)
    }

}

private fun parseAccounts(array: JSONArray?): List<AccountRow> = buildList {
    if (array == null) return@buildList
    for (index in 0 until array.length()) {
        val item = array.optJSONObject(index) ?: continue
        add(
            AccountRow(
                id = item.optString("id"),
                name = item.optString("account_name", "Account"),
                number = item.optString("account_id"),
                risk = item.optDouble("risk_amount", 0.0),
                equityBalance = item.optNullableDouble("equity_balance"),
                availableMargin = item.optNullableDouble("available_margin"),
                currencyCode = item.optString("currency_code", "USD").ifBlank { "USD" },
                brokerScopeKey = item.optString("broker_scope_key").takeIf { it.isNotBlank() },
                marketType = item.optString("market_type").takeIf { it.isNotBlank() },
                brokerType = item.optString("broker_type").takeIf { it.isNotBlank() },
                brokerServer = item.optString("broker_server").takeIf { it.isNotBlank() },
            )
        )
    }
}

private fun parseWatchlist(rows: JSONArray): List<WatchRow> = buildList {
    for (index in 0 until rows.length()) {
        val item = rows.optJSONObject(index) ?: continue
        add(WatchRow(item.optString("symbol"), item.optNullableDouble("price")))
    }
}

private fun parseWatchlistPriceDigits(rows: JSONArray): Map<String, Int> = buildMap {
    for (index in 0 until rows.length()) {
        val item = rows.optJSONObject(index) ?: continue
        priceDigitEntry(item)?.let { (key, digits) -> put(key, digits) }
    }
}

private fun parsePriceDigitsFromPrices(obj: JSONObject?): Map<String, Int> = buildMap {
    if (obj == null) return@buildMap
    obj.keys().forEach { symbol ->
        val row = obj.optJSONObject(symbol) ?: return@forEach
        priceDigitEntry(row, symbol)?.let { (key, digits) -> put(key, digits) }
    }
}

private fun parsePriceDigitsFromWatchlist(array: JSONArray?): Map<String, Int> = buildMap {
    if (array == null) return@buildMap
    for (index in 0 until array.length()) {
        val item = array.optJSONObject(index) ?: continue
        priceDigitEntry(item)?.let { (key, digits) -> put(key, digits) }
    }
}

private fun parsePrices(obj: JSONObject?): Map<String, Double> = buildMap {
    if (obj == null) return@buildMap
    obj.keys().forEach { symbol ->
        val row = obj.optJSONObject(symbol)
        val bid = row?.optNullableDouble("bid")
        val ask = row?.optNullableDouble("ask")
        val mid = if (bid != null && ask != null) (bid + ask) / 2.0 else null
        val value = row?.optNullableDouble("price") ?: mid ?: bid ?: ask ?: obj.optNullableDouble(symbol)
        if (value != null) put(symbol.uppercase(), value)
    }
}

private fun parseOrders(array: JSONArray): List<OrderRow> = buildList {
    for (index in 0 until array.length()) {
        val item = array.optJSONObject(index) ?: continue
        val brokerInfo = item.optJSONObject("broker_info")
        add(
            OrderRow(
                id = item.optString("id"),
                accountId = item.optString("account_id"),
                symbol = item.optString("symbol"),
                side = item.optString("side"),
                status = item.optString("status"),
                orderType = item.optString("order_type", "SL"),
                entry = item.optNullableDouble("entry"),
                stopLoss = item.optNullableDouble("stop_loss"),
                target = item.optNullableDouble("target"),
                quantity = item.optNullableDouble("quantity"),
                positionQuantity = item.optNullableDouble("position_quantity"),
                unrealizedPl = item.optNullableDouble("unrealized_pl"),
                realizedPl = item.optNullableDouble("realized_pl"),
                dryRun = item.optBoolean("dry_run", false),
                failureReason = item.optString("failure_reason").takeIf { it.isNotBlank() },
                placementFallbackReason = item.optString("placement_fallback_reason").takeIf { it.isNotBlank() },
                comment = item.optString("comment").takeIf { it.isNotBlank() },
                metaPositionId = item.optString("meta_position_id").takeIf { it.isNotBlank() },
                externalSource = item.optString("external_source").takeIf { it.isNotBlank() },
                rrRatio = item.optNullableDouble("rr_ratio"),
                isOpenPosition = item.optBoolean("is_open_position", false),
                plannerPlanAccountId = item.optString("planner_plan_account_id").takeIf { it.isNotBlank() },
                brokerInfoAccountId = brokerInfo?.optString("account_id")?.takeIf { it.isNotBlank() },
                brokerInfoAccountName = brokerInfo?.optString("account_name")?.takeIf { it.isNotBlank() },
                brokerInfoAvailableMargin = brokerInfo?.optNullableDouble("available_margin"),
                createdAt = item.optString("created_at").takeIf { it.isNotBlank() },
                openedAt = item.optString("opened_at").takeIf { it.isNotBlank() },
                closedAt = item.optString("closed_at").takeIf { it.isNotBlank() },
                updatedAt = item.optString("updated_at").takeIf { it.isNotBlank() },
            )
        )
    }
}

private fun parseNotifications(array: JSONArray): List<NotificationRow> = buildList {
    for (index in 0 until array.length()) {
        val item = array.optJSONObject(index) ?: continue
        add(
            NotificationRow(
                id = item.optString("id"),
                category = item.optString("category"),
                symbol = item.optString("symbol"),
                status = item.optString("status"),
                activity = item.optString("activity"),
                failureReason = item.optString("failure_reason").takeIf { it.isNotBlank() },
                placementFallbackReason = item.optString("placement_fallback_reason").takeIf { it.isNotBlank() }
            )
        )
    }
}

private fun parsePlans(array: JSONArray): List<PlannerRow> = buildList {
    for (index in 0 until array.length()) {
        val item = array.optJSONObject(index) ?: continue
        add(
            PlannerRow(
                id = item.optString("id"),
                symbol = item.optString("symbol"),
                status = item.optString("status"),
                runtime = item.optString("runtime_status"),
                entry = item.optNullableDouble("entry_price"),
                stopLoss = item.optNullableDouble("stop_loss")
            )
        )
    }
}

private fun parseGoldStrategy(payload: JSONObject): GoldStrategyState {
    val config = payload.optJSONObject("config") ?: JSONObject()
    return GoldStrategyState(
        config = GoldConfigRow(
            symbol = config.optString("symbol", "XAUUSD"),
            running = config.optBoolean("running", false),
            triggerSource = config.optString("trigger_source", "previous_day"),
            pdHigh = config.optNullableDouble("pd_high"),
            pdLow = config.optNullableDouble("pd_low"),
            userTriggerPrice = config.optNullableDouble("user_trigger_price")
        ),
        running = parseGoldRunArray(payload.optJSONArray("running") ?: JSONArray()),
        history = parseGoldRunArray(payload.optJSONArray("history") ?: JSONArray())
    )
}

private fun parseGoldRunArray(array: JSONArray): List<GoldRunRow> = buildList {
    for (index in 0 until array.length()) {
        val item = array.optJSONObject(index) ?: continue
        add(
            GoldRunRow(
                id = item.optString("id"),
                symbol = item.optString("symbol", "XAUUSD"),
                status = item.optString("status"),
                runningPl = item.optDouble("running_pl", 0.0),
                bookedPl = item.optDouble("booked_pl", 0.0),
                quantity = item.optDouble("quantity", 0.0)
            )
        )
    }
}

private fun parseContinuationFailure(payload: JSONObject): ContinuationFailureState {
    val symbols = buildList {
        val array = payload.optJSONArray("symbols") ?: JSONArray()
        for (index in 0 until array.length()) {
            val item = array.optJSONObject(index) ?: continue
            add(
                ContinuationFailureSymbolConfig(
                    symbol = item.optString("symbol"),
                    pivotPrice = item.optNullableDouble("pivot_price"),
                )
            )
        }
    }
    return ContinuationFailureState(
        symbols = symbols,
        running = parseContinuationFailureRuns(payload.optJSONArray("running") ?: JSONArray()),
        history = parseContinuationFailureRuns(payload.optJSONArray("history") ?: JSONArray()),
    )
}

private fun parseContinuationFailureRuns(array: JSONArray): List<ContinuationFailureRunRow> = buildList {
    for (index in 0 until array.length()) {
        val item = array.optJSONObject(index) ?: continue
        val events = buildList {
            val eventArray = item.optJSONArray("events") ?: JSONArray()
            for (eventIndex in 0 until eventArray.length()) {
                val event = eventArray.optJSONObject(eventIndex) ?: continue
                add(
                    ContinuationFailureEventRow(
                        id = event.optString("id"),
                        eventType = event.optString("event_type"),
                        status = event.optString("status"),
                        message = event.optString("message"),
                        createdAt = event.optString("created_at"),
                        createdAtIst = event.optString("created_at_ist"),
                    )
                )
            }
        }
        add(
            ContinuationFailureRunRow(
                id = item.optString("id"),
                symbol = item.optString("symbol"),
                status = item.optString("status"),
                direction = item.optString("direction"),
                pivotPrice = item.optNullableDouble("pivot_price"),
                runningPl = item.optDouble("running_pl", 0.0),
                bookedPl = item.optDouble("booked_pl", 0.0),
                events = events,
            )
        )
    }
}

private fun parseOrderEvents(array: JSONArray): List<OrderEventRow> = buildList {
    for (index in 0 until array.length()) {
        val item = array.optJSONObject(index) ?: continue
        add(
            OrderEventRow(
                id = item.optString("id"),
                eventType = item.optString("event_type"),
                status = item.optString("status"),
                message = item.optString("message"),
                eventTsIst = item.optString("event_ts_ist"),
                failureReason = item.optString("failure_reason").takeIf { it.isNotBlank() },
                payloadJson = item.optString("payload_json").takeIf { it.isNotBlank() }
            )
        )
    }
}

private fun parseBrokerTradeHistory(payload: JSONObject): List<BrokerTradeHistoryRow> = buildList {
    val records = payload.optJSONArray("records") ?: JSONArray()
    for (index in 0 until records.length()) {
        val item = records.optJSONObject(index) ?: continue
        add(
            BrokerTradeHistoryRow(
                id = item.optString("id", item.optString("position_id", "$index")),
                symbol = item.optString("symbol"),
                type = item.optString("type"),
                status = item.optString("status"),
                openPrice = item.optDouble("open_price").takeIf { !item.isNull("open_price") },
                closePrice = item.optDouble("close_price").takeIf { !item.isNull("close_price") },
                profit = item.optDouble("profit"),
                netProfit = item.optDouble("net_profit"),
                isRunning = item.optBoolean("is_running")
            )
        )
    }
}

private fun currentWatchPrice(row: WatchRow, prices: Map<String, Double>): Double? = prices[row.symbol.uppercase()] ?: row.price

private fun JSONObject.optNullableDouble(key: String): Double? {
    if (!has(key) || isNull(key)) return null
    return runCatching { optDouble(key) }.getOrNull()?.takeIf { !it.isNaN() }
}

private fun JSONObject.optNullableString(key: String): String? {
    if (!has(key) || isNull(key)) return null
    return optString(key).trim().takeIf { it.isNotBlank() && !it.equals("null", ignoreCase = true) }
}

@Composable
fun SignalBridgeAndroidApp(vm: MainViewModel = viewModel()) {
    val state by vm.state.collectAsState()
    val systemDarkTheme = isSystemInDarkTheme()
    var automaticNow by remember(state.appearance) { mutableStateOf(System.currentTimeMillis()) }
    LaunchedEffect(state.appearance) {
        automaticNow = System.currentTimeMillis()
        while (state.appearance == AppAppearance.Automatic) {
            delay(60_000)
            automaticNow = System.currentTimeMillis()
        }
    }
    val selectedDarkTheme = when (state.appearance) {
        AppAppearance.System -> systemDarkTheme
        AppAppearance.Automatic -> {
            val hour = java.time.Instant.ofEpochMilli(automaticNow).atZone(java.time.ZoneId.systemDefault()).hour
            hour >= 18 || hour < 6
        }
        AppAppearance.Light -> false
        AppAppearance.Dark -> true
    }
    val darkTheme = if (state.bootStatus == BootStatus.HostRequired) systemDarkTheme else selectedDarkTheme
    AppColors.apply(if (darkTheme) darkPalette else lightPalette)
    val view = LocalView.current
    val lifecycleOwner = LocalLifecycleOwner.current
    SideEffect {
        val activity = view.context as? FragmentActivity ?: return@SideEffect
        val window = activity.window
        window.statusBarColor = AndroidColor.TRANSPARENT
        window.navigationBarColor = AppColors.surface.toArgb()
        val controller = WindowCompat.getInsetsController(window, view)
        controller.isAppearanceLightStatusBars = !darkTheme
        controller.isAppearanceLightNavigationBars = !darkTheme
    }
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                vm.onAppForegrounded()
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
        }
    }
    MaterialTheme(colorScheme = signalBridgeColors(darkTheme), typography = signalBridgeTypography()) {
        Surface(modifier = Modifier.fillMaxSize(), color = AppColors.background) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(AppColors.background)
            ) {
                when {
                    state.bootLoading || state.bootStatus == BootStatus.CheckingHost -> SessionLoaderScreen(state.message)
                    state.bootStatus == BootStatus.HostRequired -> Box(Modifier.padding(16.dp)) { DirectBackendRetryScreen(state, vm) }
                    state.bootStatus == BootStatus.BiometricRequired -> Box(Modifier.padding(16.dp)) { BiometricGateScreen(state, vm) }
                    state.bootStatus == BootStatus.AuthRequired -> Box(Modifier.padding(16.dp)) { AuthScreen(state, vm) }
                    else -> DashboardScreen(state, vm)
                }
            }
        }
    }
}

@Composable
private fun SessionLoaderScreen(message: String) {
    val transition = rememberInfiniteTransition(label = "session-loader")
    val pulse by transition.animateFloat(
        initialValue = 0.88f,
        targetValue = 1.08f,
        animationSpec = infiniteRepeatable(animation = tween(900, easing = FastOutSlowInEasing), repeatMode = RepeatMode.Reverse),
        label = "pulse"
    )
    Box(
        Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    listOf(LoaderColors.background, LoaderColors.surface, Color(0xFF1E1B4B))
                )
            ),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Box(contentAlignment = Alignment.Center, modifier = Modifier.size(112.dp)) {
                Box(
                    Modifier
                        .size((92 * pulse).dp)
                        .clip(CircleShape)
                        .background(LoaderColors.accent.copy(alpha = 0.12f))
                )
                Box(
                    Modifier
                        .size((64 * pulse).dp)
                        .clip(CircleShape)
                        .background(LoaderColors.accent.copy(alpha = 0.22f))
                )
                AppBrandMark(
                    modifier = Modifier.size(44.dp),
                    background = Brush.sweepGradient(
                        listOf(LoaderColors.accent, LoaderColors.accentGlow, LoaderColors.accent)
                    )
                )
            }
            Text("SignalBridge", color = LoaderColors.text, fontSize = 24.sp, fontWeight = FontWeight.SemiBold)
            Text(message, color = LoaderColors.muted, fontSize = 14.sp, textAlign = TextAlign.Center, modifier = Modifier.padding(horizontal = 32.dp))
        }
    }
}

@Composable
private fun DirectBackendRetryScreen(state: AppState, vm: MainViewModel) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(28.dp),
            colors = CardDefaults.cardColors(containerColor = AppColors.surface),
            elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
            border = BorderStroke(1.dp, AppColors.border)
        ) {
            Column(
                modifier = Modifier.padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Box(contentAlignment = Alignment.Center, modifier = Modifier.size(116.dp)) {
                    Box(
                        Modifier
                            .size(96.dp)
                            .clip(CircleShape)
                            .background(Brush.radialGradient(listOf(AppColors.accent.copy(alpha = 0.24f), Color.Transparent)))
                    )
                    AppBrandMark(modifier = Modifier.size(64.dp))
                }
                Text("Maintenance mode", color = AppColors.accent, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                Text(
                    "SignalBridge Cloud is temporarily unavailable",
                    color = AppColors.textPrimary,
                    fontSize = 22.sp,
                    fontWeight = FontWeight.Black,
                    textAlign = TextAlign.Center
                )
                Text(
                    "The backend is currently offline for maintenance or recovery. This app will reconnect once service is restored.",
                    color = AppColors.textPrimary.copy(alpha = 0.78f),
                    fontSize = 13.sp,
                    textAlign = TextAlign.Center
                )
                ErrorText(state.error)
                PrimaryButton("Retry connection", onClick = vm::saveHostAndConnect)
            }
        }
    }
}

@Composable
private fun BiometricGateScreen(state: AppState, vm: MainViewModel) {
    val context = LocalContext.current
    val activity = context as? FragmentActivity
    var promptRequested by remember(state.token) { mutableStateOf(false) }
    fun requestBiometric() {
        if (activity == null) {
            vm.usePasswordLogin("Biometric unlock is unavailable. Please login.")
            return
        }
        showBiometricUnlock(activity, onSuccess = vm::unlockSavedLogin, onPassword = { vm.usePasswordLogin("Please login with your password.") })
    }
    LaunchedEffect(state.token) {
        if (!promptRequested) {
            promptRequested = true
            requestBiometric()
        }
    }
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        SignalCard {
            Column(verticalArrangement = Arrangement.spacedBy(14.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                BrandHeader(subtitle = "Unlock to continue.")
                Text("Unlock saved login", color = AppColors.textPrimary, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                Text("Use device biometrics to open the MT5 platform app.", color = AppColors.textMuted, fontSize = 13.sp, textAlign = TextAlign.Center)
                ErrorText(state.error)
                PrimaryButton("Unlock", onClick = { requestBiometric() })
                TextButton(onClick = { vm.usePasswordLogin("Please login with your password.") }) {
                    Text("Use password instead")
                }
            }
        }
    }
}

private fun showBiometricUnlock(activity: FragmentActivity, onSuccess: () -> Unit, onPassword: () -> Unit) {
    val authenticators = BiometricManager.Authenticators.BIOMETRIC_STRONG or BiometricManager.Authenticators.DEVICE_CREDENTIAL
    val manager = BiometricManager.from(activity)
    if (manager.canAuthenticate(authenticators) != BiometricManager.BIOMETRIC_SUCCESS) {
        onPassword()
        return
    }
    val prompt = BiometricPrompt(
        activity,
        ContextCompat.getMainExecutor(activity),
        object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                onSuccess()
            }

            override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                if (errorCode == BiometricPrompt.ERROR_NEGATIVE_BUTTON || errorCode == BiometricPrompt.ERROR_USER_CANCELED) {
                    onPassword()
                }
            }
        }
    )
    val promptInfo = BiometricPrompt.PromptInfo.Builder()
        .setTitle("Unlock MT5 Platform")
        .setSubtitle("Authenticate to use your saved login")
        .setAllowedAuthenticators(authenticators)
        .build()
    prompt.authenticate(promptInfo)
}

@Composable
private fun AuthScreen(state: AppState, vm: MainViewModel) {
    var register by remember { mutableStateOf(false) }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var fullName by remember { mutableStateOf("") }
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        SignalCard {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    AppBrandMark(modifier = Modifier.size(56.dp))
                    BrandHeader(subtitle = "Sign in to continue.")
                }
                if (register) {
                    OutlinedTextField(fullName, { fullName = it }, Modifier.fillMaxWidth(), label = { Text("Full name") }, singleLine = true)
                }
                OutlinedTextField(username, { username = it }, Modifier.fillMaxWidth(), label = { Text("Username") }, singleLine = true)
                OutlinedTextField(
                    password,
                    { password = it },
                    Modifier.fillMaxWidth(),
                    label = { Text("Password") },
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true
                )
                ErrorText(state.error)
                PrimaryButton(if (register) "Create account" else "Login", onClick = {
                    vm.login(username, password, register, fullName)
                })
                Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                    TextButton(onClick = { register = !register }) {
                        Text(if (register) "Use existing login" else "Register")
                    }
                }
            }
        }
    }
}

@Composable
private fun AppBrandMark(modifier: Modifier = Modifier, background: Brush? = null) {
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(18.dp))
            .background(
                background ?: Brush.linearGradient(
                    listOf(Color(0xFF0F172A), Color(0xFF312E81), Color(0xFF0284C7))
                )
            )
            .border(1.dp, Color.White.copy(alpha = 0.18f), RoundedCornerShape(18.dp))
            .padding(7.dp),
        contentAlignment = Alignment.Center
    ) {
        Image(
            painter = painterResource(id = R.drawable.ic_launcher_foreground),
            contentDescription = "SignalBridge app icon",
            modifier = Modifier.fillMaxSize()
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DashboardScreen(state: AppState, vm: MainViewModel) {
    if (state.showTradeSheet) {
        val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
        ModalBottomSheet(onDismissRequest = vm::closeTradeSheet, sheetState = sheetState, containerColor = AppColors.surface) {
            TradeOrderSheet(state, vm)
        }
    }
    if (state.showOrderEditSheet && state.orderEditTarget != null) {
        val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
        ModalBottomSheet(onDismissRequest = vm::closeOrderEditSheet, sheetState = sheetState, containerColor = AppColors.surface) {
            OrderEditSheet(state.orderEditTarget!!, vm)
        }
    }
    val pages = AppPage.entries
    val pagerState = rememberPagerState(
        initialPage = pages.indexOf(state.page).coerceAtLeast(0),
        pageCount = { pages.size }
    )
    LaunchedEffect(state.page) {
        val targetPage = pages.indexOf(state.page).coerceAtLeast(0)
        if (pagerState.currentPage != targetPage) {
            pagerState.animateScrollToPage(targetPage)
        }
    }
    LaunchedEffect(pagerState) {
        snapshotFlow { pagerState.settledPage }
            .distinctUntilChanged()
            .collect { pageIndex ->
                pages.getOrNull(pageIndex)?.let { page ->
                    if (page != state.page) vm.changePage(page)
                }
            }
    }
    Scaffold(
        containerColor = AppColors.background,
        topBar = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(AppColors.surface)
                    .statusBarsPadding()
            ) {
                if (state.dashboardSyncing || state.actionBusy) {
                    LinearProgressIndicator(
                        modifier = Modifier.fillMaxWidth(),
                        color = AppColors.accent,
                        trackColor = AppColors.accentSoft
                    )
                    Text(
                        if (state.actionBusy) state.actionMessage else state.syncMessage,
                        color = AppColors.textSecondary,
                        fontSize = 11.sp,
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(AppColors.surfaceMuted)
                            .padding(horizontal = 16.dp, vertical = 6.dp)
                    )
                }
                DashboardTopBar(state, vm)
            }
        },
        bottomBar = {
            DashboardBottomBar(
                selected = state.page,
                onSelect = vm::changePage
            )
        }
    ) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp)
        ) {
            if (state.error.isNotBlank()) {
                ErrorBanner(state.error)
                Spacer(Modifier.height(8.dp))
            }
            HorizontalPager(
                state = pagerState,
                modifier = Modifier.fillMaxSize()
            ) { pageIndex ->
                LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                    contentPadding = PaddingValues(top = 8.dp, bottom = 24.dp),
                    modifier = Modifier.fillMaxSize()
                ) {
                    item {
                        when (pages[pageIndex]) {
                            AppPage.Watchlist -> WatchlistScreen(state, vm)
                            AppPage.Trading -> TradingScreen(state, vm)
                            AppPage.Positions -> PositionsScreen(state, vm)
                            AppPage.Strategies -> StrategiesScreen(state, vm)
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DashboardTopBar(state: AppState, vm: MainViewModel) {
    var menuOpen by remember { mutableStateOf(false) }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        AppBrandMark(modifier = Modifier.size(46.dp))
        Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(
                state.fullName.ifBlank { state.username },
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Text(
                "SignalBridge",
                style = MaterialTheme.typography.bodySmall,
                color = AppColors.textSecondary
            )
        }
        Row(
            modifier = Modifier
                .clip(RoundedCornerShape(999.dp))
                .background(if (state.liveStatus == "CONNECTED") AppColors.successSoft else AppColors.surfaceMuted)
                .padding(horizontal = 10.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            StatusDot(state.liveStatus == "CONNECTED")
            Text(
                if (state.liveStatus == "CONNECTED") "Live" else state.liveStatus.lowercase().replaceFirstChar { it.uppercase() },
                style = MaterialTheme.typography.labelSmall,
                color = if (state.liveStatus == "CONNECTED") AppColors.success else AppColors.textMuted
            )
        }
        Box {
            TextButton(
                onClick = { menuOpen = true },
                modifier = Modifier
                    .clip(RoundedCornerShape(999.dp))
                    .background(AppColors.accentSoft)
            ) {
                Text("Menu", color = AppColors.accent, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            }
            DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                DropdownMenuItem(text = { Text("Refresh") }, onClick = { menuOpen = false; vm.refresh() })
                AppAppearance.entries.forEach { appearance ->
                    DropdownMenuItem(
                        text = {
                            Text(if (state.appearance == appearance) "\u2713 ${appearance.label}" else appearance.label)
                        },
                        onClick = {
                            menuOpen = false
                            vm.setAppearance(appearance)
                        }
                    )
                }
                DropdownMenuItem(text = { Text("Logout") }, onClick = { menuOpen = false; vm.logout() })
            }
        }
    }
}

@Composable
private fun StatusDot(connected: Boolean) {
    Box(
        Modifier
            .size(10.dp)
            .clip(CircleShape)
            .background(if (connected) AppColors.success else AppColors.textMuted)
    )
}

@Composable
private fun DashboardBottomBar(selected: AppPage, onSelect: (AppPage) -> Unit) {
    NavigationBar(containerColor = AppColors.surface, tonalElevation = 0.dp) {
        AppPage.entries.forEach { page ->
            NavigationBarItem(
                selected = page == selected,
                onClick = { onSelect(page) },
                icon = {
                    Icon(
                        imageVector = page.navigationIcon(page == selected),
                        contentDescription = page.label,
                        modifier = Modifier.size(22.dp)
                    )
                },
                label = { Text(page.label, fontSize = 11.sp, maxLines = 1) },
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = AppColors.accent,
                    selectedTextColor = AppColors.accent,
                    unselectedIconColor = AppColors.textMuted,
                    unselectedTextColor = AppColors.textMuted,
                    indicatorColor = AppColors.accentSoft
                )
            )
        }
    }
}

@Composable
private fun ErrorBanner(text: String) {
    Text(
        text,
        color = AppColors.danger,
        fontSize = 13.sp,
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(AppColors.dangerSoft)
            .padding(horizontal = 12.dp, vertical = 10.dp)
    )
}

@Composable
private fun ScreenHeader(title: String, subtitle: String, actionLabel: String? = null, onAction: (() -> Unit)? = null) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleLarge, color = AppColors.textPrimary, fontWeight = FontWeight.SemiBold)
            if (subtitle.isNotBlank()) {
                Text(subtitle, style = MaterialTheme.typography.bodySmall, color = AppColors.textSecondary, modifier = Modifier.padding(top = 2.dp))
            }
        }
        if (actionLabel != null && onAction != null) {
            TextButton(onClick = onAction) {
                Text(actionLabel, color = AppColors.accent, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
            }
        }
    }
}

@Composable
private fun SummaryStrip(state: AppState, vm: MainViewModel) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
        MetricPill("P/L", formatMoney(state.runningPl), state.runningPl >= 0, Modifier.weight(1f), vm::openPositionsFromSummary)
        MetricPill("Orders", state.orders.size.toString(), true, Modifier.weight(1f), vm::openOrderHistoryFromSummary)
    }
}

@Composable
private fun WatchlistScreen(state: AppState, vm: MainViewModel) {
    var expandedWatchSymbol by remember { mutableStateOf("") }
    var showAddSymbol by remember { mutableStateOf(false) }
    var previousWatchPrices by remember { mutableStateOf<Map<String, Double>>(emptyMap()) }
    var watchDirections by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    LaunchedEffect(state.prices, state.watchlist) {
        val latestPrices = state.watchlist.mapNotNull { row ->
            currentWatchPrice(row, state.prices)?.let { row.symbol.uppercase() to it }
        }.toMap()
        val nextDirections = latestPrices.mapValues { (symbol, price) ->
            val previous = previousWatchPrices[symbol]
            when {
                previous == null -> watchDirections[symbol] ?: "flat"
                price > previous -> "up"
                price < previous -> "down"
                else -> watchDirections[symbol] ?: "flat"
            }
        }
        if (latestPrices.isNotEmpty()) {
            previousWatchPrices = latestPrices
            watchDirections = nextDirections
        }
    }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        ScreenHeader("Watchlist", "Live symbols from your platform", if (showAddSymbol) "Done" else "+ Add", {
            showAddSymbol = !showAddSymbol
        })
        SummaryStrip(state, vm)
        if (showAddSymbol) {
            CompactInlineForm("Symbol", "XAUUSD", onSubmit = {
                vm.addWatchSymbol(it)
                showAddSymbol = false
            })
        }
        if (state.watchlist.isEmpty()) {
            EmptyText(if (state.dashboardSyncing) "Loading watchlist..." else "No symbols yet. Tap + Add to subscribe.")
        }
        state.watchlist.forEach { row ->
            val normalizedSymbol = row.symbol.uppercase()
            val livePrice = currentWatchPrice(row, state.prices)
            val direction = watchDirections[normalizedSymbol] ?: "flat"
            val expanded = expandedWatchSymbol == normalizedSymbol
            DataCard {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(12.dp))
                            .clickable { expandedWatchSymbol = if (expanded) "" else normalizedSymbol }
                            .padding(vertical = 2.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(modifier = Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                            InstrumentBadge(normalizedSymbol)
                            Column {
                                Text(normalizedSymbol, fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary, fontSize = 15.sp)
                                Text(symbolSubtitle(normalizedSymbol), color = AppColors.textSecondary, fontSize = 11.sp)
                            }
                        }
                        PriceMovement(price = livePrice, direction = direction, symbol = normalizedSymbol, priceDigits = state.priceDigits, modifier = Modifier.width(108.dp))
                    }
                    if (expanded) {
                        HorizontalDivider(color = AppColors.border)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                            SecondaryButton("Trade", Modifier.weight(1f)) { vm.openTrade(normalizedSymbol) }
                            TextButton(onClick = { vm.removeWatchSymbol(normalizedSymbol) }) {
                                Text("Remove", color = AppColors.danger, fontSize = 12.sp)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun TradingScreen(state: AppState, vm: MainViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        ScreenHeader("Trade", "Place manual orders on your MT5 account", "+ New order", vm::showTradeForm)
        SummaryStrip(state, vm)
        DataCard {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Quick actions", fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary, fontSize = 14.sp)
                Text("Open a new order sheet or trade directly from Watchlist.", color = AppColors.textSecondary, fontSize = 12.sp)
                PrimaryButton("New order", onClick = vm::showTradeForm)
            }
        }
        if (state.orders.isNotEmpty()) {
            Text("Recent activity", style = MaterialTheme.typography.labelLarge, color = AppColors.textSecondary)
            state.orders.take(3).forEach { order ->
                DataCard {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Column {
                            Text("${order.symbol} ${order.side}", fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary, fontSize = 14.sp)
                            Text(plainStatus(order.status), color = AppColors.textSecondary, fontSize = 12.sp)
                        }
                        Text(formatMoney(order.unrealizedPl ?: 0.0), color = if ((order.unrealizedPl ?: 0.0) >= 0) AppColors.success else AppColors.danger, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }
    }
}

@Composable
private fun TradeOrderSheet(state: AppState, vm: MainViewModel) {
    var symbol by remember(state.tradeDraftSymbol, state.showTradeSheet) { mutableStateOf(state.tradeDraftSymbol) }
    var orderType by remember { mutableStateOf("SL") }
    var side by remember { mutableStateOf("BUY") }
    var entry by remember { mutableStateOf("") }
    var stopLoss by remember { mutableStateOf("") }
    var target by remember { mutableStateOf("") }
    var retryableOrder by remember { mutableStateOf(true) }
    var automaticTradeManagement by remember { mutableStateOf(true) }
    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 20.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Text("New order", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        Text("Defaults match the web trading ticket.", style = MaterialTheme.typography.bodySmall, color = AppColors.textSecondary)
        OutlinedTextField(symbol, { symbol = it.uppercase() }, Modifier.fillMaxWidth(), label = { Text("Symbol") }, singleLine = true)
        ChipRow(listOf("MARKET", "LIMIT", "SL"), orderType) { orderType = it }
        ChipRow(listOf("BUY", "SELL"), side) { side = it }
        OutlinedTextField(entry, { entry = it }, Modifier.fillMaxWidth(), label = { Text("Entry") }, singleLine = true, enabled = orderType != "MARKET")
        OutlinedTextField(stopLoss, { stopLoss = it }, Modifier.fillMaxWidth(), label = { Text("Stop loss") }, singleLine = true)
        OutlinedTextField(target, { target = it }, Modifier.fillMaxWidth(), label = { Text("Target (optional)") }, singleLine = true)
        CompactToggle("Automatic trade management", "Book 50% at 4R; exit remainder at target.", automaticTradeManagement) { automaticTradeManagement = it }
        if (orderType == "LIMIT" || orderType == "SL") {
            CompactToggle("Retryable order", "Re-place once as SL after a clean stop hit.", retryableOrder) { retryableOrder = it }
        }
        PrimaryButton("Place order", onClick = {
            vm.placeOrder(symbol, orderType, side, entry, stopLoss, target, retryableOrder, automaticTradeManagement)
        })
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
private fun OrderEditSheet(order: OrderRow, vm: MainViewModel) {
    var entry by remember(order.id) { mutableStateOf(order.entry?.toString().orEmpty()) }
    var stopLoss by remember(order.id) { mutableStateOf(order.stopLoss?.toString().orEmpty()) }
    var target by remember(order.id) { mutableStateOf(order.target?.toString().orEmpty()) }
    var quantity by remember(order.id) { mutableStateOf(formatQty(order.quantity)) }
    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 20.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Text("Edit pending order", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        Text("${order.symbol} ${order.side} · ${order.orderType}", style = MaterialTheme.typography.bodySmall, color = AppColors.textSecondary)
        Text(
            "Changing quantity cancels the broker order and places a new one. Other changes update the pending order at the broker when quantity stays the same.",
            style = MaterialTheme.typography.bodySmall,
            color = AppColors.textSecondary
        )
        OutlinedTextField(entry, { entry = it }, Modifier.fillMaxWidth(), label = { Text("Entry") }, singleLine = true, enabled = order.orderType.uppercase() != "MARKET")
        OutlinedTextField(stopLoss, { stopLoss = it }, Modifier.fillMaxWidth(), label = { Text("Stop loss") }, singleLine = true)
        OutlinedTextField(target, { target = it }, Modifier.fillMaxWidth(), label = { Text("Target (optional)") }, singleLine = true)
        OutlinedTextField(quantity, { quantity = it }, Modifier.fillMaxWidth(), label = { Text("Quantity") }, singleLine = true)
        PrimaryButton("Save changes", onClick = { vm.modifyOrder(order, entry, stopLoss, target, quantity) })
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
private fun CompactToggle(title: String, subtitle: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    Row(verticalAlignment = Alignment.Top, modifier = Modifier.fillMaxWidth()) {
        Checkbox(checked = checked, onCheckedChange = onCheckedChange)
        Column(Modifier.padding(top = 8.dp)) {
            Text(title, fontWeight = FontWeight.Medium, color = AppColors.textPrimary, fontSize = 13.sp)
            Text(subtitle, color = AppColors.textSecondary, fontSize = 11.sp)
        }
    }
}

@Composable
private fun CompactInlineForm(label: String, placeholder: String, onSubmit: (String) -> Unit) {
    var value by remember { mutableStateOf("") }
    DataCard {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(value, { value = it.uppercase() }, Modifier.weight(1f), label = { Text(label) }, placeholder = { Text(placeholder) }, singleLine = true)
            PrimaryButton("Add", onClick = { if (value.isNotBlank()) { onSubmit(value); value = "" } }, modifier = Modifier)
        }
    }
}

@Composable
private fun StrategiesScreen(state: AppState, vm: MainViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (state.strategySection == null) {
            ScreenHeader("Strategies", "FSM engines, Trend Pilot, and trade planner")
            StrategyTile("FSM Engines", "Trap reversal automation", false) { vm.openStrategy(StrategySection.TrapReversal) }
            StrategyTile("Trend Pilot", "H4 breakout engine", false) { vm.openStrategy(StrategySection.TrendPilot) }
            StrategyTile("Trade Planner", "${state.plans.count { it.status == "RUNNING" }} running plans", false) { vm.openStrategy(StrategySection.Planner) }
        } else {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = vm::closeStrategy) { Text("← Back", color = AppColors.accent) }
                Text(
                    when (state.strategySection) {
                        StrategySection.TrapReversal -> "FSM Engines"
                        StrategySection.TrendPilot -> "Trend Pilot"
                        StrategySection.Planner -> "Trade Planner"
                    },
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold
                )
            }
            when (state.strategySection) {
                StrategySection.TrapReversal -> TrapReversalScreen(state, vm)
                StrategySection.TrendPilot -> TrendPilotScreen(state, vm)
                StrategySection.Planner -> PlannerScreen(state, vm)
            }
        }
    }
}

@Composable
private fun StrategyTile(title: String, subtitle: String, active: Boolean, onClick: () -> Unit) {
    DataCard {
        Row(
            Modifier
                .fillMaxWidth()
                .clickable(onClick = onClick)
                .padding(vertical = 4.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(Modifier.weight(1f)) {
                Text(title, fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary, fontSize = 15.sp)
                Text(subtitle, color = AppColors.textSecondary, fontSize = 12.sp)
            }
            if (active) StatusPill("RUNNING", true) else Text("›", color = AppColors.textMuted, fontSize = 22.sp)
        }
    }
}

@Composable
private fun PlPill(amount: Double) {
    val positive = amount >= 0
    val bg = if (positive) AppColors.successSoft else AppColors.dangerSoft
    val fg = if (positive) AppColors.success else AppColors.danger
    Text(
        formatMoney(amount),
        color = fg,
        fontSize = 12.sp,
        fontWeight = FontWeight.Bold,
        modifier = Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(bg)
            .padding(horizontal = 10.dp, vertical = 5.dp)
    )
}

@Composable
private fun AccountFilter(accounts: List<AccountRow>, selected: String, onSelect: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    val label = if (selected == "ALL") "All" else accounts.find { it.id == selected }?.name ?: "Account"
    Box {
        OutlinedButton(
            onClick = { expanded = true },
            shape = RoundedCornerShape(999.dp),
            contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp),
            border = BorderStroke(1.dp, AppColors.border)
        ) {
            Text(label, color = AppColors.textSecondary, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            accounts.forEach { account ->
                DropdownMenuItem(
                    text = { Text(account.name) },
                    onClick = {
                        onSelect(account.id)
                        expanded = false
                    }
                )
            }
            DropdownMenuItem(
                text = { Text("All") },
                onClick = {
                    onSelect("ALL")
                    expanded = false
                }
            )
        }
    }
}

@Composable
private fun ClosedStatusFilter(selected: String, onSelect: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    val options = listOf("CLOSED", "CANCELLED", "FAILED", "ALL")
    Box {
        OutlinedButton(
            onClick = { expanded = true },
            shape = RoundedCornerShape(999.dp),
            contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp),
            border = BorderStroke(1.dp, AppColors.border)
        ) {
            Text(plainStatus(selected), color = AppColors.textSecondary, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { option ->
                DropdownMenuItem(
                    text = { Text(plainStatus(option)) },
                    onClick = {
                        onSelect(option)
                        expanded = false
                    }
                )
            }
        }
    }
}

private fun isClosedOrderStatus(status: String): Boolean =
    status.uppercase() in setOf("CLOSED", "CANCELLED", "FAILED")

private fun orderAccountId(row: OrderRow): String =
    row.accountId.takeIf { it.isNotBlank() } ?: row.plannerPlanAccountId.orEmpty()

private fun isPresentNumber(value: Double?): Boolean =
    value != null && value.isFinite() && value > 0

private fun normalizeLiveOrders(rows: List<OrderRow>): List<OrderRow> {
    data class SeqEntry(val type: String, val row: OrderRow? = null, val key: String? = null)
    val positionGroups = linkedMapOf<String, MutableList<OrderRow>>()
    val sequence = mutableListOf<SeqEntry>()
    rows.forEach { row ->
        val status = row.status.uppercase()
        val positionId = row.metaPositionId?.trim().orEmpty()
        if (positionId.isBlank() || status !in setOf("FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED")) {
            sequence.add(SeqEntry("row", row = row))
            return@forEach
        }
        val key = "${orderAccountId(row)}:$positionId"
        if (!positionGroups.containsKey(key)) {
            positionGroups[key] = mutableListOf()
            sequence.add(SeqEntry("position", key = key))
        }
        positionGroups.getValue(key).add(row)
    }
    fun pickPrimary(duplicates: List<OrderRow>): OrderRow {
        val tracked = duplicates.filter { it.externalSource?.uppercase() != "BROKER_IMPORT" }
        val pool = if (tracked.isNotEmpty()) tracked else duplicates
        return pool.minByOrNull { it.id }!!
    }
    return sequence.map { entry ->
        if (entry.type == "row") return@map entry.row!!
        val duplicates = positionGroups[entry.key]!!
        if (duplicates.size == 1) return@map duplicates[0]
        val primary = pickPrimary(duplicates)
        var merged = primary
        if (!isPresentNumber(merged.target)) {
            merged = merged.copy(target = duplicates.firstOrNull { isPresentNumber(it.target) }?.target)
        }
        if (!isPresentNumber(merged.stopLoss)) {
            merged = merged.copy(stopLoss = duplicates.firstOrNull { isPresentNumber(it.stopLoss) }?.stopLoss)
        }
        if (!isPresentNumber(merged.entry)) {
            merged = merged.copy(entry = duplicates.firstOrNull { isPresentNumber(it.entry) }?.entry)
        }
        if (!isPresentNumber(merged.rrRatio)) {
            merged = merged.copy(rrRatio = duplicates.firstOrNull { isPresentNumber(it.rrRatio) }?.rrRatio)
        }
        if (merged.side.isBlank()) {
            merged = merged.copy(side = duplicates.firstOrNull { it.side.isNotBlank() }?.side ?: merged.side)
        }
        merged
    }
}

private fun parseAppTimestamp(value: String?): Long {
    if (value.isNullOrBlank()) return 0L
    return runCatching {
        val normalized = if (value.endsWith("Z", ignoreCase = true)) value else "${value}Z"
        java.time.Instant.parse(normalized).toEpochMilli()
    }.getOrElse {
        runCatching { java.time.OffsetDateTime.parse(value).toInstant().toEpochMilli() }.getOrDefault(0L)
    }
}

private fun compareOrders(left: OrderRow, right: OrderRow, active: Boolean): Int {
    val statusPriority = mapOf(
        "POSITION_OPEN" to 0,
        "PARTIALLY_CLOSED" to 1,
        "FILLED" to 2,
        "PENDING" to 3,
        "PLACEMENT_PENDING" to 4,
    )
    val leftStatus = left.status.uppercase()
    val rightStatus = right.status.uppercase()
    val leftPriority = statusPriority[leftStatus] ?: 99
    val rightPriority = statusPriority[rightStatus] ?: 99
    if (leftPriority != rightPriority) return leftPriority - rightPriority
    fun timestampValue(row: OrderRow): Long {
        val candidates = if (active) listOf(row.openedAt, row.createdAt) else listOf(row.closedAt, row.updatedAt, row.createdAt)
        return candidates.mapNotNull { parseAppTimestamp(it).takeIf { ts -> ts > 0 } }.maxOrNull() ?: 0L
    }
    val leftTime = timestampValue(left)
    val rightTime = timestampValue(right)
    if (leftTime != rightTime) return (rightTime - leftTime).compareTo(0)
    return left.id.compareTo(right.id)
}

private data class OrderedRows(val active: List<OrderRow>, val closed: List<OrderRow>)

private fun orderActiveAndClosed(rows: List<OrderRow>): OrderedRows {
    val active = rows.filter { !isClosedOrderStatus(it.status) }.sortedWith { left, right -> compareOrders(left, right, true) }
    val closed = rows.filter { isClosedOrderStatus(it.status) }.sortedWith { left, right -> compareOrders(left, right, false) }
    return OrderedRows(active, closed)
}

private fun brokerLabel(row: OrderRow): String =
    row.brokerInfoAccountName?.takeIf { it.isNotBlank() } ?: "Unknown broker"

private fun accountGroupLabel(row: OrderRow, accounts: List<AccountRow>): String {
    val accountId = orderAccountId(row)
    val account = accounts.find { it.id == accountId }
    val name = account?.name ?: brokerLabel(row)
    val balance = account?.availableMargin ?: row.brokerInfoAvailableMargin
    return if (balance != null) "$name · Bal ${formatMoney(balance)}" else name
}

private fun groupRowsByAccount(rows: List<OrderRow>, accounts: List<AccountRow>): List<Triple<String, String, List<OrderRow>>> {
    data class Group(val key: String, val label: String, val sortName: String, val rows: MutableList<OrderRow>)
    val groups = linkedMapOf<String, Group>()
    rows.forEach { row ->
        val accountId = orderAccountId(row)
        val key = accountId.ifBlank { "label:${brokerLabel(row)}" }
        if (!groups.containsKey(key)) {
            val account = accounts.find { it.id == accountId }
            groups[key] = Group(
                key = key,
                label = accountGroupLabel(row, accounts),
                sortName = (account?.name ?: brokerLabel(row)).lowercase(),
                rows = mutableListOf(),
            )
        }
        groups.getValue(key).rows.add(row)
    }
    fun sortRows(left: OrderRow, right: OrderRow): Int {
        val symbolCompare = left.symbol.compareTo(right.symbol)
        if (symbolCompare != 0) return symbolCompare
        return left.id.compareTo(right.id)
    }
    return groups.values
        .sortedWith(compareBy<Group> { it.sortName }.thenBy { it.key })
        .map { group -> Triple(group.key, group.label, group.rows.sortedWith(::sortRows)) }
}

private fun inferPositionDirection(row: OrderRow): String {
    val entry = row.entry
    val sl = row.stopLoss
    val tp = row.target
    if (entry != null && entry > 0 && isPresentNumber(sl)) {
        return if (sl!! < entry) "LONG" else "SHORT"
    }
    if (entry != null && entry > 0 && isPresentNumber(tp)) {
        return if (tp!! > entry) "LONG" else "SHORT"
    }
    return when (row.side.uppercase()) {
        "BUY" -> "LONG"
        "SELL" -> "SHORT"
        else -> ""
    }
}

private fun buildDerivedOrders(positionRows: List<OrderRow>, pendingRows: List<OrderRow>): Pair<List<OrdersTabRow>, List<OrdersTabRow>> {
    val open = mutableListOf<OrdersTabRow>()
    val stop = mutableListOf<OrdersTabRow>()
    pendingRows.forEach { row ->
        val tabRow = OrdersTabRow(
            id = row.id,
            symbol = row.symbol,
            side = row.side,
            orderTypeLabel = ordersTabTypeLabel(row.orderType),
            price = row.entry,
            quantity = row.quantity,
            status = row.status,
            editable = true,
            sourceOrder = row,
            accountId = orderAccountId(row),
            brokerInfoAccountName = row.brokerInfoAccountName,
        )
        if (row.orderType.uppercase() == "LIMIT") open.add(tabRow) else stop.add(tabRow)
    }
    positionRows.forEach { row ->
        val direction = inferPositionDirection(row)
        val exitSide = when (direction) {
            "LONG" -> "SELL"
            "SHORT" -> "BUY"
            else -> ""
        }
        val quantity = row.positionQuantity ?: row.quantity
        if (isPresentNumber(row.target)) {
            open.add(
                OrdersTabRow(
                    id = "${row.id}-tp",
                    symbol = row.symbol,
                    side = exitSide,
                    orderTypeLabel = "Take Profit",
                    price = row.target,
                    quantity = quantity,
                    status = "WORKING",
                    derived = true,
                    accountId = orderAccountId(row),
                    brokerInfoAccountName = row.brokerInfoAccountName,
                )
            )
        }
        if (isPresentNumber(row.stopLoss)) {
            stop.add(
                OrdersTabRow(
                    id = "${row.id}-sl",
                    symbol = row.symbol,
                    side = exitSide,
                    orderTypeLabel = "Stop Loss",
                    price = row.stopLoss,
                    quantity = quantity,
                    status = "WORKING",
                    derived = true,
                    accountId = orderAccountId(row),
                    brokerInfoAccountName = row.brokerInfoAccountName,
                )
            )
        }
    }
    return open to stop
}

private fun ordersTabTypeLabel(orderType: String): String = when (orderType.uppercase()) {
    "LIMIT" -> "Limit"
    "SL" -> "Stop"
    "MARKET" -> "Market"
    else -> plainStatus(orderType)
}

private fun groupOrdersTabRows(rows: List<OrdersTabRow>, accounts: List<AccountRow>): List<Pair<String, List<OrdersTabRow>>> {
    data class Group(val label: String, val sortName: String, val rows: MutableList<OrdersTabRow>)
    val groups = linkedMapOf<String, Group>()
    rows.forEach { row ->
        val key = row.accountId.ifBlank { "label:${row.brokerInfoAccountName ?: "Unknown broker"}" }
        if (!groups.containsKey(key)) {
            val account = accounts.find { it.id == row.accountId }
            val name = account?.name ?: row.brokerInfoAccountName ?: "Unknown broker"
            val balance = account?.availableMargin
            val label = if (balance != null) "$name · Bal ${formatMoney(balance)}" else name
            groups[key] = Group(label = label, sortName = name.lowercase(), rows = mutableListOf())
        }
        groups.getValue(key).rows.add(row)
    }
    return groups.values
        .sortedWith(compareBy<Group> { it.sortName }.thenBy { it.label })
        .map { it.label to it.rows.sortedWith(compareBy({ it.symbol }, { it.id })) }
}

private fun closedQuantitySubtext(order: OrderRow): String? {
    val total = order.quantity
    val remaining = order.positionQuantity
    if (total == null || remaining == null) return null
    val closed = total - remaining
    if (closed <= 0.0001) return null
    return "Closed ${formatQty(closed)}"
}

@Composable
private fun PositionsSectionHeader(title: String, count: Int, trailing: (@Composable () -> Unit)? = null) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(top = 4.dp, bottom = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(title.uppercase(), color = AppColors.textMuted, fontSize = 12.sp, fontWeight = FontWeight.Bold, letterSpacing = 0.8.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            trailing?.invoke()
            Text(
                count.toString(),
                color = AppColors.skyDeep,
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier
                    .clip(RoundedCornerShape(999.dp))
                    .background(AppColors.skySoft)
                    .padding(horizontal = 8.dp, vertical = 4.dp)
            )
        }
    }
}

@Composable
private fun PositionOrderCard(
    order: OrderRow,
    expanded: Boolean,
    showClosedPl: Boolean,
    onToggleExpanded: () -> Unit,
    vm: MainViewModel,
    priceDigits: Map<String, Int>
) {
    DataCard {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .clickable { onToggleExpanded() }
                    .padding(vertical = 2.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("${order.symbol} ${order.side}", fontWeight = FontWeight.Bold, color = AppColors.textPrimary)
                StatusPill(order.status, order.status in setOf("POSITION_OPEN", "FILLED", "PARTIALLY_CLOSED"))
            }
            Text(
                "Entry ${formatPrice(order.entry, order.symbol, priceDigits, listOf(order.stopLoss, order.target))}  SL ${formatPrice(order.stopLoss, order.symbol, priceDigits, listOf(order.entry, order.target))}  Target ${formatPrice(order.target, order.symbol, priceDigits, listOf(order.entry, order.stopLoss))}",
                color = AppColors.textSecondary
            )
            Text("Qty ${formatQty(order.positionQuantity ?: order.quantity)}", color = AppColors.textSecondary)
            closedQuantitySubtext(order)?.let { closedText ->
                Text(closedText, color = AppColors.textMuted, fontSize = 11.sp)
            }
            order.failureReason?.let { reason ->
                Text("Failure: $reason", color = AppColors.danger, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            }
            order.placementFallbackReason?.let { reason ->
                Text("Placement: $reason", color = AppColors.trap, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            }
            if (showClosedPl) {
                Text(
                    formatMoney(order.realizedPl ?: 0.0),
                    color = if ((order.realizedPl ?: 0.0) >= 0) AppColors.success else AppColors.danger,
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 13.sp
                )
            } else {
                Text("Running P/L ${formatMoney(order.unrealizedPl ?: 0.0)}  Booked P/L ${formatMoney(order.realizedPl ?: 0.0)}", color = AppColors.textSecondary, fontSize = 12.sp)
            }
            if (order.dryRun) Text("Forward Test - No Broker Order", color = AppColors.trap, fontWeight = FontWeight.SemiBold)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (order.status.uppercase() in setOf("PLACEMENT_PENDING", "PENDING")) {
                    OutlinedButton(onClick = { vm.openOrderEditor(order) }, shape = RoundedCornerShape(12.dp)) { Text("Edit") }
                    OutlinedButton(onClick = { vm.cancelOrder(order.id) }, shape = RoundedCornerShape(12.dp)) { Text("Cancel") }
                }
                if (order.status in setOf("FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED")) {
                    PrimaryButton("Full Exit", onClick = { vm.closeOrder(order) })
                }
            }
            if (expanded) {
                OrderActivityTimeline(orderId = order.id, vm = vm)
            } else {
                Text("Tap row to view trade activity", color = AppColors.textMuted, fontSize = 11.sp)
            }
        }
    }
}

@Composable
private fun BrokerClosedTradeCard(row: BrokerTradeHistoryRow, priceDigits: Map<String, Int>) {
    DataCard {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("${row.symbol} ${row.type}", fontWeight = FontWeight.Bold, color = AppColors.textPrimary)
                StatusPill("CLOSED", false)
            }
            Text("Open ${formatPrice(row.openPrice, row.symbol, priceDigits, listOf(row.closePrice))}  Close ${formatPrice(row.closePrice, row.symbol, priceDigits, listOf(row.openPrice))}", color = AppColors.textSecondary, fontSize = 12.sp)
            Text(
                formatMoney(row.netProfit),
                color = if (row.netProfit >= 0) AppColors.success else AppColors.danger,
                fontWeight = FontWeight.SemiBold,
                fontSize = 13.sp
            )
        }
    }
}

@Composable
private fun OrdersTabCard(row: OrdersTabRow, vm: MainViewModel, priceDigits: Map<String, Int>) {
    DataCard {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("${row.symbol} ${row.side}", fontWeight = FontWeight.Bold, color = AppColors.textPrimary)
                StatusPill(if (row.derived) "WORKING" else row.status, row.derived || row.status.uppercase() in setOf("PENDING", "PLACEMENT_PENDING"))
            }
            Text(
                "${row.orderTypeLabel}  Price ${formatPrice(row.price, row.symbol, priceDigits)}  Qty ${formatQty(row.quantity)}",
                color = AppColors.textSecondary,
                fontSize = 12.sp
            )
            when {
                row.editable && row.sourceOrder != null -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { vm.openOrderEditor(row.sourceOrder) }, shape = RoundedCornerShape(12.dp)) { Text("Edit") }
                    OutlinedButton(onClick = { vm.cancelOrder(row.sourceOrder.id) }, shape = RoundedCornerShape(12.dp)) { Text("Cancel") }
                }
                row.derived -> Text("From position", color = AppColors.textMuted, fontSize = 11.sp)
            }
        }
    }
}

@Composable
private fun AccountGroupHeader(label: String, count: Int) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(top = 4.dp, bottom = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(label.uppercase(), color = AppColors.textSecondary, fontSize = 11.sp, fontWeight = FontWeight.Bold)
        Text(
            count.toString(),
            color = AppColors.textMuted,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier
                .clip(RoundedCornerShape(999.dp))
                .background(AppColors.surfaceMuted)
                .padding(horizontal = 8.dp, vertical = 2.dp)
        )
    }
}

@Composable
private fun PositionsScreen(state: AppState, vm: MainViewModel) {
    var expandedOrderId by remember { mutableStateOf("") }
    var closedStatusFilter by remember { mutableStateOf("CLOSED") }
    var closedAccountFilter by remember(state.selectedAccountId, state.accounts) {
        mutableStateOf(
            state.selectedAccountId.takeIf { it.isNotBlank() }
                ?: state.accounts.firstOrNull()?.id.orEmpty()
        )
    }
    var historyAccountFilter by remember(state.selectedAccountId, state.accounts) {
        mutableStateOf(
            state.selectedAccountId.takeIf { it.isNotBlank() }
                ?: state.accounts.firstOrNull()?.id.orEmpty()
        )
    }
    var historyTypeFilter by remember { mutableStateOf("all") }
    var historyPage by remember { mutableStateOf(1) }
    var closedBrokerRows by remember { mutableStateOf<List<BrokerTradeHistoryRow>>(emptyList()) }
    var closedBrokerLoading by remember { mutableStateOf(false) }
    var closedBrokerError by remember { mutableStateOf("") }
    var brokerHistory by remember { mutableStateOf<List<BrokerTradeHistoryRow>>(emptyList()) }
    var historyLoading by remember { mutableStateOf(false) }
    var historyError by remember { mutableStateOf("") }
    LaunchedEffect(state.selectedAccountId, state.accounts, closedAccountFilter) {
        if (closedAccountFilter == "ALL") return@LaunchedEffect
        if (closedAccountFilter.isNotBlank() && state.accounts.any { it.id == closedAccountFilter }) return@LaunchedEffect
        closedAccountFilter = state.selectedAccountId.takeIf { it.isNotBlank() }
            ?: state.accounts.firstOrNull()?.id.orEmpty()
    }
    val ordered = remember(state.orders) { orderActiveAndClosed(state.orders) }
    val positionRows = remember(ordered.active) {
        ordered.active.filter { it.status.uppercase() in setOf("FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED") }
    }
    val pendingRows = remember(ordered.active) {
        ordered.active.filter { it.status.uppercase() in setOf("PENDING", "PLACEMENT_PENDING") }
    }
    val (openOrders, stopOrders) = remember(positionRows, pendingRows) { buildDerivedOrders(positionRows, pendingRows) }
    val positionGroups = remember(positionRows, state.accounts) { groupRowsByAccount(positionRows, state.accounts) }
    val openOrderGroups = remember(openOrders, state.accounts) { groupOrdersTabRows(openOrders, state.accounts) }
    val stopOrderGroups = remember(stopOrders, state.accounts) { groupOrdersTabRows(stopOrders, state.accounts) }
    val accountFilteredClosedOrders = remember(ordered.closed, closedAccountFilter) {
        if (closedAccountFilter == "ALL" || closedAccountFilter.isBlank()) ordered.closed
        else ordered.closed.filter { orderAccountId(it) == closedAccountFilter }
    }
    val usesBrokerClosedToday = closedStatusFilter == "CLOSED" || closedStatusFilter == "ALL"
    val localNonBrokerClosedOrders = remember(accountFilteredClosedOrders, closedStatusFilter) {
        if (closedStatusFilter == "CLOSED") emptyList()
        else accountFilteredClosedOrders.filter { order ->
            val status = order.status.uppercase()
            status != "CLOSED" && (closedStatusFilter == "ALL" || status == closedStatusFilter.uppercase())
        }
    }
    val closedDisplayCount = remember(closedBrokerRows, localNonBrokerClosedOrders, usesBrokerClosedToday) {
        (if (usesBrokerClosedToday) closedBrokerRows.size else 0) + localNonBrokerClosedOrders.size
    }
    val totalClosedPl = remember(closedBrokerRows, localNonBrokerClosedOrders, usesBrokerClosedToday) {
        val brokerPl = if (usesBrokerClosedToday) closedBrokerRows.sumOf { it.netProfit } else 0.0
        val localPl = localNonBrokerClosedOrders.sumOf { it.realizedPl ?: 0.0 }
        brokerPl + localPl
    }
    LaunchedEffect(state.positionsTab, closedAccountFilter, closedStatusFilter, state.accounts) {
        if (state.positionsTab != "Positions" || !usesBrokerClosedToday) return@LaunchedEffect
        closedBrokerLoading = true
        closedBrokerError = ""
        try {
            closedBrokerRows = vm.fetchClosedTodayBrokerTrades(closedAccountFilter, state.accounts)
        } catch (exc: Exception) {
            closedBrokerRows = emptyList()
            closedBrokerError = exc.message ?: "Could not load today's closed broker trades."
        } finally {
            closedBrokerLoading = false
        }
    }
    LaunchedEffect(state.positionsTab, historyAccountFilter, historyTypeFilter, historyPage) {
        if (state.positionsTab != "History") return@LaunchedEffect
        historyLoading = true
        historyError = ""
        try {
            brokerHistory = vm.fetchBrokerTradeHistory(
                accountId = if (historyAccountFilter == "ALL") null else historyAccountFilter,
                page = historyPage,
                pageSize = 20,
                type = historyTypeFilter,
            )
        } catch (exc: Exception) {
            brokerHistory = emptyList()
            historyError = exc.message ?: "Could not load broker trade history."
        } finally {
            historyLoading = false
        }
    }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        ScreenHeader("Positions", "Open positions, working orders, and history")
        SummaryStrip(state, vm)
        ChipRow(listOf("Positions", "Orders", "History"), state.positionsTab, vm::setPositionsTab)
        when (state.positionsTab) {
            "Orders" -> {
                PositionsSectionHeader("Open Orders", openOrders.size)
                if (openOrders.isEmpty()) {
                    EmptyText("No open orders for today yet.")
                } else {
                    openOrderGroups.forEach { (label, rows) ->
                        AccountGroupHeader(label, rows.size)
                        rows.forEach { row -> OrdersTabCard(row, vm, state.priceDigits) }
                    }
                }
                PositionsSectionHeader("Stop Orders", stopOrders.size)
                if (stopOrders.isEmpty()) {
                    EmptyText("No stop orders for today yet.")
                } else {
                    stopOrderGroups.forEach { (label, rows) ->
                        AccountGroupHeader(label, rows.size)
                        rows.forEach { row -> OrdersTabCard(row, vm, state.priceDigits) }
                    }
                }
            }
            "History" -> {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    AccountFilter(state.accounts, historyAccountFilter, onSelect = { historyAccountFilter = it; historyPage = 1 })
                    var historyTypeExpanded by remember { mutableStateOf(false) }
                    Box {
                        OutlinedButton(onClick = { historyTypeExpanded = true }, shape = RoundedCornerShape(999.dp), contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp), border = BorderStroke(1.dp, AppColors.border)) {
                            Text(historyTypeFilter.uppercase(), color = AppColors.textSecondary, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                        }
                        DropdownMenu(expanded = historyTypeExpanded, onDismissRequest = { historyTypeExpanded = false }) {
                            listOf("all", "closed", "open").forEach { option ->
                                DropdownMenuItem(text = { Text(option.uppercase()) }, onClick = { historyTypeFilter = option; historyPage = 1; historyTypeExpanded = false })
                            }
                        }
                    }
                }
                when {
                    historyLoading -> EmptyText("Loading broker trade history...")
                    historyError.isNotBlank() -> EmptyText(historyError)
                    brokerHistory.isEmpty() -> EmptyText("No broker trade history found.")
                    else -> {
                        brokerHistory.forEach { row -> BrokerClosedTradeCard(row, state.priceDigits) }
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = { if (historyPage > 1) historyPage -= 1 }, enabled = historyPage > 1) { Text("Previous") }
                            Text("Page $historyPage", color = AppColors.textMuted, modifier = Modifier.padding(top = 10.dp))
                            OutlinedButton(onClick = { historyPage += 1 }, enabled = brokerHistory.size >= 20) { Text("Next") }
                        }
                    }
                }
            }
            else -> {
                PositionsSectionHeader("Open Positions", positionRows.size)
                if (positionRows.isEmpty()) {
                    EmptyText("No open positions for today yet.")
                } else {
                    positionGroups.forEach { (_, label, rows) ->
                        AccountGroupHeader(label, rows.size)
                        rows.forEach { order ->
                            PositionOrderCard(
                                order = order,
                                expanded = expandedOrderId == order.id,
                                showClosedPl = false,
                                onToggleExpanded = { expandedOrderId = if (expandedOrderId == order.id) "" else order.id },
                                vm = vm,
                                priceDigits = state.priceDigits
                            )
                        }
                    }
                }
                PositionsSectionHeader(
                    title = "Closed Today",
                    count = closedDisplayCount,
                    trailing = {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                            AccountFilter(state.accounts, closedAccountFilter, onSelect = { closedAccountFilter = it })
                            ClosedStatusFilter(closedStatusFilter, onSelect = { closedStatusFilter = it })
                            PlPill(totalClosedPl)
                        }
                    }
                )
                when {
                    closedBrokerError.isNotBlank() -> EmptyText(closedBrokerError)
                    closedBrokerLoading && usesBrokerClosedToday -> EmptyText("Loading today's closed broker trades...")
                    closedDisplayCount == 0 -> EmptyText(
                        when (closedStatusFilter) {
                            "ALL" -> "No closed trades for today yet."
                            "CLOSED" -> "No closed broker trades for today yet."
                            else -> "No ${plainStatus(closedStatusFilter).lowercase()} orders for today yet."
                        }
                    )
                    else -> {
                        if (usesBrokerClosedToday) {
                            closedBrokerRows.forEach { row -> BrokerClosedTradeCard(row, state.priceDigits) }
                        }
                        localNonBrokerClosedOrders.forEach { order ->
                            PositionOrderCard(
                                order = order,
                                expanded = expandedOrderId == order.id,
                                showClosedPl = true,
                                onToggleExpanded = { expandedOrderId = if (expandedOrderId == order.id) "" else order.id },
                                vm = vm,
                                priceDigits = state.priceDigits
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun OrderActivityTimeline(orderId: String, vm: MainViewModel) {
    var events by remember(orderId) { mutableStateOf<List<OrderEventRow>>(emptyList()) }
    var loading by remember(orderId) { mutableStateOf(true) }
    var error by remember(orderId) { mutableStateOf("") }
    LaunchedEffect(orderId) {
        loading = true
        error = ""
        try {
            events = vm.fetchOrderEvents(orderId)
        } catch (exc: Exception) {
            events = emptyList()
            error = exc.message ?: "Could not load order activity."
        } finally {
            loading = false
        }
    }
    HorizontalDivider(color = AppColors.border)
    Text("Trade Activity", color = AppColors.textMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold)
    when {
        loading -> Text("Loading activity...", color = AppColors.textMuted, fontSize = 12.sp)
        error.isNotBlank() -> Text(error, color = AppColors.danger, fontSize = 12.sp)
        events.isEmpty() -> Text("No saved activity yet.", color = AppColors.textMuted, fontSize = 12.sp)
        else -> events.forEach { event ->
            Column(
                Modifier
                    .fillMaxWidth()
                    .padding(top = 6.dp)
                    .border(1.dp, AppColors.border, RoundedCornerShape(10.dp))
                    .padding(10.dp)
            ) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(humanizeEventType(event.eventType), fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary, fontSize = 13.sp)
                    Text(event.eventTsIst.ifBlank { "-" }, color = AppColors.textMuted, fontSize = 11.sp)
                }
                Text(event.message, color = AppColors.textSecondary, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
                orderEventPriceContext(event)?.let { prices ->
                    Text("Prices: $prices", color = AppColors.textMuted, fontSize = 12.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(top = 4.dp))
                }
                orderEventFailureReason(event)?.let { reason ->
                    Text("Failure: $reason", color = AppColors.danger, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 4.dp))
                }
                if (event.status.isNotBlank()) {
                    Text("Status: ${plainStatus(event.status)}", color = AppColors.textMuted, fontSize = 11.sp, modifier = Modifier.padding(top = 2.dp))
                }
            }
        }
    }
}

@Composable
private fun PlannerScreen(state: AppState, vm: MainViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Monitor and control saved plans. Create detailed plans on web.", color = AppColors.textSecondary, fontSize = 12.sp)
        if (state.plans.isEmpty()) EmptyText("No trade plans found.")
        state.plans.forEach { plan ->
            DataCard {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(plan.symbol, fontWeight = FontWeight.Bold, color = AppColors.textPrimary)
                        StatusPill(plan.status, plan.status == "RUNNING")
                    }
                    Text("Runtime ${plan.runtime}  Entry ${formatPrice(plan.entry, plan.symbol, state.priceDigits, listOf(plan.stopLoss))}  SL ${formatPrice(plan.stopLoss, plan.symbol, state.priceDigits, listOf(plan.entry))}", color = AppColors.textSecondary)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = { vm.togglePlan(plan, plan.status != "RUNNING") }, shape = RoundedCornerShape(12.dp)) {
                            Text(if (plan.status == "RUNNING") "Deactivate" else "Run")
                        }
                        OutlinedButton(onClick = { vm.deletePlan(plan.id) }, shape = RoundedCornerShape(12.dp)) { Text("Delete") }
                    }
                }
            }
        }
    }
}

@Composable
private fun GoldScreen(state: AppState, vm: MainViewModel) {
    var activeTab by remember { mutableStateOf("Active") }
    val gold = state.goldStrategy
    if (gold == null) {
        EmptyText("GOLD strategy data is not available yet.")
        return
    }
    val activeStatuses = strategyActiveStatuses()
    val activeRuns = gold.running.filter { it.status.uppercase() in activeStatuses }
    val inactiveRuns = (gold.running.filterNot { it.status.uppercase() in activeStatuses }) + gold.history
    val displayedRuns = if (activeTab == "Active") activeRuns else inactiveRuns
    val livePrice = state.prices[gold.config.symbol.uppercase()]
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        DataCard {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Column {
                        Text(gold.config.symbol, fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary, fontSize = 15.sp)
                        Text(
                            if (gold.config.triggerSource == "user_selected") "User trigger ${formatPrice(gold.config.userTriggerPrice, gold.config.symbol, state.priceDigits)}"
                            else "PDH ${formatPrice(gold.config.pdHigh, gold.config.symbol, state.priceDigits)} · PDL ${formatPrice(gold.config.pdLow, gold.config.symbol, state.priceDigits)}",
                            color = AppColors.textSecondary,
                            fontSize = 12.sp
                        )
                    }
                    StatusPill(if (gold.config.running) "RUNNING" else "STOPPED", gold.config.running)
                }
                Text("Live ${formatPrice(livePrice, gold.config.symbol, state.priceDigits)}", color = AppColors.textSecondary, fontSize = 12.sp)
                if (gold.config.running) {
                    SecondaryButton("Stop GOLD strategy", Modifier.fillMaxWidth(), danger = true) { vm.stopGoldStrategy() }
                } else {
                    Text("Start and full configuration stay on web.", color = AppColors.textSecondary, fontSize = 12.sp)
                }
            }
        }
        ChipRow(listOf("Active", "History"), activeTab) { activeTab = it }
        if (displayedRuns.isEmpty()) EmptyText("No ${activeTab.lowercase()} GOLD strategy runs found.")
        displayedRuns.forEach { run ->
            DataCard {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(run.symbol, fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary, fontSize = 14.sp)
                        StatusPill(run.status, run.status.uppercase() in activeStatuses)
                    }
                    Text("Running ${formatMoney(run.runningPl)} · Booked ${formatMoney(run.bookedPl)} · Qty ${formatQty(run.quantity)}", color = AppColors.textSecondary, fontSize = 12.sp)
                }
            }
        }
    }
}

@Composable
private fun ContinuationFailureScreen(state: AppState, vm: MainViewModel) {
    var activeTab by remember { mutableStateOf("Running") }
    var showCreateSheet by remember { mutableStateOf(false) }
    val cf = state.continuationFailure
    if (cf == null) {
        EmptyText("Continuation Failure data is not available yet.")
        return
    }
    val activeStatuses = continuationFailureActiveStatuses()
    val runningRuns = cf.running.filter { it.status.uppercase() in activeStatuses }
    val displayedRuns = if (activeTab == "Running") runningRuns else cf.history
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            ChipRow(listOf("Running", "History"), activeTab) { activeTab = it }
            PrimaryButton("Create", onClick = { showCreateSheet = true }, modifier = Modifier)
        }
        if (displayedRuns.isEmpty()) {
            EmptyText("No ${activeTab.lowercase()} Continuation Failure runs found.")
        }
        displayedRuns.forEach { run ->
            DataCard {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Top) {
                        Column {
                            Text(run.symbol, fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary, fontSize = 15.sp)
                            Text(
                                "${run.direction} · Pivot ${formatPrice(run.pivotPrice, run.symbol, state.priceDigits)}",
                                color = AppColors.textSecondary,
                                fontSize = 12.sp
                            )
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text("Running ${formatMoney(run.runningPl)}", color = AppColors.textSecondary, fontSize = 12.sp)
                            Text("Booked ${formatMoney(run.bookedPl)}", color = AppColors.textSecondary, fontSize = 12.sp)
                        }
                    }
                    if (activeTab == "Running") {
                        SecondaryButton("Stop", danger = true, modifier = Modifier.fillMaxWidth()) {
                            vm.stopContinuationFailure(run.symbol)
                        }
                    }
                    if (run.events.isNotEmpty()) {
                        HorizontalDivider(color = AppColors.border)
                        Text("Events", color = AppColors.textMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        run.events.forEach { event ->
                            Column(
                                Modifier
                                    .fillMaxWidth()
                                    .padding(top = 6.dp)
                                    .border(1.dp, AppColors.border, RoundedCornerShape(10.dp))
                                    .padding(10.dp)
                            ) {
                                Text(
                                    event.createdAtIst.ifBlank { event.createdAt }.ifBlank { "-" },
                                    color = AppColors.textMuted,
                                    fontSize = 11.sp
                                )
                                Text(event.message, color = AppColors.textSecondary, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
                            }
                        }
                    }
                }
            }
        }
    }
    if (showCreateSheet) {
        ContinuationFailureCreateSheet(
            state = state,
            vm = vm,
            snapshot = cf,
            onDismiss = { showCreateSheet = false },
            onStarted = {
                showCreateSheet = false
                activeTab = "Running"
            }
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ContinuationFailureCreateSheet(
    state: AppState,
    vm: MainViewModel,
    snapshot: ContinuationFailureState,
    onDismiss: () -> Unit,
    onStarted: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var symbolSearch by remember { mutableStateOf("") }
    var selectedSymbol by remember { mutableStateOf("") }
    var suggestions by remember { mutableStateOf<List<String>>(emptyList()) }
    var pivotPrice by remember { mutableStateOf("") }
    var selectedIds by remember(state.selectedAccountId, state.accounts) {
        mutableStateOf(normalizeCfSelection(listOfNotNull(state.selectedAccountId.takeIf { it.isNotBlank() }), state.accounts, state.selectedAccountId))
    }
    var riskInputs by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var exitTargets by remember { mutableStateOf(listOf(Pair("", ""))) }
    var brokerSymbolInfo by remember { mutableStateOf<JSONObject?>(null) }
    val resolvedSymbol = selectedSymbol.trim().uppercase()
    val livePrice = state.prices[resolvedSymbol]
    val displaySymbol = brokerSymbolInfo?.optString("display_symbol")?.takeIf { it.isNotBlank() } ?: resolvedSymbol
    val inferredDirection = remember(pivotPrice, livePrice) {
        val pivot = pivotPrice.toDoubleOrNull()
        val price = livePrice
        if (pivot == null || pivot <= 0 || price == null) null
        else when {
            pivot > price -> "SHORT"
            pivot < price -> "LONG"
            else -> "invalid"
        }
    }
    LaunchedEffect(symbolSearch) {
        if (symbolSearch.trim().length < 1) {
            suggestions = emptyList()
            return@LaunchedEffect
        }
        delay(180)
        suggestions = runCatching { vm.suggestInstruments(symbolSearch.trim()) }.getOrDefault(emptyList())
    }
    LaunchedEffect(resolvedSymbol) {
        if (resolvedSymbol.isBlank()) {
            brokerSymbolInfo = null
            return@LaunchedEffect
        }
        brokerSymbolInfo = runCatching { vm.resolveContinuationFailureSymbol(resolvedSymbol) }.getOrNull()
    }
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState, containerColor = AppColors.surface) {
        Column(
            Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text("Create strategy", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = AppColors.textPrimary)
            OutlinedTextField(
                value = symbolSearch,
                onValueChange = { symbolSearch = it.uppercase() },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Symbol") },
                placeholder = { Text("Search instrument") },
                singleLine = true,
            )
            if (suggestions.isNotEmpty() && symbolSearch.isNotBlank()) {
                suggestions.forEach { suggestion ->
                    TextButton(onClick = {
                        selectedSymbol = suggestion.uppercase()
                        symbolSearch = suggestion.uppercase()
                        suggestions = emptyList()
                        val config = snapshot.symbols.find { it.symbol.uppercase() == selectedSymbol }
                        pivotPrice = config?.pivotPrice?.toString().orEmpty()
                    }) {
                        Text(suggestion, color = AppColors.textPrimary)
                    }
                }
            }
            if (resolvedSymbol.isNotBlank()) {
                Text(displaySymbol, fontWeight = FontWeight.Bold, fontSize = 20.sp, color = AppColors.textPrimary)
                Text("Live ${formatPrice(livePrice, resolvedSymbol, state.priceDigits)}", color = AppColors.textSecondary, fontSize = 12.sp)
            }
            OutlinedTextField(
                value = pivotPrice,
                onValueChange = { pivotPrice = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Pivot") },
                placeholder = { Text("Pivot price") },
                singleLine = true,
            )
            when (inferredDirection) {
                "SHORT", "LONG" -> Text(inferredDirection, color = AppColors.textPrimary, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                "invalid" -> Text("Pivot cannot equal market price", color = AppColors.danger, fontSize = 12.sp)
            }
            Text("Accounts", color = AppColors.textMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold)
            state.accounts.forEach { account ->
                val checked = selectedIds.contains(account.id)
                val disabled = isCfAccountDisabled(account, selectedIds, state.accounts, state.selectedAccountId)
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Checkbox(
                        checked = checked,
                        onCheckedChange = { next ->
                            val updated = if (next) selectedIds + account.id else selectedIds.filter { it != account.id }
                            selectedIds = normalizeCfSelection(updated, state.accounts, state.selectedAccountId)
                        },
                        enabled = !disabled || checked,
                    )
                    Column(Modifier.weight(1f)) {
                        Text(account.name, color = AppColors.textPrimary, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                        if (account.id == state.selectedAccountId) {
                            Text("Feed", color = AppColors.accent, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                    OutlinedTextField(
                        value = riskInputs[account.id] ?: account.risk.toString(),
                        onValueChange = { riskInputs = riskInputs + (account.id to it) },
                        modifier = Modifier.width(100.dp),
                        enabled = checked,
                        label = { Text("Risk") },
                        singleLine = true,
                    )
                }
            }
            Text("Exit targets", color = AppColors.textMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold)
            exitTargets.forEachIndexed { index, target ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(
                        value = target.first,
                        onValueChange = { value ->
                            exitTargets = exitTargets.toMutableList().also { it[index] = value to target.second }
                        },
                        modifier = Modifier.weight(1f),
                        label = { Text("Price") },
                        singleLine = true,
                    )
                    OutlinedTextField(
                        value = target.second,
                        onValueChange = { value ->
                            exitTargets = exitTargets.toMutableList().also { it[index] = target.first to value }
                        },
                        modifier = Modifier.width(100.dp),
                        label = { Text("Qty") },
                        singleLine = true,
                    )
                    if (exitTargets.size > 1) {
                        TextButton(onClick = { exitTargets = exitTargets.filterIndexed { rowIndex, _ -> rowIndex != index } }) {
                            Text("Remove", color = AppColors.danger)
                        }
                    }
                }
            }
            SecondaryButton("Add target", modifier = Modifier.fillMaxWidth()) {
                exitTargets = exitTargets + ("" to "")
            }
            val canStart = resolvedSymbol.isNotBlank() &&
                pivotPrice.isNotBlank() &&
                livePrice != null &&
                inferredDirection != null &&
                inferredDirection != "invalid"
            PrimaryButton(
                label = "Start",
                onClick = {
                    val targets = selectedIds.mapNotNull { accountId ->
                        val account = state.accounts.find { it.id == accountId } ?: return@mapNotNull null
                        val risk = (riskInputs[accountId] ?: account.risk.toString()).toDoubleOrNull() ?: account.risk
                        accountId to risk
                    }
                    val exits = exitTargets.mapNotNull { (priceText, qtyText) ->
                        val price = priceText.toDoubleOrNull() ?: return@mapNotNull null
                        price to qtyText.toDoubleOrNull()
                    }
                    vm.startContinuationFailure(
                        symbol = resolvedSymbol,
                        pivotPrice = pivotPrice.toDouble(),
                        startReferencePrice = livePrice!!,
                        targets = targets,
                        exitTargets = exits,
                    )
                    onStarted()
                },
                modifier = Modifier.fillMaxWidth(),
            )
            if (!canStart) {
                Text("Resolve symbol, pivot, and live price before starting.", color = AppColors.textMuted, fontSize = 11.sp)
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun BrandHeader(subtitle: String) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("SignalBridge", color = AppColors.textPrimary, fontSize = 28.sp, fontWeight = FontWeight.Black)
        Text(subtitle, color = AppColors.textMuted, fontSize = 14.sp)
    }
}

@Composable
private fun SignalCard(content: @Composable () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = AppColors.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 3.dp)
    ) {
        Box(Modifier.padding(16.dp)) { content() }
    }
}

@Composable
private fun appTextFieldColors() = OutlinedTextFieldDefaults.colors(
    focusedTextColor = AppColors.textPrimary,
    unfocusedTextColor = AppColors.textPrimary,
    focusedBorderColor = AppColors.accent,
    unfocusedBorderColor = AppColors.border,
    focusedContainerColor = AppColors.surfaceMuted,
    unfocusedContainerColor = AppColors.surfaceMuted,
    cursorColor = AppColors.accent,
    focusedLabelColor = AppColors.textSecondary,
    unfocusedLabelColor = AppColors.textMuted,
)

@Composable
internal fun DataCard(content: @Composable () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = AppColors.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, AppColors.border)
    ) {
        Box(Modifier.padding(14.dp)) { content() }
    }
}

@Composable
internal fun PrimaryButton(label: String, onClick: () -> Unit, modifier: Modifier = Modifier.fillMaxWidth(), enabled: Boolean = true) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.buttonColors(containerColor = AppColors.accent, contentColor = Color.White),
        contentPadding = PaddingValues(vertical = 12.dp)
    ) {
        Text(label, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
    }
}

@Composable
internal fun SecondaryButton(label: String, modifier: Modifier = Modifier, danger: Boolean = false, enabled: Boolean = true, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = if (danger) AppColors.danger else AppColors.accent),
        border = androidx.compose.foundation.BorderStroke(1.dp, if (danger) AppColors.danger.copy(alpha = 0.35f) else AppColors.border)
    ) {
        Text(label, fontWeight = FontWeight.Medium, fontSize = 13.sp)
    }
}

@Composable
private fun SectionTitle(text: String) {
    Text(text, color = AppColors.textPrimary, fontSize = 18.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 4.dp))
}

@Composable
internal fun EmptyText(text: String) {
    DataCard { Text(text, color = AppColors.textMuted) }
}

@Composable
internal fun ErrorText(text: String) {
    if (text.isNotBlank()) {
        Text(text, color = AppColors.danger, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun StatusPill(label: String, positive: Boolean) {
    val bg = if (positive) AppColors.successSoft else AppColors.warningSoft
    val fg = if (positive) AppColors.success else AppColors.warning
    Text(
        plainStatus(label),
        color = fg,
        fontSize = 11.sp,
        fontWeight = FontWeight.Bold,
        modifier = Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(bg)
            .padding(horizontal = 10.dp, vertical = 5.dp)
    )
}

private fun humanizeEventType(value: String): String = plainStatus(value)
private fun orderEventPriceContext(event: OrderEventRow): String? {
    val payloadJson = event.payloadJson?.takeIf { it.isNotBlank() } ?: return null
    val payload = try {
        JSONObject(payloadJson)
    } catch (_: Exception) {
        return null
    }
    val parts = mutableListOf<String>()
    payload.optString("side").takeIf { it.isNotBlank() }?.let { parts.add(it.uppercase()) }
    fun priceLabel(key: String, altKey: String, label: String) {
        val raw = when {
            !payload.isNull(key) -> payload.optDouble(key)
            !payload.isNull(altKey) -> payload.optDouble(altKey)
            else -> null
        } ?: return
        if (!raw.isFinite() || raw <= 0.0) return
        val text = "%.5f".format(raw).trimEnd('0').trimEnd('.')
        parts.add("$label $text")
    }
    priceLabel("entry", "price", "entry")
    priceLabel("stop_loss", "sl", "SL")
    priceLabel("target", "tp", "TP")
    val qty = when {
        !payload.isNull("quantity") -> payload.optDouble("quantity")
        !payload.isNull("volume") -> payload.optDouble("volume")
        else -> null
    }
    if (qty != null && qty.isFinite() && qty > 0.0) parts.add("qty ${qty}")
    val bid = if (!payload.isNull("bid")) payload.optDouble("bid") else null
    val ask = if (!payload.isNull("ask")) payload.optDouble("ask") else null
    if ((bid != null && bid.isFinite() && bid > 0.0) || (ask != null && ask.isFinite() && ask > 0.0)) {
        val bidText = if (bid != null && bid.isFinite() && bid > 0.0) "%.5f".format(bid).trimEnd('0').trimEnd('.') else "-"
        val askText = if (ask != null && ask.isFinite() && ask > 0.0) "%.5f".format(ask).trimEnd('0').trimEnd('.') else "-"
        parts.add("bid $bidText ask $askText")
    }
    return parts.joinToString(" · ").ifBlank { null }
}

private fun orderEventFailureReason(event: OrderEventRow): String? {
    event.failureReason?.takeIf { it.isNotBlank() }?.let { return it }
    val payloadJson = event.payloadJson?.takeIf { it.isNotBlank() } ?: return null
    return try {
        val payload = JSONObject(payloadJson)
        sequenceOf("error", "failure_reason", "reason")
            .mapNotNull { key -> payload.optString(key).takeIf { it.isNotBlank() } }
            .firstOrNull()
    } catch (_: Exception) {
        null
    }
}

private fun strategyActiveStatuses(): Set<String> = setOf(
    "WAITING_BREAK",
    "ARMED",
    "ARMED_WAIT_STRUCTURE",
    "ARMED_WAIT_SWEEP",
    "ARMED_WAIT_ENTRY",
    "ORDER_OPEN"
)

private fun continuationFailureActiveStatuses(): Set<String> = setOf(
    "WAITING_PIVOT_BREACH",
    "PIVOT_BREACHED_WAITING_SETUP",
    "ORDER_PENDING",
    "ORDER_OPEN",
)

private fun normalizeCfSelection(currentIds: List<String>, accounts: List<AccountRow>, activeAccountId: String): List<String> {
    val unique = currentIds.filter { it.isNotBlank() }.distinct()
    val activeAccount = accounts.find { it.id == activeAccountId }
    val activeScope = activeAccount?.brokerScope().orEmpty()
    // Feed may be omitted; keep only same-broker accounts and cap at two.
    return unique.filter { id ->
        val account = accounts.find { it.id == id }
        account != null && (activeScope.isBlank() || account.brokerScope() == activeScope)
    }.take(2)
}

private fun isCfAccountDisabled(account: AccountRow, selectedIds: List<String>, accounts: List<AccountRow>, activeAccountId: String): Boolean {
    val activeAccount = accounts.find { it.id == activeAccountId }
    if (activeAccount != null && account.brokerScope() != activeAccount.brokerScope()) return true
    return selectedIds.size >= 2 && !selectedIds.contains(account.id)
}

private fun plainStatus(value: String): String {
    val words = value.ifBlank { "-" }.lowercase().split("_", " ").filter { it.isNotBlank() }
    if (words.isEmpty()) return "-"
    return listOf(words.first().replaceFirstChar { it.uppercase() }).plus(words.drop(1)).joinToString(" ")
}

@Composable
private fun TinyPill(label: String, background: Color, foreground: Color, compact: Boolean = false) {
    Text(
        label,
        color = foreground,
        fontSize = if (compact) 10.sp else 11.sp,
        fontWeight = FontWeight.Bold,
        maxLines = 1,
        softWrap = false,
        overflow = TextOverflow.Ellipsis,
        modifier = Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(background)
            .padding(horizontal = if (compact) 7.dp else 9.dp, vertical = if (compact) 4.dp else 5.dp)
    )
}

@Composable
private fun MetricPill(label: String, value: String, positive: Boolean, modifier: Modifier = Modifier, onClick: (() -> Unit)? = null) {
    val fg = if (positive) AppColors.success else AppColors.danger
    Column(
        modifier
            .clip(RoundedCornerShape(12.dp))
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .background(AppColors.surface)
            .border(1.dp, AppColors.border, RoundedCornerShape(12.dp))
            .padding(horizontal = 10.dp, vertical = 8.dp)
    ) {
        Text(label.uppercase(), color = AppColors.textMuted, fontSize = 10.sp, fontWeight = FontWeight.Medium)
        Text(value, color = if (label == "Orders") AppColors.textPrimary else fg, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
    }
}

@Composable
private fun InlineForm(label: String, placeholder: String, onSubmit: (String) -> Unit) {
    var value by remember { mutableStateOf("") }
    DataCard {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                value,
                { value = it.uppercase() },
                modifier = Modifier.weight(1f),
                label = { Text(label) },
                placeholder = { Text(placeholder) },
                singleLine = true
            )
            PrimaryButton("Add", onClick = { if (value.isNotBlank()) { onSubmit(value); value = "" } }, modifier = Modifier)
        }
    }
}

@Composable
private fun ChipRow(values: List<String>, selected: String, onSelect: (String) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.horizontalScroll(rememberScrollState())) {
        values.forEach { value ->
            val active = value == selected
            Button(
                onClick = { onSelect(value) },
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (active) AppColors.accentSoft else AppColors.surfaceMuted,
                    contentColor = if (active) AppColors.accent else AppColors.textSecondary
                ),
                shape = RoundedCornerShape(999.dp),
                contentPadding = PaddingValues(horizontal = 14.dp, vertical = 6.dp),
                elevation = ButtonDefaults.buttonElevation(defaultElevation = 0.dp)
            ) {
                Text(value, fontSize = 12.sp, fontWeight = FontWeight.Medium)
            }
        }
    }
}

private fun JSONObject.optNullableInt(key: String): Int? {
    if (!has(key) || isNull(key)) return null
    return runCatching { optInt(key) }.getOrNull()
}

private fun normalizeSymbolKey(symbol: String?): String =
    symbol.orEmpty().uppercase().replace("/", "").replace("-", "")

private fun symbolPriceDigitEntries(brokerSymbol: String, requestedSymbol: String?, digits: Int): Map<String, Int> {
    val clamped = digits.coerceIn(0, 10)
    val entries = mutableMapOf<String, Int>()
    val brokerKey = normalizeSymbolKey(brokerSymbol)
    val requestedKey = normalizeSymbolKey(requestedSymbol)
    if (brokerKey.isNotBlank()) entries[brokerKey] = clamped
    if (requestedKey.isNotBlank()) entries[requestedKey] = clamped
    return entries
}

private fun priceDigitEntry(obj: JSONObject, fallbackSymbol: String? = null): Pair<String, Int>? {
    val digits = obj.optNullableInt("price_digits") ?: return null
    val symbol = obj.optString("symbol").takeIf { it.isNotBlank() } ?: fallbackSymbol
    val key = normalizeSymbolKey(symbol)
    if (key.isBlank()) return null
    return key to digits.coerceIn(0, 10)
}

private fun AppState.displayPrice(value: Double?, symbol: String? = null, vararg related: Double?): String =
    formatPrice(value, symbol, priceDigits, related.toList())

private fun formatPrice(
    value: Double?,
    symbol: String? = null,
    priceDigits: Map<String, Int> = emptyMap(),
    relatedValues: List<Double?> = emptyList(),
): String {
    if (value == null) return "-"
    val digits = resolvePriceDigits(symbol, priceDigits, relatedValues + value)
    return "%.${digits}f".format(value)
}

private fun resolvePriceDigits(symbol: String?, priceDigits: Map<String, Int>, relatedValues: List<Double?>): Int {
    val key = normalizeSymbolKey(symbol)
    priceDigits[key]?.let { return it.coerceIn(0, 10) }
    val inferred = relatedValues.mapNotNull { decimalPlaces(it) }.maxOrNull() ?: 0
    if (inferred > 0) return inferred.coerceAtMost(10)
    return fallbackPriceDigitsForSymbol(symbol)
}

private fun decimalPlaces(value: Double?): Int {
    if (value == null || value.isNaN()) return 0
    val text = "%.10f".format(value).trimEnd('0').trimEnd('.')
    val dot = text.indexOf('.')
    if (dot < 0) return 0
    return (text.length - dot - 1).coerceAtMost(10)
}

private fun fallbackPriceDigitsForSymbol(symbol: String?): Int {
    val upper = symbol.orEmpty().uppercase()
    return when {
        upper.contains("JPY") -> 3
        upper.contains("XAU") || upper.contains("GOLD") -> 2
        upper.contains("BTC") || upper.contains("ETH") || upper.contains("US30") || upper.contains("NAS") || upper.contains("SPX") -> 2
        else -> 5
    }
}
private fun formatQty(value: Double?): String = value?.let { "%.2f".format(it) } ?: "-"
internal fun formatMoney(value: Double): String = (if (value >= 0) "+" else "") + "%.2f".format(value)
private fun accountDisplayName(name: String): String = name.replace(Regex("\\s*\\([^)]*\\)\\s*$"), "").ifBlank { name }
private fun formatAccountBalance(account: AccountRow?): String? {
    val value = account?.equityBalance ?: return null
    if (!value.isFinite()) return null
    return try {
        java.text.NumberFormat.getCurrencyInstance(java.util.Locale.US).apply {
            currency = java.util.Currency.getInstance(account.currencyCode.uppercase())
        }.format(value)
    } catch (_: Exception) {
        "%.2f".format(value)
    }
}
private fun lookupAccount(accounts: List<AccountRow>, accountId: String): AccountRow? =
    accounts.firstOrNull { it.id == accountId }

@Composable
private fun InstrumentBadge(symbol: String) {
    val normalized = symbol.uppercase()
    if (normalized.length >= 6 && normalized.take(6).all { it.isLetter() }) {
        val baseFlag = currencyIconLabel(normalized.take(3))
        val quoteFlag = currencyIconLabel(normalized.substring(3, 6))
        Box(Modifier.size(38.dp)) {
            CurrencyCircle(baseFlag, Modifier.align(Alignment.TopStart))
            CurrencyCircle(quoteFlag, Modifier.align(Alignment.BottomEnd))
        }
        return
    }
    val label = when {
        normalized.startsWith("XAU") -> "Au"
        normalized.startsWith("XAG") -> "Ag"
        normalized.length >= 3 -> normalized.take(3)
        else -> normalized
    }
    Box(
        modifier = Modifier
            .size(38.dp)
            .clip(CircleShape)
            .background(Brush.linearGradient(listOf(Color(0xFF1E293B), Color(0xFF4F46E5))))
            .border(1.dp, Color(0xFFE0E7FF), CircleShape),
        contentAlignment = Alignment.Center
    ) {
        Text(label, color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Black)
    }
}

@Composable
private fun CurrencyCircle(label: String, modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .size(24.dp)
            .clip(CircleShape)
            .background(AppColors.surface)
            .border(1.dp, AppColors.border, CircleShape),
        contentAlignment = Alignment.Center
    ) {
        Text(label, fontSize = 15.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun PriceMovement(price: Double?, direction: String, symbol: String, priceDigits: Map<String, Int>, modifier: Modifier = Modifier) {
    val tone = when (direction) {
        "up" -> AppColors.success
        "down" -> AppColors.danger
        else -> AppColors.textSecondary
    }
    val arrow = when (direction) {
        "up" -> "^"
        "down" -> "v"
        else -> ""
    }
    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.End,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            formatPrice(price, symbol, priceDigits),
            color = tone,
            fontWeight = FontWeight.Black,
            textAlign = TextAlign.End,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f)
        )
        Text(
            arrow,
            color = tone,
            fontSize = 11.sp,
            fontWeight = FontWeight.Black,
            textAlign = TextAlign.Center,
            modifier = Modifier.width(14.dp)
        )
    }
}

private fun symbolSubtitle(symbol: String): String {
    val normalized = symbol.uppercase()
    if (normalized.length >= 6 && normalized.take(6).all { it.isLetter() }) {
        return "${normalized.take(3)} / ${normalized.substring(3, 6)}"
    }
    return when {
        normalized.startsWith("XAU") -> "Gold"
        normalized.startsWith("XAG") -> "Silver"
        else -> "Instrument"
    }
}

private fun currencyIconLabel(code: String): String {
    return when (code.uppercase()) {
        "USD" -> "🇺🇸"
        "EUR" -> "🇪🇺"
        "GBP" -> "🇬🇧"
        "JPY" -> "🇯🇵"
        "CHF" -> "🇨🇭"
        "CAD" -> "🇨🇦"
        "AUD" -> "🇦🇺"
        "NZD" -> "🇳🇿"
        "INR" -> "🇮🇳"
        "SGD" -> "🇸🇬"
        "HKD" -> "🇭🇰"
        "CNH", "CNY" -> "🇨🇳"
        else -> code.take(2)
    }
}

private fun signalBridgeColors(darkTheme: Boolean) = if (darkTheme) {
    darkColorScheme(
        primary = AppColors.accent,
        secondary = Color(0xFFC4B5FD),
        background = AppColors.background,
        surface = AppColors.surface,
        onSurface = AppColors.textPrimary,
        onBackground = AppColors.textPrimary
    )
} else {
    androidx.compose.material3.lightColorScheme(
        primary = AppColors.accent,
        secondary = Color(0xFF7C3AED),
        background = AppColors.background,
        surface = AppColors.surface,
        onSurface = AppColors.textPrimary,
        onBackground = AppColors.textPrimary
    )
}

private fun signalBridgeTypography() = Typography(
    titleLarge = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary),
    titleMedium = TextStyle(fontSize = 17.sp, fontWeight = FontWeight.SemiBold, color = AppColors.textPrimary),
    bodyLarge = TextStyle(fontSize = 15.sp, fontWeight = FontWeight.Normal, color = AppColors.textPrimary),
    bodyMedium = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.Normal, color = AppColors.textPrimary),
    bodySmall = TextStyle(fontSize = 12.sp, fontWeight = FontWeight.Normal, color = AppColors.textSecondary),
    labelLarge = TextStyle(fontSize = 12.sp, fontWeight = FontWeight.Medium, color = AppColors.textSecondary)
)
