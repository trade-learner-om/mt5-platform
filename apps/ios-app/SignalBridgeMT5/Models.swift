import SwiftUI

enum BootStatus {
    case checkingHost, hostRequired, biometricRequired, authRequired, ready
}

enum AppPage: String, CaseIterable, Identifiable {
    case watchlist = "Watch"
    case trading = "Trade"
    case positions = "Positions"
    case strategies = "More"

    var id: String { rawValue }

    var systemImage: String {
        switch self {
        case .watchlist: return "star"
        case .trading: return "chart.line.uptrend.xyaxis"
        case .positions: return "square.stack.3d.up"
        case .strategies: return "square.grid.2x2"
        }
    }
}

enum StrategySection {
    case trapReversal, trendPilot, planner
}

enum AppAppearance: String {
    case system, automatic, light, dark

    var label: String {
        switch self {
        case .system: return "Follow system"
        case .automatic: return "Auto 6am/6pm"
        case .light: return "Light"
        case .dark: return "Dark"
        }
    }

    func preferredColorScheme(now: Date = Date()) -> ColorScheme? {
        switch self {
        case .system:
            return nil
        case .automatic:
            let hour = Calendar.current.component(.hour, from: now)
            return (hour >= 18 || hour < 6) ? .dark : .light
        case .light:
            return .light
        case .dark:
            return .dark
        }
    }
}

struct AppState {
    var bootStatus: BootStatus = .checkingHost
    var apiBase = ""
    var wsBase = ""
    var token = ""
    var fullName = ""
    var username = ""
    var selectedMarket = "INTERNATIONAL"
    var selectedAccountId = ""
    var liveStatus = "CONNECTING"
    var bootLoading = true
    var dashboardSyncing = false
    var syncMessage = ""
    var actionBusy = false
    var actionMessage = ""
    var message = "Connecting securely..."
    var error = ""
    var appearance: AppAppearance = .system
    var page: AppPage = .watchlist
    var strategySection: StrategySection?
    var positionsTab = "Positions"
    var tradeDraftSymbol = ""
    var showTradeSheet = false
    var showOrderEditSheet = false
    var orderEditTarget: OrderRow?
    var accounts: [AccountRow] = []
    var watchlist: [WatchRow] = []
    var prices: [String: Double] = [:]
    var priceDigits: [String: Int] = [:]
    var orders: [OrderRow] = []
    var plans: [PlannerRow] = []
    var goldStrategy: GoldStrategyState?
    var continuationFailure: ContinuationFailureState?

    var runningPl: Double {
        orders.filter { ["FILLED", "POSITION_OPEN", "PARTIALLY_CLOSED"].contains($0.status) }
            .reduce(0) { $0 + ($1.unrealizedPl ?? 0) }
    }
}

struct AccountRow: Identifiable, Equatable {
    let id: String
    let name: String
    let number: String
    let risk: Double
    let equityBalance: Double?
    let availableMargin: Double?
    let currencyCode: String
    let brokerScopeKey: String?
    let marketType: String?
    let brokerType: String?
    let brokerServer: String?

    func brokerScope() -> String {
        if let key = brokerScopeKey, !key.isEmpty { return key }
        let market = (marketType?.isEmpty == false ? marketType! : "INTERNATIONAL").uppercased()
        let broker = (brokerType?.isEmpty == false ? brokerType! : "MT5").uppercased()
        let server = (brokerServer ?? "").uppercased()
        return "\(market)|\(broker)|\(server)"
    }
}

struct WatchRow: Identifiable {
    var id: String { symbol.uppercased() }
    let symbol: String
    let price: Double?
}

struct OrderRow: Identifiable {
    let id: String
    let accountId: String
    let symbol: String
    let side: String
    let status: String
    let orderType: String
    let entry: Double?
    let stopLoss: Double?
    let target: Double?
    let quantity: Double?
    let positionQuantity: Double?
    let unrealizedPl: Double?
    let realizedPl: Double?
    let dryRun: Bool
    let failureReason: String?
    let placementFallbackReason: String?
    let comment: String?
    let metaPositionId: String?
    let externalSource: String?
    let rrRatio: Double?
    let isOpenPosition: Bool
    let plannerPlanAccountId: String?
    let brokerInfoAccountId: String?
    let brokerInfoAccountName: String?
    let brokerInfoAvailableMargin: Double?
    let createdAt: String?
    let openedAt: String?
    let closedAt: String?
    let updatedAt: String?
}

