# Desktop Design System

This directory contains desktop-shell-specific design token extensions.

## Token Layers

```text
Base tokens      -> frontend/src/styles/theme.css
Desktop tokens   -> frontend/src/desktop/design-system/desktop-design-tokens.css
```

Base tokens are shared by the whole frontend. Desktop tokens are opt-in variables for shell components such as windows, taskbar, launcher, menus, and tray surfaces.

## Usage

1. Business module content should prefer base tokens from `theme.css`.
2. Desktop shell components may use `--desktop-*` variables.
3. Desktop tokens must not leak into reusable business module styles.
4. New desktop-only tokens belong in this directory and must use the `--desktop-` prefix.

