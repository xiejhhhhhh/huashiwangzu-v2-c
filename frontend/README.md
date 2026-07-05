# Frontend

The frontend is the Vue desktop shell for V2. Business module UI belongs under `modules/`.

## Stack

- Vue 3
- TypeScript
- Vite
- Pinia
- Element Plus

## Responsibilities

- Login and app entry routing.
- Desktop shell, windows, taskbar, launcher, tray, context menus, drag/drop.
- Shared API client, upload helpers, icons, and file associations.
- Dynamic loading of module frontend entries.

## Main Paths

```text
frontend/src/app-entry/
frontend/src/desktop/
frontend/src/platform/
frontend/src/shared/
frontend/src/styles/
```

## Commands

```bash
cd frontend && npm run dev
cd frontend && npm run build
cd frontend && npm run scan:modules
```

Module frontend code must use runtime/platform APIs and must not import desktop shell internals.
