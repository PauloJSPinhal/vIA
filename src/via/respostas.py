"""Interpretação de respostas dos modelos e capacidades dos mesmos."""

import json
import re

ACOES_VALIDAS = ("executar", "conversar")

DECISAO_BASE = {
    "acao": "conversar",
    "script": None,
    "argumento": "",
    "resposta": "",
}


def limpar_texto_modelo(texto: str) -> str:
    """Remove blocos de raciocínio e cercas markdown que envolvem o JSON."""
    if not texto:
        return ""
    limpo = re.sub(r"<think(?:ing)?>.*?</think(?:ing)?>", "", texto, flags=re.DOTALL | re.IGNORECASE)
    limpo = limpo.strip()
    limpo = re.sub(r"^```(?:json)?\s*", "", limpo, flags=re.IGNORECASE)
    limpo = re.sub(r"\s*```$", "", limpo)
    return limpo.strip()


def _procurar_objeto_json(texto: str):
    """Fallback: extrai o primeiro objeto JSON embutido em texto livre."""
    profundidade = 0
    inicio = None
    for i, ch in enumerate(texto):
        if ch == "{":
            if profundidade == 0:
                inicio = i
            profundidade += 1
        elif ch == "}":
            if profundidade > 0:
                profundidade -= 1
                if profundidade == 0 and inicio is not None:
                    try:
                        return json.loads(texto[inicio:i + 1])
                    except json.JSONDecodeError:
                        inicio = None
    return None


def extrair_json_resposta(texto: str) -> dict:
    """Converte a resposta do modelo numa decisão normalizada.

    Nunca lança exceção: se o modelo responder texto livre, devolve uma
    decisão de conversa com esse texto em ``resposta``.
    """
    limpo = limpar_texto_modelo(texto)

    dados = None
    try:
        dados = json.loads(limpo)
    except (json.JSONDecodeError, TypeError):
        dados = _procurar_objeto_json(limpo)

    if not isinstance(dados, dict):
        return {**DECISAO_BASE, "resposta": limpo}

    decisao = {**DECISAO_BASE, **dados}

    if decisao.get("acao") not in ACOES_VALIDAS:
        decisao["acao"] = "conversar"

    valor = decisao.get("script")
    decisao["script"] = valor.strip() if isinstance(valor, str) and valor.strip() else None

    for campo in ("argumento", "resposta"):
        valor = decisao.get(campo)
        if valor is None:
            decisao[campo] = ""
        elif not isinstance(valor, str):
            decisao[campo] = json.dumps(valor, ensure_ascii=False)

    return decisao


def suporta_visao(provedor: str, nome_modelo: str) -> bool:
    """Indica se o modelo ativo consegue receber imagens.

    Como os modelos são descobertos em runtime, a capacidade é inferida pelo
    nome. Todos os modelos Gemini ``generateContent`` aceitam imagens.
    """
    nome = (nome_modelo or "").lower()
    if provedor == "gemini":
        return True
    if provedor == "groq":
        return any(k in nome for k in ("vision", "vl", "llama-4", "qwen3", "muse-spark"))
    if provedor == "ollama":
        return any(k in nome for k in ("vl", "vision", "llava", "minicpm", "moondream", "gemma3"))
    return False
