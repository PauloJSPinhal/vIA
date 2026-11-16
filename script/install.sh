#!/usr/bin/env bash
set -e

# Resolve o diretório raiz do projeto independentemente de onde o script é chamado
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
CONFIG_DIR="$HOME/.config/via"

echo "=== A instalar o vIA ==="

# 1. Garantir permissões de execução no projeto
chmod +x "$PROJECT_ROOT/src/via.py"
if [ -f "$PROJECT_ROOT/via" ]; then
    chmod +x "$PROJECT_ROOT/via"
    TARGET_EXEC="$PROJECT_ROOT/via"
else
    TARGET_EXEC="$PROJECT_ROOT/src/via.py"
fi

# 2. Criar link simbólico em ~/.local/bin/via
mkdir -p "$BIN_DIR"
ln -sf "$TARGET_EXEC" "$BIN_DIR/via"
echo "[OK] Comando 'via' ligado em $BIN_DIR/via"

# 3. Criar diretório de configuração XDG
mkdir -p "$CONFIG_DIR"
echo "[OK] Diretório de configuração preparado em $CONFIG_DIR"

# 4. Criar lançador gráfico (.desktop) para o menu do sistema
mkdir -p "$APP_DIR"
ICON_PATH="utilities-terminal"
if [ -f "$PROJECT_ROOT/assets/icons/via.svg" ]; then
    ICON_PATH="$PROJECT_ROOT/assets/icons/via.svg"
fi

cat << DESKTOP > "$APP_DIR/vIA.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=vIA
Comment=Assistente híbrido de terminal Linux e gestor de scripts
Exec=$BIN_DIR/via
Icon=$ICON_PATH
Terminal=false
Categories=System;Utility;Development;
StartupNotify=true
DESKTOP

chmod +x "$APP_DIR/vIA.desktop"
echo "[OK] Atalho gráfico criado em $APP_DIR/vIA.desktop"

# 5. Verificar se ~/.local/bin está no PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "[AVISO] $BIN_DIR não está no teu \$PATH atual."
    echo "Adiciona 'export PATH=\"\$HOME/.local/bin:\$PATH\"' ao teu ~/.zshrc ou ~/.bashrc."
fi

echo ""
echo "Instalação concluída! Podes iniciar o vIA escrevendo 'via' no terminal ou pelo menu de aplicações."
