# Sandbox - AI Assistant Module

This is the independent development environment for the AI Assistant module.

Run:
  cd modules/ai-assistant/sandbox
  npm install
  npm run dev

The sandbox runs at http://localhost:5174 and serves the module frontend
inside a minimal desktop shell. API requests to /api are proxied to
the main backend.

Use this when developing or debugging the module in isolation.
When it works, run `cd frontend && npm run build` to verify full integration.

Sandbox config is in runtime.config.json and will be replaced by the
main framework configuration when the module is integrated.
