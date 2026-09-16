import ExecutionTerminalWorkspace from "../terminal/ExecutionTerminalWorkspace";

export default function InternationalMarketWorkspace({
  mobileWatchlistOpen,
  setMobileWatchlistOpen,
  WatchlistComponent,
  selectedAccountExists,
  liveWatchlist,
  notify,
  selectedInstrument,
  setSelectedInstrument,
  liveStatus,
  me,
  internationalAccounts,
  activeAccountSymbolAliases = {},
  symbolPriceDigits = {},
  onSymbolDigits,
  OrderScreenComponent,
  token,
  livePrices,
  liveOrders = [],
  subscribeLiveSymbol,
  onAccountRiskSaved,
  onFullClosePosition,
  onOpenPartialClose,
  actionLoadingId = "",
  onMeUpdated,
}) {
  return (
    <ExecutionTerminalWorkspace
      mobileWatchlistOpen={mobileWatchlistOpen}
      setMobileWatchlistOpen={setMobileWatchlistOpen}
      WatchlistComponent={WatchlistComponent}
      selectedAccountExists={selectedAccountExists}
      liveWatchlist={liveWatchlist}
      notify={notify}
      selectedInstrument={selectedInstrument}
      setSelectedInstrument={setSelectedInstrument}
      liveStatus={liveStatus}
      me={me}
      internationalAccounts={internationalAccounts}
      activeAccountSymbolAliases={activeAccountSymbolAliases}
      symbolPriceDigits={symbolPriceDigits}
      onSymbolDigits={onSymbolDigits}
      OrderScreenComponent={OrderScreenComponent}
      accounts={internationalAccounts}
      activeAccountId={me?.selected_account_id || ""}
      token={token}
      livePrices={livePrices}
      liveOrders={liveOrders}
      subscribeLiveSymbol={subscribeLiveSymbol}
      onAccountRiskSaved={onAccountRiskSaved}
      onFullClosePosition={onFullClosePosition}
      onOpenPartialClose={onOpenPartialClose}
      actionLoadingId={actionLoadingId}
      onMeUpdated={onMeUpdated}
    />
  );
}
