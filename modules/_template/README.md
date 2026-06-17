# Module Template

Copy this directory to create a new module.

## Quick Start

```bash
# 1. Copy the template
cp -r modules/_template modules/YOUR_MODULE_KEY

# 2. Replace placeholders (case-sensitive):
#    MODULE_KEY          → your-module-key
#    MODULE_DISPLAY_NAME → Your Module Display Name
#
#    Files to update:
#      manifest.json
#      sandbox/package.json
#      sandbox/index.html
#      sandbox/src/App.vue
#
# 3. Set sandbox port (pick a unique port, check existing sandboxes):
#    Option A: export VITE_SANDBOX_PORT=5175 && npm run dev
#    Option B: edit sandbox/vite.config.ts default value (currently 5173)

# 4. Install and run
cd modules/YOUR_MODULE_KEY/sandbox
npm install
npm run dev
```

## Directory Structure

```
modules/{module_key}/
  manifest.json          ← Module identity (name, icon, icon_asset, permissions, window spec, backend router)
  frontend/              ← Your Vue components and business logic
    index.vue            ← Entry component (referenced by manifest.component_key)
    assets/              ← Module static assets (icons, images — NOT in framework dir)
  backend/               ← (Optional) Python FastAPI router
    router.py            ← Export `router = APIRouter(prefix="/api/xxx")`
  runtime/               ← Runtime middle layer (copied from _template)
    index.ts             ← getApiUrl(), getModuleSetting(), hasPermission(), initRuntime()
  sandbox/               ← Independent dev environment
    package.json         ← npm dependencies
    vite.config.ts       ← Vite config with proxy to backend
    runtime.config.json  ← Sandbox settings (API URL, permissions, module prefs)
    index.html           ← Entry HTML
    src/main.ts          ← Vue app bootstrap
    src/App.vue          ← Sandbox shell wrapping your module entry
```

### Icon

Module icons live in the module directory, never in framework assets.

- `manifest.icon` — Element Plus icon key for SVG fallback (e.g. `"ChatDotRound"`, `"Collection"`)
- `manifest.icon_asset` — Optional, path to a custom PNG relative to `frontend/` (e.g. `"assets/icon.png"`)

Place your PNG at `modules/{key}/frontend/assets/icon.png` and declare it in manifest. The build pipeline auto-registers it — no framework file changes needed.

See `开发文档/03_模块开发文档/README.md` → 图标（Icon） for the full spec.

## Sandbox Development

- `npm run dev` starts the sandbox at a unique port
- API calls to `/api/*` are proxied to the main backend
- The sandbox imports your module entry via `@modules/MODULE_KEY/frontend/index.vue`
- The sandbox registers Element Plus globally to keep isolated local preview simple. The main framework still uses on-demand Element Plus imports and chunk splitting.
- When development is complete, run `cd frontend && npm run build` to verify integration

## If the Sandbox Template Isn't Enough

The sandbox is a minimal shell. If your module needs framework features that aren't available:

1. Add a local adapter in `runtime/` first.
2. Use module-local mock data, stub services, or test components inside the sandbox.
3. Add any extra dependencies to `sandbox/package.json`.
4. If the capability should become shared, promote it to a platform API or runtime contract before using it in the module.

The goal is that your module frontend code (`modules/{name}/frontend/`) never imports from
`@/` (framework) — it only imports from `../runtime` and `@modules/...` (other modules).
