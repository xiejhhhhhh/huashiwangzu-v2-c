# Desktop Design System

Desktop shell token extensions live here. Business modules should prefer shared base tokens.

## Token Layers

```text
Base tokens     -> frontend/src/styles/theme.css
Desktop tokens  -> frontend/src/desktop/design-system/desktop-design-tokens.css
```

## Rules

1. Shell components may use `--desktop-*` variables.
2. Business modules should use shared base tokens unless a platform contract explicitly exposes a desktop token.
3. New desktop-only tokens belong here and must use the `--desktop-` prefix.
