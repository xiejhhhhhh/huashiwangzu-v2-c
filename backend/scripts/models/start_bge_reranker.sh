#!/bin/zsh
LLAMA_BIN="/Users/hekunhua/llama.cpp-latest/build/bin/llama-server"
MODEL="/Users/hekunhua/Documents/AI模型/Embedding模型/bge-reranker-v2-m3-Q4_K_M.gguf"
PORT=30001

exec "$LLAMA_BIN" \
  -m "$MODEL" \
  --port "$PORT" \
  --sleep-idle-seconds 300 \
  -c 8192 \
  -ngl 99 \
  --rerank
