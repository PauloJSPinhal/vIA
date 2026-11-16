"""Provedor Ollama (modelos locais)."""

import json
import urllib.error
import urllib.request

from via import constants as C
from via.providers.base import ErroProvider, _mensagem_erro, requisicao_json


def listar_modelos_info() -> list[dict] | None:
    """Lista os modelos instalados localmente, com tamanho em disco.

    Devolve ``None`` quando o Ollama não está acessível, para distinguir de
    uma instalação válida sem modelos (lista vazia).
    """
    try:
        dados = requisicao_json(f"{C.OLLAMA_BASE_URL}/api/tags", timeout=C.DESCOBERTA_TIMEOUT)
    except ErroProvider:
        return None

    if not isinstance(dados, dict):
        return None

    modelos = []
    for item in dados.get("models", []):
        if not isinstance(item, dict):
            continue
        nome = item.get("name")
        if not isinstance(nome, str) or not nome:
            continue
        tamanho = item.get("size")
        detalhe = (
            f"{tamanho / (1024 ** 3):.1f} GB"
            if isinstance(tamanho, (int, float)) and tamanho > 0
            else ""
        )
        modelos.append({"id": nome, "detalhe": detalhe})

    return sorted(modelos, key=lambda m: m["id"])


def chamar(modelo: str, prompt: str, imagens: list[dict], config: dict) -> str:
    """Envia um pedido de geração e devolve o texto bruto do modelo."""
    payload = {
        "model": modelo,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": config.get("temperatura", 0.3),
            "repeat_penalty": 1.2,
        },
    }
    # O DeepSeek-R1 não suporta o modo JSON forçado.
    if "deepseek-r1" not in modelo.lower():
        payload["format"] = "json"
    if imagens:
        payload["images"] = [img["b64"] for img in imagens]

    dados = requisicao_json(
        f"{C.OLLAMA_BASE_URL}/api/generate",
        payload,
        timeout=config.get("timeout", 90),
    )

    resposta = dados.get("response", "")
    if not isinstance(resposta, str):
        raise ErroProvider("O Ollama devolveu uma resposta num formato inesperado.")
    return resposta


def iterar_instalacao(nome_modelo: str):
    """Gera eventos do ``/api/pull`` à medida que o download progride."""
    payload = json.dumps({"name": nome_modelo, "stream": True}).encode("utf-8")
    req = urllib.request.Request(
        f"{C.OLLAMA_BASE_URL}/api/pull",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            for linha in resp:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    evento = json.loads(linha.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                if isinstance(evento, dict):
                    yield evento
    except urllib.error.HTTPError as exc:
        detalhe = _mensagem_erro(exc.read().decode("utf-8", errors="replace"))
        raise ErroProvider(f"Erro HTTP {exc.code} ao instalar '{nome_modelo}': {detalhe}") from exc
    except urllib.error.URLError as exc:
        raise ErroProvider(
            f"Ollama não acessível em {C.OLLAMA_BASE_URL}: {exc.reason}"
        ) from exc
    except OSError as exc:
        raise ErroProvider(f"Falha de rede ao instalar '{nome_modelo}': {exc}") from exc
