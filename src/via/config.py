"""Persistência de configuração e catálogo de scripts.

Todos os ficheiros vivem em ``~/.config/via/`` (ou ``$XDG_CONFIG_HOME/via``).
Inclui migração automática da pasta antiga ``~/.config/assistente``.
"""

import json
import os
import re
import shutil
from pathlib import Path

from via import constants as C


# ---------------------------------------------------------------------------
# Normalização e validação
# ---------------------------------------------------------------------------
def normalizar_modelo(modelo) -> str:
    """Garante que o modelo tem provedor explícito.

    Um valor vazio é permitido: significa que ainda não foi descoberto ou
    escolhido nenhum modelo.
    """
    valor = (modelo or "").strip()
    if not valor:
        return ""
    if valor.startswith(C.PREFIXOS_PROVEDOR):
        return valor
    return f"ollama:{valor}"


def normalizar_config(cfg: dict) -> dict:
    """Aplica valores por omissão e corrige tipos fora do intervalo."""
    resultado = {**C.DEFAULT_CONFIG, **(cfg or {})}

    resultado["modelo"] = normalizar_modelo(resultado.get("modelo"))

    try:
        temperatura = float(resultado.get("temperatura", C.DEFAULT_CONFIG["temperatura"]))
    except (TypeError, ValueError):
        temperatura = C.DEFAULT_CONFIG["temperatura"]
    resultado["temperatura"] = round(min(max(temperatura, 0.0), 2.0), 2)

    try:
        timeout = int(resultado.get("timeout", C.DEFAULT_CONFIG["timeout"]))
    except (TypeError, ValueError):
        timeout = C.DEFAULT_CONFIG["timeout"]
    resultado["timeout"] = min(max(timeout, 10), 900)

    try:
        timeout_script = int(resultado.get("timeout_script", C.TIMEOUT_SCRIPT_PADRAO))
    except (TypeError, ValueError):
        timeout_script = C.TIMEOUT_SCRIPT_PADRAO
    resultado["timeout_script"] = min(max(timeout_script, 0), 3600)

    regras = resultado.get("regras")
    if not isinstance(regras, str) or not regras.strip():
        resultado["regras"] = C.DEFAULT_CONFIG["regras"]

    return resultado


def normalizar_script(info: dict) -> dict | None:
    """Valida uma entrada do catálogo; devolve ``None`` se for inválida."""
    if not isinstance(info, dict):
        return None

    caminho = str(info.get("caminho") or "").strip()
    if not caminho:
        return None

    # Corrige caminhos criados pelo valor por omissão errado de versões antigas,
    # mas apenas se o caminho corrigido existir e o antigo não existir.
    corrigido = C.CORRECOES_CAMINHOS_CONHECIDOS.get(caminho)
    if corrigido and not Path(caminho).expanduser().exists() and Path(corrigido).exists():
        caminho = corrigido

    return {
        "caminho": caminho,
        "descricao": str(info.get("descricao") or "").strip(),
        "args": bool(info.get("args", False)),
        "perigoso": bool(info.get("perigoso", False)),
    }


# ---------------------------------------------------------------------------
# Escrita atómica (evita ficheiros JSON truncados) sem segredos
# ---------------------------------------------------------------------------
# Chaves/passwords nunca são persistidas. A aplicação lê-as apenas do
# ambiente; esta lista é uma salvaguarda adicional caso algo tente escrevê-las.
CHAVES_SENSIVEIS = {
    "api_key", "apikey", "app_key", "appkey", "password", "passwd",
    "palavra_passe", "secret", "token", "access_token", "refresh_token",
}


def _remover_segredos(dados):
    """Remove recursivamente campos sensíveis antes de gravar em disco."""
    if isinstance(dados, dict):
        return {
            chave: _remover_segredos(valor)
            for chave, valor in dados.items()
            if str(chave).strip().lower() not in CHAVES_SENSIVEIS
        }
    if isinstance(dados, list):
        return [_remover_segredos(valor) for valor in dados]
    return dados


