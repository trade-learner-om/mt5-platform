# Android App

## Purpose

Maintain the native Android client in `apps/android-app` for direct access to the deployed SignalBridge backend.

## Implementation

The Android app is a Kotlin/Jetpack Compose project. It does not embed the React app in a WebView. The current build connects directly to the production backend:

- REST API: `https://api.signalbridge.in`
- WebSocket: `wss://api.signalbridge.in/ws/live`

The app uses OkHttp for REST and websocket calls and mirrors the React mobile visual language with Compose cards, rounded controls, indigo/slate colors, and compact mobile tabs.
