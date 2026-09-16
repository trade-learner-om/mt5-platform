# 2026-07-09 - Unmitigated Swings Price Formatting

## Frontend

- Updated `apps/frontend-react/src/pages/UnmitigatedSwingsPage.jsx` to use the shared price-precision helpers instead of a page-local formatter.
- The page now resolves broker price digits from the live tick stream and cached symbol digit map, so:
  - live price;
  - level price;
  - distance-to-live-price
  all render with the same decimal precision as the active instrument.
- `apps/frontend-react/src/App.jsx` now passes `symbolPriceDigits` into the Unmitigated Swings page so broker precision remains available even before the next live tick refresh.
