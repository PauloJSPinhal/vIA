"""Provedores compatíveis com a API OpenAI (Groq e DeepSeek)."""

from via.providers.base import ErroProvider, requisicao_json

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
DEEPSEEK_MODELS_URL = "https://api.deepseek.com/models"


def listar_modelos(url: str, api_key: str, timeout: int = 8) -> list[dict]:
    """Lista os modelos disponíveis num endpoint compatível com OpenAI."""
    if not api_key:
        raise ErroProvider("Chave API em falta para listar os modelos.")

    dados = requisicao_json(
        url, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout
    )
    itens = dados.get("data") if isinstance(dados, dict) else None
    if not isinstance(itens, list):
        raise ErroProvider("Resposta inesperada ao listar os modelos.")

    modelos = []
    for item in itens:
        if not isinstance(item, dict) or item.get("active") is False:
            continue
        modelo_id = item.get("id")
        if not isinstance(modelo_id, str) or not modelo_id:
            continue
        dono = item.get("owned_by")
        modelos.append({
            "id": modelo_id,
            "dono": dono if isinstance(dono, str) else "",
        })

    return sorted(modelos, key=lambda m: m["id"])


def chamar(url: str, api_key: str, modelo: str, prompt_sistema: str,
           prompt_utilizador: str, imagens: list[dict], config: dict) -> str:
    if not api_key:
        raise ErroProvider(f"Chave API em falta para o modelo '{modelo}'.")

    if imagens:
        conteudo_utilizador = [{"type": "text", "text": prompt_utilizador}]
        for img in imagens:
            conteudo_utilizador.append({
                "type": "image_url",
                "image_url": {"url": f"data:{img['mime']};base64,{img['b64']}"},
            })
    else:
        conteudo_utilizador = prompt_utilizador

    payload = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": conteudo_utilizador},
        ],
        "temperature": config.get("temperatura", 0.3),
    }
    if "reasoner" not in modelo.lower():
        payload["response_format"] = {"type": "json_object"}

    dados = requisicao_json(
        url,
        payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=config.get("timeout", 90),
    )

    try:
        texto = dados["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ErroProvider(f"O serviço de '{modelo}' devolveu uma resposta sem conteúdo.") from exc

    if not isinstance(texto, str) or not texto.strip():
        raise ErroProvider(f"O serviço de '{modelo}' devolveu uma resposta vazia.")
    return texto
