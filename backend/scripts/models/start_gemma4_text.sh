#!/bin/zsh
LLAMA_BIN="/Users/hekunhua/llama.cpp-latest/build/bin/llama-server"
MODEL="/Users/hekunhua/Documents/AI模型/文本模型/google_gemma-4-26B-A4B-it-Q4_K_M.gguf"
PORT=30003

exec "$LLAMA_BIN" \
  -m "$MODEL" \
  --port "$PORT" \
  --sleep-idle-seconds 300 \
  -c 8192 \
  -ngl 99
