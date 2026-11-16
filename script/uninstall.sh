#!/usr/bin/env bash
set -e

BIN_LINK="$HOME/.local/bin/via"
DESKTOP_FILE="$HOME/.local/share/applications/vIA.desktop"
CONFIG_DIR="$HOME/.config/via"

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
if [ -d "$CONFIG_DIR" ]; then
    echo ""
    read -r -p "Desejas também apagar as configurações e scripts registados em $CONFIG_DIR? [s/N]: " resp
    if [[ "$resp" =~ ^[sS]$ ]]; then
        rm -rf "$CONFIG_DIR"
        echo "[OK] Configurações removidas ($CONFIG_DIR)."
    else
        echo "[OK] Configurações mantidas em $CONFIG_DIR."
    fi
fi

echo ""
echo "Desinstalação concluída. A pasta do código-fonte não foi alterada."
