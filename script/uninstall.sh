#!/usr/bin/env bash
set -e

BIN_LINK="$HOME/.local/bin/via"
DESKTOP_FILE="$HOME/.local/share/applications/vIA.desktop"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/via"
CONFIG_LEGADO="$HOME/.config/assistente"

echo "=== A desinstalar o vIA ==="

# 1. Remover link simbólico do executável
if [ -L "$BIN_LINK" ] || [ -f "$BIN_LINK" ]; then
    rm -f "$BIN_LINK"
    echo "[OK] Removido $BIN_LINK"
else
    echo "[--] Link $BIN_LINK não encontrado."
fi

# 2. Remover lançador gráfico (.desktop)
if [ -f "$DESKTOP_FILE" ]; then
    rm -f "$DESKTOP_FILE"
    echo "[OK] Removido $DESKTOP_FILE"
else
    echo "[--] Atalho $DESKTOP_FILE não encontrado."
fi

# 3. Perguntar se pretende apagar as configurações e lista de scripts
for DIR_CONFIG in "$CONFIG_DIR" "$CONFIG_LEGADO"; do
    if [ -d "$DIR_CONFIG" ]; then
        echo ""
        read -r -p "Apagar configurações e scripts em $DIR_CONFIG? [s/N]: " resp || resp="n"
        case "$resp" in
            [sS])
                rm -rf "$DIR_CONFIG"
                echo "[OK] Removido $DIR_CONFIG"
                ;;
            *)
                echo "[OK] Mantido $DIR_CONFIG"
                ;;
        esac
    fi
done

echo ""
echo "Desinstalação concluída. A pasta do código-fonte não foi alterada."