struct OrdersTabRow: Identifiable {
    let id: String
    let symbol: String
    let side: String
    let orderTypeLabel: String
    let price: Double?
    let quantity: Double?
    let status: String
    let derived: Bool
    let editable: Bool
    let sourceOrder: OrderRow?
    let accountId: String
    let brokerInfoAccountName: String?
}

struct OrderEventRow: Identifiable {
    let id: String
    let eventType: String
    let status: String
    let message: String
    let eventTsIst: String
    let failureReason: String?
    let payloadJson: String?
}

struct BrokerTradeHistoryRow: Identifiable {
    let id: String
    let symbol: String
    let type: String
    let status: String
    let openPrice: Double?
    let closePrice: Double?
    let profit: Double
    let netProfit: Double
    let isRunning: Bool
}

struct GoldConfigRow {
    let symbol: String
    let running: Bool
    let triggerSource: String
    let pdHigh: Double?
    let pdLow: Double?
    let userTriggerPrice: Double?
}

struct GoldRunRow: Identifiable {
    let id: String
    let symbol: String
    let status: String
    let runningPl: Double
    let bookedPl: Double
    let quantity: Double
}

struct GoldStrategyState {
    let config: GoldConfigRow
    let running: [GoldRunRow]
    let history: [GoldRunRow]
}

struct ContinuationFailureEventRow: Identifiable {
    let id: String
    let eventType: String
    let status: String
    let message: String
    let createdAt: String
    let createdAtIst: String
}

struct ContinuationFailureRunRow: Identifiable {
    let id: String
    let symbol: String
    let status: String
    let direction: String
    let pivotPrice: Double?
    let runningPl: Double
    let bookedPl: Double
    let events: [ContinuationFailureEventRow]
}

struct ContinuationFailureSymbolConfig {
    let symbol: String
    let pivotPrice: Double?
}

struct ContinuationFailureState {
    let symbols: [ContinuationFailureSymbolConfig]
    let running: [ContinuationFailureRunRow]
    let history: [ContinuationFailureRunRow]
}

struct PlannerRow: Identifiable {
    let id: String
    let symbol: String
    let status: String
    let runtime: String
    let entry: Double?
    let stopLoss: Double?
}

struct NotificationRow: Identifiable {
    let id: String
    let category: String
    let symbol: String
    let status: String
    let activity: String
    let failureReason: String?
    let placementFallbackReason: String?
}

struct TrendPilotRunRow: Identifiable {
    var id: String { runId }
    let runId: String
    let accountId: String
    let accountName: String
    let symbol: String
    let displaySymbol: String
    let state: String
    let currentSide: String
    let rollCount: Int
    let quantity: Double
    let windowHigh: Double?
    let windowLow: Double?
    let cumulativePnl: Double
    let lossCapEnabled: Bool
    let lossCapPct: Double
    let lastError: String
}

struct TrendPilotHistoryRow: Identifiable {
    var id: String { runId }
    let runId: String
    let accountId: String
    let accountName: String
    let symbol: String
    let displaySymbol: String
    let status: String
    let rollCount: Int
    let startedAt: String
    let totalPnl: Double?
    let closedTrades: Int?
    let maxDrawdown: Double?
}

struct TrendPilotBacktestRow: Identifiable {
    var id: String { resultId }
    let resultId: String
    let symbol: String
    let displaySymbol: String
    let fromDate: String
    let toDate: String
    let quantity: Double
    let totalPnl: Double?
    let closedTrades: Int?
    let rollCount: Int
    let maxDrawdown: Double?
}

struct TrendPilotBacktestPage {
    let results: [TrendPilotBacktestRow]
    let hasNextPage: Bool
    let hasPreviousPage: Bool
    let endCursor: String?
    let totalCount: Int
    let totalPages: Int
    let limit: Int
}

struct TrendPilotRollRow: Identifiable {
    var id: String { "\(eventType)-\(eventTime)-\(fromSide)-\(toSide)" }
    let eventType: String
    let eventTime: String
    let fromSide: String
    let toSide: String
    let pnlUpdate: Double
    let cumulativePnl: Double
    let message: String
}

struct TrapReversalRunRow: Identifiable {
    var id: String { symbol }
    let symbol: String
    let displaySymbol: String
    let state: String
    let riskAmount: Double
}

struct TrapReversalLevels {
    let symbol: String
    let displaySymbol: String
    let supports: [Double]
    let resistances: [Double]
    let priceDigits: Int?
}
