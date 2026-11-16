"""Constantes, valores por omissão e caminhos do vIA.

Os modelos NÃO são definidos aqui: são descobertos em runtime a partir do
Ollama local e dos endpoints ``/models`` das APIs cujas chaves estejam
definidas no ambiente.
"""

import os
from pathlib import Path

APP_NOME = "vIA"
APP_ID = "via"
APP_VERSAO = "1.2.0"

# --- Caminhos XDG ---
# Respeita XDG_CONFIG_HOME; recorre a ~/.config quando não está definido.
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
CONFIG_DIR = CONFIG_HOME / APP_ID
CONFIG_FILE = CONFIG_DIR / "config.json"
SCRIPTS_FILE = CONFIG_DIR / "scripts.json"

# Diretório usado por versões antigas (migrado automaticamente).
CONFIG_LEGADO_DIR = Path.home() / ".config" / "assistente"

# --- Ollama ---
OLLAMA_BASE_URL = os.environ.get("VIA_OLLAMA_URL", "http://localhost:11434").rstrip("/")

# --- Descoberta de modelos ---
DESCOBERTA_TIMEOUT = 8  # segundos por provedor

PREFIXOS_PROVEDOR = ("ollama:", "gemini:", "groq:", "deepseek:")

# Chave de ambiente necessária para cada provedor externo.
PROVEDORES_EXTERNOS = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}

# Nomes apresentados na interface (não são modelos).
NOMES_PROVEDORES = {
    "ollama": "Local",
    "gemini": "Gemini",
    "groq": "Groq",
    "deepseek": "DeepSeek",
}

# --- Limites de anexos (evitam pedidos gigantes e bloqueios da interface) ---
TAMANHO_MAX_TEXTO = 30_000
TAMANHO_MAX_PDF = 25_000
TAMANHO_MAX_IMAGEM = 10 * 1024 * 1024  # 10 MB por imagem
MAX_IMAGENS = 8
MAX_ANEXOS = 20
MAX_ARGUMENTO = 4_096

# --- Execução de scripts ---
TIMEOUT_SCRIPT_PADRAO = 300  # segundos; 0 = sem limite

DEFAULT_CONFIG = {
    # Vazio até a descoberta encontrar um modelo disponível.
    "modelo": "",
    "temperatura": 0.3,
    "timeout": 90,
    "timeout_script": TIMEOUT_SCRIPT_PADRAO,
    "regras": (
        "És um assistente de terminal Linux útil e direto. Comunicas sempre em português de Portugal.\n"
        "1. Se o pedido (ou os ficheiros anexados) corresponder à execução de um dos scripts locais disponíveis, "
        "define \"acao\": \"executar\", indica o nome exato do script e extrai o argumento (como o caminho do ficheiro).\n"
        "2. Se o utilizador anexar imagens, PDFs ou ficheiros de texto/código para analisar, responde de forma clara, "
        "técnica e estruturada sobre o conteúdo desses ficheiros.\n"
        "3. Para qualquer outra pergunta ou conversa, responde de forma útil, natural e variada."
    ),
}

DEFAULT_SCRIPTS = {
    "audio-reset": {
        "caminho": "/mnt/dados/Projetos/1_Scripts/Audio-Reset/audio-reset.sh",
        "descricao": "Reinicia o servidor de som (WirePlumber/PipeWire) quando o áudio encrava ou deixa de dar.",
        "args": False,
        "perigoso": False,
    }
}

# Correções de caminhos criados por versões antigas com valores por omissão errados.
CORRECOES_CAMINHOS_CONHECIDOS = {
    "/mnt/dados/Projetos/1_Scripts/Audio-Reset/src/audio-reset.sh":
        "/mnt/dados/Projetos/1_Scripts/Audio-Reset/audio-reset.sh",
}
