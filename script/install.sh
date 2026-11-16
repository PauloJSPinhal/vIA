#!/usr/bin/env bash
set -e

# Resolve o diretório raiz do projeto independentemente de onde o script é chamado
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/via"
CONFIG_LEGADO="$HOME/.config/assistente"

echo "=== A instalar o vIA ==="

# 1. Garantir permissões de execução no projeto
chmod +x "$PROJECT_ROOT/src/main.py"
if [ -f "$PROJECT_ROOT/via" ]; then
    chmod +x "$PROJECT_ROOT/via"
    TARGET_EXEC="$PROJECT_ROOT/via"
else
    TARGET_EXEC="$PROJECT_ROOT/src/main.py"
fi

# 2. Verificar dependências Python
if ! python3 -c "import PySide6" >/dev/null 2>&1; then
    echo "[ERRO] PySide6 não está instalado."
    echo "       Debian/Ubuntu: sudo apt install python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtwidgets"
    echo "       Ou:            pip install -r \"$PROJECT_ROOT/requirements.txt\""
    exit 1
fi
echo "[OK] PySide6 disponível"

# 3. Criar link simbólico em ~/.local/bin/via
mkdir -p "$BIN_DIR"
ln -sf "$TARGET_EXEC" "$BIN_DIR/via"
echo "[OK] Comando 'via' ligado em $BIN_DIR/via"

# 4. Criar diretório de configuração XDG
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"
echo "[OK] Diretório de configuração em $CONFIG_DIR"
if [ -d "$CONFIG_LEGADO" ] && [ ! -f "$CONFIG_DIR/config.json" ]; then
    echo "[--] Configuração antiga detetada em $CONFIG_LEGADO (será migrada no primeiro arranque)."
fi

# 5. Criar lançador gráfico (.desktop) para o menu do sistema
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
Exec="$BIN_DIR/via"
Icon=$ICON_PATH
Terminal=false
Categories=System;Utility;Development;
StartupNotify=true
DESKTOP

chmod +x "$APP_DIR/vIA.desktop"
echo "[OK] Atalho gráfico criado em $APP_DIR/vIA.desktop"

# 6. Verificar se ~/.local/bin está no PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "[AVISO] $BIN_DIR não está no teu \$PATH atual."
    echo "Adiciona 'export PATH=\"\$HOME/.local/bin:\$PATH\"' ao teu ~/.zshrc ou ~/.bashrc."
fi

echo ""
echo "Instalação concluída! Podes iniciar o vIA escrevendo 'via' no terminal ou pelo menu de aplicações."
