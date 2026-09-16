import TerminalDashboard from "./TerminalDashboard";

export default function ExecutionTerminalWorkspace({
  selectedAccountExists,
  liveWatchlist,
  notify,
  selectedInstrument,
  setSelectedInstrument,
  token,
  livePrices,
  liveOrders = [],
  symbolPriceDigits = {},
  OrderScreenComponent,
  accounts = [],
  activeAccountId = "",
  onSymbolDigits,
  subscribeLiveSymbol,
  onAccountRiskSaved,
  me,
  onMeUpdated,
  onFullClosePosition,
  onOpenPartialClose,
  actionLoadingId = "",
}) {
  return (
    <TerminalDashboard
      token={token}
      selectedAccountExists={selectedAccountExists}
      liveWatchlist={liveWatchlist}
      liveOrders={liveOrders}
      selectedInstrument={selectedInstrument}
      onSelectInstrument={setSelectedInstrument}
      onNotify={notify}
      livePrices={livePrices}
      symbolPriceDigits={symbolPriceDigits}
      OrderScreenComponent={OrderScreenComponent}
      accounts={accounts}
      activeAccountId={activeAccountId}
      onSymbolDigits={onSymbolDigits}
      subscribeLiveSymbol={subscribeLiveSymbol}
      onAccountRiskSaved={onAccountRiskSaved}
      me={me}
      onMeUpdated={onMeUpdated}
      onFullClosePosition={onFullClosePosition}
      onOpenPartialClose={onOpenPartialClose}
      actionLoadingId={actionLoadingId}
    />
  );
}
