"""Provedor Google Gemini."""

from via.providers.base import ErroProvider, requisicao_json

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def listar_modelos(api_key: str, timeout: int = 8) -> list[dict]:
    """Lista os modelos que suportam ``generateContent`` nesta chave."""
    if not api_key:
        raise ErroProvider("Variável de ambiente GEMINI_API_KEY não encontrada.")

    dados = requisicao_json(BASE_URL, headers={"x-goog-api-key": api_key}, timeout=timeout)
    itens = dados.get("models") if isinstance(dados, dict) else None
    if not isinstance(itens, list):
        raise ErroProvider("Resposta inesperada ao listar os modelos Gemini.")

    modelos = []
    for item in itens:
        if not isinstance(item, dict):
            continue
        metodos = item.get("supportedGenerationMethods") or []
        if "generateContent" not in metodos:
            continue
        nome = str(item.get("name") or "").removeprefix("models/")
        if not nome:
            continue
        modelos.append({
            "id": nome,
            "nome": str(item.get("displayName") or nome),
        })

    return sorted(modelos, key=lambda m: m["id"])


def chamar(modelo: str, api_key: str, prompt_sistema: str,
           prompt_utilizador: str, imagens: list[dict], config: dict) -> str:
    if not api_key:
        raise ErroProvider("Variável de ambiente GEMINI_API_KEY não encontrada.")

    parts = [{"text": f"{prompt_sistema}\n\nPedido do utilizador:\n{prompt_utilizador}"}]
    for img in imagens:
        parts.append({
            "inline_data": {
                "mime_type": img["mime"],
                "data": img["b64"],
            }
        })

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": config.get("temperatura", 0.3),
            "responseMimeType": "application/json",
        },
    }

    # A chave vai no cabeçalho (e não na query string) para não ficar
    # registada em logs, proxies ou histórico de pedidos.
    dados = requisicao_json(
        f"{BASE_URL}/{modelo}:generateContent",
        payload,
        headers={"x-goog-api-key": api_key},
        timeout=config.get("timeout", 90),
    )

    try:
        partes = dados["candidates"][0]["content"]["parts"]
        texto = "".join(p.get("text", "") for p in partes if isinstance(p, dict))
    except (KeyError, IndexError, TypeError) as exc:
        motivo = (dados.get("promptFeedback") or {}).get("blockReason")
        if motivo:
            raise ErroProvider(f"O Gemini bloqueou a resposta (motivo: {motivo}).") from exc
        raise ErroProvider("O Gemini devolveu uma resposta sem conteúdo.") from exc

    if not texto.strip():
        raise ErroProvider("O Gemini devolveu uma resposta vazia.")
    return texto
