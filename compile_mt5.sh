#!/usr/bin/env bash
set -e

WINE_BIN="${WINE_BIN:-/opt/homebrew/bin/wine}"
WINEPREFIX="${WINEPREFIX:-/Users/alami/mt5prefix}"
MT5_DIR="$WINEPREFIX/drive_c/Program Files/MetaTrader 5"
EXPERTS_DIR="$MT5_DIR/MQL5/Experts"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_DIR="$REPO_DIR/bridge/mt5"
LINK_TARGET="$EXPERTS_DIR/LLMTradingV2"

echo "=== LLMTradingV2 MT5 Auto-Link & Compiler ==="

# 1. Ensure Symlink exists in MT5 Wine directory
if [ ! -L "$LINK_TARGET" ] && [ ! -d "$LINK_TARGET" ]; then
    echo "Creating symlink from $BRIDGE_DIR to $LINK_TARGET..."
    ln -s "$BRIDGE_DIR" "$LINK_TARGET"
    echo "Symlink created successfully."
else
    echo "Symlink already active: $LINK_TARGET -> $(readlink "$LINK_TARGET" || echo "$LINK_TARGET")"
fi

# 2. Compile all MQ5 files
cd "$MT5_DIR"

compile_file() {
    local rel_path="$1"
    local win_path="${rel_path//\//\\}"
    echo "--------------------------------------------------------"
    echo "Compiling: $win_path"
    
    WINEPREFIX="$WINEPREFIX" "$WINE_BIN" ./MetaEditor64.exe /compile:"$win_path" /log > /dev/null 2>&1 || true

    local log_file="$MT5_DIR/${rel_path%.*}.log"
    if [ -f "$log_file" ]; then
        local summary=$(iconv -f UTF-16LE -t UTF-8 "$log_file" 2>/dev/null | grep "Result:" || echo "Compilation finished")
        echo "  $summary"
    else
        echo "  Done."
    fi
}

# Main Bridge EA
compile_file "MQL5/Experts/LLMTradingV2/LLMTradingBridge.mq5"

# Inspectors
compile_file "MQL5/Experts/LLMTradingV2/inspectors/Structure_Inspector.mq5"
compile_file "MQL5/Experts/LLMTradingV2/inspectors/FVG_Inspector.mq5"
compile_file "MQL5/Experts/LLMTradingV2/inspectors/OrderBlock_Inspector.mq5"
compile_file "MQL5/Experts/LLMTradingV2/inspectors/CandlePattern_Inspector.mq5"
compile_file "MQL5/Experts/LLMTradingV2/inspectors/Fibonacci_OTE_Inspector.mq5"
compile_file "MQL5/Experts/LLMTradingV2/inspectors/Liquidity_Inspector.mq5"

echo "--------------------------------------------------------"
echo "✅ All EAs compiled into .ex5 directly inside bridge/mt5/"
echo "In MT5: Right-click 'Experts' -> 'Refresh' in Navigator to see updated EAs."
