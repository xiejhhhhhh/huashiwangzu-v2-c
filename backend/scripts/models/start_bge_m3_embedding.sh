#!/bin/zsh
LLAMA_BIN="/Users/hekunhua/llama.cpp-latest/build/bin/llama-server"
MODEL="/Users/hekunhua/Documents/AI模型/Embedding模型/bge-m3-q4_k_m.gguf"
PORT=30000

exec "$LLAMA_BIN" \
  -m "$MODEL" \
  --port "$PORT" \
  --sleep-idle-seconds 300 \
  -c 8192 \
  -ngl 99 \
  --pooling cls \
  --embeddings
