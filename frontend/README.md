# Frontend

The frontend is the Vue desktop shell for V2.

## Stack

- Vue 3
- TypeScript
- Vite
- Element Plus

## Responsibilities

- Desktop shell entry.
- Login and app entry routing.
- Window system, taskbar, launcher, selection, drag and drop, context menu.
- Shared UI, API client, upload helpers, icons, and file associations.
- Dynamic loading of business modules.

Business module UI should live under `modules/`, not inside the desktop shell.

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
npm run dev
npm run build
```

