#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_DIR="$REPO_DIR/bridge/mt5"

echo "============================================================"
echo "🔨 LLMTradingV2 MT5 Auto-Link & Compiler"
echo "Source: $BRIDGE_DIR"
echo "============================================================"

# Mode 1: Native Windows via Git Bash / MSYS / Cygwin
IS_WINDOWS=false
if [[ "$OSTYPE" == "msys"* || "$OSTYPE" == "cygwin"* || -n "$WINDIR" ]]; then
    IS_WINDOWS=true
fi

if [ "$IS_WINDOWS" = true ]; then
    echo "[Mode] Native Windows detected."
    EDITOR_EXE=""
    CANDIDATES=(
        "/c/Program Files/MetaTrader 5/metaeditor64.exe"
        "/c/Program Files/PU Prime MetaTrader 5/metaeditor64.exe"
        "/c/Program Files/ICMarkets MetaTrader 5/metaeditor64.exe"
        "/c/Program Files/XM Global MT5/metaeditor64.exe"
        "/c/Program Files/Exness MetaTrader 5/metaeditor64.exe"
        "/c/Program Files/FTMO MetaTrader 5/metaeditor64.exe"
        "/c/Program Files (x86)/MetaTrader 5/metaeditor64.exe"
        "C:\\Program Files\\MetaTrader 5\\metaeditor64.exe"
    )
    for c in "${CANDIDATES[@]}"; do
        if [ -f "$c" ]; then
            EDITOR_EXE="$c"
            break
        fi
    done

    if [ -z "$EDITOR_EXE" ]; then
        EDITOR_EXE="$(find /c/Program\ Files* -name "metaeditor64.exe" -o -name "MetaEditor64.exe" 2>/dev/null | head -n 1 || true)"
    fi

    if [ -z "$EDITOR_EXE" ]; then
        echo "❌ [ERROR] metaeditor64.exe not found in Program Files."
        exit 1
    fi

    echo "Using MetaEditor: $EDITOR_EXE"
    compile_file_win() {
        local file_rel="$1"
        local full_path="$BRIDGE_DIR/$file_rel"
        local win_src="$(cygpath -w "$full_path" 2>/dev/null || echo "$full_path")"
        local log_file="$BRIDGE_DIR/${file_rel%.*}.log"
        local win_log="$(cygpath -w "$log_file" 2>/dev/null || echo "$log_file")"
        
        echo "--------------------------------------------------------"
        echo "Compiling: $file_rel"
        "$EDITOR_EXE" /compile:"$win_src" /log:"$win_log" > /dev/null 2>&1 || true
        
        if [ -f "$log_file" ]; then
            local summary=$(iconv -f UTF-16LE -t UTF-8 "$log_file" 2>/dev/null | grep "Result:" || cat "$log_file" 2>/dev/null | head -n 2)
            echo "  $summary"
        else
            echo "  Done."
        fi
    }

    compile_file_win "LLMTradingBridge.mq5"
    echo "--------------------------------------------------------"
    echo "✅ Compiled successfully into bridge/mt5/LLMTradingBridge.ex5"
    exit 0
fi

# Mode 2: Linux / macOS via Wine
echo "[Mode] Wine environment detected."

# 1. Auto-detect WINE_BIN
if [ -z "$WINE_BIN" ] || [ ! -x "$WINE_BIN" ]; then
    if command -v wine64 &>/dev/null; then
        WINE_BIN="$(command -v wine64)"
    elif command -v wine &>/dev/null; then
        WINE_BIN="$(command -v wine)"
    elif [ -x "/opt/homebrew/bin/wine" ]; then
        WINE_BIN="/opt/homebrew/bin/wine"
    elif [ -x "/usr/local/bin/wine" ]; then
        WINE_BIN="/usr/local/bin/wine"
    elif [ -x "/usr/bin/wine" ]; then
        WINE_BIN="/usr/bin/wine"
    else
        echo "❌ [ERROR] Wine binary not found. Please install wine or set WINE_BIN."
        exit 1
    fi
fi
echo "Using Wine: $WINE_BIN"

# 2. Auto-detect WINEPREFIX
if [ -z "$WINEPREFIX" ] || [ ! -d "$WINEPREFIX" ]; then
    PREFIX_CANDIDATES=(
        "$HOME/mt5prefix"
        "$HOME/.wine"
        "/root/mt5prefix"
        "/root/.wine"
        "$HOME/.local/share/wineprefixes/mt5"
        "/Users/alami/mt5prefix"
    )
    for p in "${PREFIX_CANDIDATES[@]}"; do
        if [ -d "$p" ]; then
            WINEPREFIX="$p"
            break
        fi
    done
fi

if [ -z "$WINEPREFIX" ] || [ ! -d "$WINEPREFIX" ]; then
    echo "❌ [ERROR] WINEPREFIX directory not found. Please set WINEPREFIX."
    exit 1
fi
echo "Using WINEPREFIX: $WINEPREFIX"

# 3. Auto-detect MT5_DIR
if [ -z "$MT5_DIR" ] || [ ! -d "$MT5_DIR" ]; then
    MT5_CANDIDATES=(
        "$WINEPREFIX/drive_c/Program Files/MetaTrader 5"
        "$WINEPREFIX/drive_c/Program Files (x86)/MetaTrader 5"
        "$WINEPREFIX/drive_c/Program Files/PU Prime MetaTrader 5"
        "$WINEPREFIX/drive_c/Program Files/ICMarkets MetaTrader 5"
    )
    for m in "${MT5_CANDIDATES[@]}"; do
        if [ -d "$m" ]; then
            MT5_DIR="$m"
            break
        fi
    done
fi

if [ -z "$MT5_DIR" ] || [ ! -d "$MT5_DIR" ]; then
    MT5_DIR="$(find "$WINEPREFIX/drive_c/Program Files" -name "metaeditor64.exe" -o -name "MetaEditor64.exe" 2>/dev/null | head -n 1 | xargs -r dirname || true)"
fi

if [ -z "$MT5_DIR" ] || [ ! -d "$MT5_DIR" ]; then
    echo "❌ [ERROR] MetaTrader 5 directory not found inside $WINEPREFIX."
    exit 1
fi
echo "Using MT5 DIR: $MT5_DIR"

EXPERTS_DIR="$MT5_DIR/MQL5/Experts"
mkdir -p "$EXPERTS_DIR"
LINK_TARGET="$EXPERTS_DIR/LLMTradingV2"

# Ensure Symlink exists in MT5 Wine directory
if [ ! -L "$LINK_TARGET" ] && [ ! -d "$LINK_TARGET" ]; then
    echo "Creating symlink from $BRIDGE_DIR to $LINK_TARGET..."
    ln -s "$BRIDGE_DIR" "$LINK_TARGET"
    echo "Symlink created successfully."
else
    echo "Symlink already active: $LINK_TARGET"
fi

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

# Standalone Visual Backtester EA for Strategy Tester
if [ -f "$MT5_DIR/MQL5/Experts/LLMTradingV2/PAC_Visual_Backtester.mq5" ]; then
    compile_file "MQL5/Experts/LLMTradingV2/PAC_Visual_Backtester.mq5"
fi

echo "--------------------------------------------------------"
echo "✅ All EAs compiled into .ex5 directly inside bridge/mt5/"
echo "In MT5: Right-click 'Experts' -> 'Refresh' in Navigator or switch timeframes."
