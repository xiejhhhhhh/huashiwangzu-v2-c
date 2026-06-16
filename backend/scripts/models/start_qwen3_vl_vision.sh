#!/bin/zsh
LLAMA_BIN="/Users/hekunhua/llama.cpp-latest/build/bin/llama-server"
MODEL="/Users/hekunhua/Documents/AI模型/图片分析模型/Qwen3VL-8B-Instruct-Q4_K_M.gguf"
MMPROJ="/Users/hekunhua/Documents/AI模型/图片分析模型/mmproj-Qwen3VL-8B-Instruct-F16.gguf"
PORT=30002

exec "$LLAMA_BIN" \
  -m "$MODEL" \
  --mmproj "$MMPROJ" \
  --port "$PORT" \
  --sleep-idle-seconds 300 \
  -c 32768 \
  -ngl 99
