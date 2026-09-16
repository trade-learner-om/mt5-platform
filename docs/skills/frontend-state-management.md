# Frontend State Management

## Purpose

Separate local session state from server state.

## Implementation

Zustand stores the JWT token and current user profile in `src/stores/authStore.ts`. React Query owns API-backed data such as current user and MT5 account information.

The Axios client reads the token from Zustand before each request and adds the bearer token header.

## Dependencies

- `zustand`
- `@tanstack/react-query`
- `axios`
- `react-router-dom`

## Usage Examples

- Use `useLogin` and `useRegister` for auth mutations.
- Use `useCurrentUser` to hydrate session user data after refresh.
- Use `useMT5Account` for dashboard/header account data; it polls every 30 seconds.

Do not store MT5 passwords or decrypted credentials in frontend state.
