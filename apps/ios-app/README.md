# SignalBridge MT5 — iOS App

Native SwiftUI iOS client matching the Android app in `apps/android-app`. The app talks directly to the production backend at `https://api.signalbridge.in` and `wss://api.signalbridge.in/ws/live`.

## Features

- Production backend `/health` check
- Login / register, saved JWT, Face ID / passcode unlock
- Watch, Trade, Positions, More (Strategies)
- Live websocket state, watchlist, manual orders
- Positions with expandable order activity timeline
- Trap Reversal start/stop/levels (live API)
- Trade planner run/deactivate/delete
- Local notifications for order/strategy status changes

Note: some screens may still reference removed `/gold-strategy/*` or `/trend-pilot/*` endpoints. Do not restore those backends; clean up mobile callers when touching strategy UI.

## Requirements

- Xcode 26+ (iOS 26 deployment target)
- Reachability to `https://api.signalbridge.in`

## Open in Xcode

1. Open `apps/ios-app/SignalBridgeMT5.xcodeproj`
2. Select your development team under **Signing & Capabilities**
3. Build and run on a physical device

## First launch

When `AppConfig.useFixedHost` is `true` (default for this build), the app connects automatically to `https://api.signalbridge.in` and skips the host setup screen. Change `AppConfig.fixedApiBase` / `AppConfig.fixedHost` in `AppConfig.swift` to point at another server.

Otherwise:

1. Enter primary host, e.g. `192.168.7.1:5173`
2. Login or register with your platform credentials
3. Use Watchlist → Trade shortcuts or bottom tabs

The app stores JWT in UserDefaults. In the fixed-build path, API base is `https://api.signalbridge.in`.

## HTTPS on iOS

This build talks to the platform over standard **HTTPS** and **WSS**. The older LAN HTTP notes below only matter if you switch the app back to an unsecured local host:

- `NSAllowsArbitraryLoads = true` — allows HTTP to any host (standard for developer/trusted installs)
- `NSExceptionAllowsInsecureHTTPLoads` for `localhost` — extra allowance if you point back to an HTTP-only local debug host

Trusted developer signing does **not** bypass ATS by itself. The **Info.plist inside the installed `.app`** must contain those keys.

After changing ATS settings you must:

1. Delete SignalBridge from the iPhone
2. Xcode → **Product → Clean Build Folder** (⇧⌘K)
3. **Run** again (⌘R)

To verify the built app picked up ATS settings (on Mac, after a device build):

```bash
plutil -p ~/Library/Developer/Xcode/DerivedData/*/Build/Products/Debug-iphoneos/SignalBridgeMT5.app/Info.plist | rg -A6 AppTransport
```

You should see `NSAllowsArbitraryLoads => 1`.
