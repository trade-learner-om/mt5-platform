# Frontend production build hang fix

## Problem

`npm run build` appeared stuck at `transforming...` indefinitely (0% CPU). Multiple overlapping `vite build` processes from retries could deadlock each other. Vite 8 + Rolldown also has known transform deadlocks on constrained CI runners.

## Fix

- Downgrade to Vite 6 + `@vitejs/plugin-react` 4 (Rollup-based, stable)
- Remove duplicate `vite.config.ts` (keep single `vite.config.js`)
- Use esbuild minify and split vendor chunks in build config

If a build hangs again, stop all `vite build` processes and clear `node_modules/.vite` before retrying.
