# Hello World Module

Sample module for scaffolding and integration testing.

## Capability

No HTTP API or capability registered. Used as a minimal verification target in framework tests.

## Verification

```bash
# Module is registered in app manifest: hello-world
# Verified via framework health endpoint:
curl http://127.0.0.1:33000/api/health | python3 -m json.tool
```

