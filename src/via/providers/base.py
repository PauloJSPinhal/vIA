"""Utilitários HTTP partilhados pelos provedores de modelos."""

import json
import socket
import urllib.error
import urllib.request

from via import constants as C


class ErroProvider(Exception):
    """Erro legível para apresentar ao utilizador."""


def _mensagem_erro(corpo: str) -> str:
    """Extrai a mensagem útil de um corpo de erro HTTP (JSON ou texto)."""
    texto = (corpo or "").strip()
    try:
        dados = json.loads(texto)
    except (json.JSONDecodeError, TypeError):
        return texto[:400] or "sem detalhes"

    if isinstance(dados, dict):
        erro = dados.get("error")
        if isinstance(erro, dict):
            return str(erro.get("message") or erro)[:400]
        if erro:
            return str(erro)[:400]
        for chave in ("message", "detail", "msg"):
            if dados.get(chave):
                return str(dados[chave])[:400]
    return texto[:400]


def requisicao_json(url: str, payload=None, headers: dict | None = None,
                    timeout: int = 90) -> dict:
    """Faz um pedido HTTP e devolve o JSON da resposta.

    Converte erros de rede/HTTP em :class:`ErroProvider` com mensagens em
    português, para que a interface nunca mostre exceções cruas.
    """
    dados = None if payload is None else json.dumps(payload).encode("utf-8")
    cabecalhos = {
        "Content-Type": "application/json",
        "User-Agent": f"{C.APP_NOME}/{C.APP_VERSAO}",
    }
    cabecalhos.update(headers or {})

    req = urllib.request.Request(url, data=dados, headers=cabecalhos)
    destino = url.split("?", 1)[0]

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            bruto = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detalhe = _mensagem_erro(exc.read().decode("utf-8", errors="replace"))
        if exc.code in (401, 403):
            detalhe += " (verifica se a chave API está correta e ativa)"
        elif exc.code == 404:
            detalhe += " (o modelo ou o endpoint pode já não existir)"
        elif exc.code == 429:
            detalhe += " (limite de utilização atingido; tenta novamente mais tarde)"
        raise ErroProvider(f"Erro HTTP {exc.code} em {destino}: {detalhe}") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise ErroProvider(
                f"Tempo limite excedido ({timeout}s) ao contactar {destino}."
            ) from exc
        raise ErroProvider(f"Não foi possível contactar {destino}: {exc.reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise ErroProvider(f"Tempo limite excedido ({timeout}s) ao contactar {destino}.") from exc
    except OSError as exc:
        raise ErroProvider(f"Falha de rede ao contactar {destino}: {exc}") from exc

    try:
        return json.loads(bruto)
    except json.JSONDecodeError as exc:
        raise ErroProvider(f"A resposta de {destino} não é JSON válido.") from exc
