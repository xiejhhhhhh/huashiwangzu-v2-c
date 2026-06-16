#!/bin/bash
# Ensure pdfjs worker is available in public/ for production builds
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC="$FRONTEND_DIR/node_modules/pdfjs-dist/build/pdf.worker.min.mjs"
DEST="$FRONTEND_DIR/public/pdf.worker.min.mjs"
if [ -f "$SRC" ]; then
  cp "$SRC" "$DEST"
  echo "pdf worker copied to $DEST"
else
  echo "warning: pdf worker not found at $SRC, skipping"
fi
