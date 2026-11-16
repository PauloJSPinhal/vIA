"""Descoberta dinâmica dos modelos realmente disponíveis.

Fontes consultadas em paralelo:
  * Ollama local: ``/api/tags`` (modelos instalados);
  * Gemini: ``GET /v1beta/models`` (apenas métodos ``generateContent``);
  * Groq e DeepSeek: ``GET /models`` (formato OpenAI).

Nenhum modelo está codificado na aplicação. A lista é reconstruída no
arranque e sempre que o utilizador clica em "Atualizar Modelos".
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from via import constants as C
from via.providers import gemini, ollama, openai_compat
from via.providers.base import ErroProvider

# Modelos que não servem para conversação/JSON por provedor.
PALAVRAS_IGNORADAS = {
    "gemini": ("image", "tts", "embedding", "aqa", "audio", "live"),
    "groq": ("whisper", "tts", "guard", "embed", "rerank", "orpheus", "moderation"),
    "deepseek": (),
}


@dataclass(frozen=True)
class ModeloDisponivel:
    modelo_id: str
    nome: str
    provedor: str
    detalhe: str = ""

    @property
    def rotulo(self) -> str:
        """Texto apresentado no seletor de modelos."""
        prefixo = C.NOMES_PROVEDORES.get(self.provedor, self.provedor.title())

        if self.provedor == "gemini":
            texto = self.nome or self.modelo_id
            if self.nome and self.nome != self.modelo_id:
                texto = f"{texto} ({self.modelo_id})"
        elif self.provedor == "ollama":
            texto = self.modelo_id.split(":", 1)[-1]
        else:
            texto = self.modelo_id

        if self.detalhe:
            texto = f"{texto} — {self.detalhe}"
        return f"[{prefixo}] {texto}"


def _tarefas_externas(chaves: dict) -> dict:
    """Constrói as chamadas de listagem para as chaves presentes no ambiente."""
    tarefas = {}

    chave = C.PROVEDORES_EXTERNOS["gemini"]
    if chaves.get(chave):
        tarefas["gemini"] = (gemini.listar_modelos, (chaves[chave],))

    chave = C.PROVEDORES_EXTERNOS["groq"]
    if chaves.get(chave):
        tarefas["groq"] = (
            openai_compat.listar_modelos,
            (openai_compat.GROQ_MODELS_URL, chaves[chave]),
        )

    chave = C.PROVEDORES_EXTERNOS["deepseek"]
    if chaves.get(chave):
        tarefas["deepseek"] = (
            openai_compat.listar_modelos,
            (openai_compat.DEEPSEEK_MODELS_URL, chaves[chave]),
        )

    return tarefas


def descobrir_modelos(chaves: dict) -> tuple[list[ModeloDisponivel], list[str]]:
    """Constrói a lista de modelos disponíveis e os avisos de falha."""
    chaves = chaves or {}
    avisos: list[str] = []
    resultados: dict = {}

    with ThreadPoolExecutor(max_workers=4) as pool:
        futuros = {"ollama": pool.submit(ollama.listar_modelos_info)}
        for provedor, (funcao, argumentos) in _tarefas_externas(chaves).items():
            futuros[provedor] = pool.submit(
                funcao, *argumentos, timeout=C.DESCOBERTA_TIMEOUT
            )

        for provedor, futuro in futuros.items():
            etiqueta = C.NOMES_PROVEDORES.get(provedor, provedor.title())
            try:
                resultados[provedor] = futuro.result()
            except ErroProvider as exc:
                avisos.append(f"{etiqueta}: {exc}")
            except Exception as exc:  # salvaguarda
                avisos.append(f"{etiqueta}: erro inesperado: {exc}")

    modelos: list[ModeloDisponivel] = []

    locais = resultados.get("ollama")
    if locais is None:
        avisos.append(f"Ollama não está acessível em {C.OLLAMA_BASE_URL}.")
    else:
        for item in locais:
            modelos.append(ModeloDisponivel(
                modelo_id=f"ollama:{item['id']}",
                nome=item["id"],
                provedor="ollama",
                detalhe=str(item.get("detalhe") or ""),
            ))

    for provedor in ("gemini", "groq", "deepseek"):
        lista = resultados.get(provedor)
        if not lista:
            continue
        for item in lista:
            if any(
                palavra in item["id"].lower()
                for palavra in PALAVRAS_IGNORADAS.get(provedor, ())
            ):
                continue
            nome = str(item.get("nome") or item["id"])
            modelos.append(ModeloDisponivel(
                modelo_id=f"{provedor}:{item['id']}",
                nome=nome,
                provedor=provedor,
                detalhe=str(item.get("dono") or ""),
            ))

    return modelos, avisos