def _restringir_permissoes(caminho: Path) -> None:
    """Garante que ficheiros de configuração são privados (0600)."""
    try:
        os.chmod(caminho, 0o600)
    except OSError:
        pass


def _escrever_json(caminho: Path, dados) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_name(caminho.name + ".tmp")
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(_remover_segredos(dados), f, indent=4, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(temporario, 0o600)
    os.replace(temporario, caminho)
    _restringir_permissoes(caminho)


# ---------------------------------------------------------------------------
# Arranque / migração
# ---------------------------------------------------------------------------
def garantir_diretorio_config() -> None:
    C.CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(C.CONFIG_DIR, 0o700)
    except OSError:
        pass


def migrar_config_legada() -> list[str]:
    """Copia config/scripts de ``~/.config/assistente`` para ``~/.config/via``.

    Devolve a lista de ficheiros migrados. Não apaga a pasta antiga: o
    utilizador decide isso no desinstalador.
    """
    legado = C.CONFIG_LEGADO_DIR
    if not legado.is_dir():
        return []

    garantir_diretorio_config()
    migrados = []
    for nome in ("config.json", "scripts.json"):
        origem = legado / nome
        destino = C.CONFIG_DIR / nome
        if origem.is_file() and not destino.exists():
            try:
                shutil.copy2(origem, destino)
                _restringir_permissoes(destino)
                migrados.append(nome)
            except OSError:
                pass
    return migrados


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
def carregar_config() -> dict:
    garantir_diretorio_config()

    if not C.CONFIG_FILE.exists():
        config = normalizar_config(C.DEFAULT_CONFIG)
        guardar_config(config)
        return config

    _restringir_permissoes(C.CONFIG_FILE)

    try:
        with open(C.CONFIG_FILE, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except (json.JSONDecodeError, OSError):
        # Não destrói o ficheiro inválido: guarda uma cópia para diagnóstico.
        try:
            C.CONFIG_FILE.replace(C.CONFIG_FILE.with_suffix(".json.invalido"))
        except OSError:
            pass
        config = normalizar_config(C.DEFAULT_CONFIG)
        guardar_config(config)
        return config

    config = normalizar_config(dados)
    # Re-grava apenas se a normalização alterou algo (ex.: modelo obsoleto).
    if config != {**C.DEFAULT_CONFIG, **dados}:
        guardar_config(config)
    return config


def guardar_config(cfg: dict) -> None:
    _escrever_json(C.CONFIG_FILE, normalizar_config(cfg))


# ---------------------------------------------------------------------------
# Catálogo de scripts
# ---------------------------------------------------------------------------
def carregar_scripts() -> dict:
    garantir_diretorio_config()

    if not C.SCRIPTS_FILE.exists():
        scripts = {nome: dict(info) for nome, info in C.DEFAULT_SCRIPTS.items()}
        guardar_scripts(scripts)
        return scripts

    _restringir_permissoes(C.SCRIPTS_FILE)

    try:
        with open(C.SCRIPTS_FILE, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(dados, dict):
        return {}

    limpos = {}
    for nome, info in dados.items():
        if not isinstance(nome, str) or not nome.strip():
            continue
        entrada = normalizar_script(info)
        if entrada is not None:
            limpos[nome.strip()] = entrada

    # Persiste correções/normalizações (ex.: caminho por omissão de versões antigas).
    if limpos != dados:
        guardar_scripts(limpos)

    return limpos


def guardar_scripts(scripts: dict) -> None:
    limpos = {}
    for nome, info in (scripts or {}).items():
        entrada = normalizar_script(info)
        if entrada is not None:
            limpos[nome] = entrada
    _escrever_json(C.SCRIPTS_FILE, limpos)


NOME_SCRIPT_VALIDO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def nome_script_valido(nome: str) -> bool:
    return bool(NOME_SCRIPT_VALIDO.match((nome or "").strip()))
