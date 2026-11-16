"""Threads de trabalho: descoberta de modelos, pedidos à IA e downloads."""

from PySide6.QtCore import QThread, Signal

from via.config import normalizar_modelo
from via.discovery import descobrir_modelos
from via.parsers.anexos import preparar_anexos
from via.prompt import construir_prompt_sistema, construir_prompt_utilizador
from via.providers import gemini, ollama, openai_compat
from via.providers.base import ErroProvider
from via.respostas import extrair_json_resposta, suporta_visao


class DescobertaModelosWorker(QThread):
    """Descobre modelos locais e externos sem bloquear a interface."""

    concluido = Signal(object, object)  # list[ModeloDisponivel], list[str]

    def __init__(self, chaves: dict, parent=None):
        super().__init__(parent)
        self.chaves = dict(chaves or {})

    def run(self):
        try:
            modelos, avisos = descobrir_modelos(self.chaves)
        except Exception as exc:  # salvaguarda: nunca deixar a UI pendurada
            modelos, avisos = [], [f"Erro ao descobrir modelos: {exc}"]
        self.concluido.emit(modelos, avisos)


class PullModeloWorker(QThread):
    """Descarrega um modelo Ollama em streaming."""

    progresso = Signal(str)
    concluido = Signal(bool, str)

    def __init__(self, nome_modelo: str, parent=None):
        super().__init__(parent)
        self.nome_modelo = nome_modelo.replace("ollama:", "").strip()
        self._cancelar = False

    def cancelar(self):
        self._cancelar = True

    def run(self):
        ultimo_status = ""
        try:
            for evento in ollama.iterar_instalacao(self.nome_modelo):
                if self._cancelar:
                    self.concluido.emit(False, "Instalação cancelada pelo utilizador.")
                    return
                if "error" in evento:
                    self.concluido.emit(False, str(evento["error"]))
                    return

                status = str(evento.get("status", ""))
                total = evento.get("total") or 0
                completo = evento.get("completed") or 0
                msg = f"{status}: {int(completo / total * 100)}%" if total else status
                if msg and msg != ultimo_status:
                    self.progresso.emit(msg)
                    ultimo_status = msg

            self.concluido.emit(True, f"ollama:{self.nome_modelo}")
        except ErroProvider as exc:
            self.concluido.emit(False, str(exc))
        except Exception as exc:  # rede/stream inesperado
            self.concluido.emit(False, f"Erro inesperado ao instalar o modelo: {exc}")


class AssistenteWorker(QThread):
    """Prepara anexos, constrói o prompt e chama o provedor ativo."""

    resultado_pronto = Signal(dict)
    erro_ocorrido = Signal(str)
    aviso = Signal(str)

    def __init__(self, pedido, anexos, scripts, config, hardware_info, chaves, parent=None):
        super().__init__(parent)
        self.pedido = pedido
        self.anexos = anexos
        self.scripts = scripts
        self.config = config
        self.hardware_info = hardware_info
        self.chaves = chaves

    def run(self):
        try:
            if self.isInterruptionRequested():
                return

            imagens, bloco_anexos, avisos = preparar_anexos(self.anexos)
            for aviso in avisos:
                self.aviso.emit(aviso)

            modelo_completo = normalizar_modelo(self.config.get("modelo"))
            if not modelo_completo:
                self.erro_ocorrido.emit(
                    "Nenhum modelo selecionado. Abre Configurações, clica em "
                    "'Atualizar Modelos' e escolhe um modelo disponível."
                )
                return

            provedor, nome_modelo = modelo_completo.split(":", 1)

            if imagens and not suporta_visao(provedor, nome_modelo):
                self.erro_ocorrido.emit(
                    f"O modelo ativo '{modelo_completo}' não suporta análise de imagens. "
                    "Escolhe um modelo com visão (Gemini, Groq multimodal ou Ollama 'vl')."
                )
                return

            prompt_sistema = construir_prompt_sistema(
                regras=self.config["regras"],
                hardware=self.hardware_info,
                modelo_ativo=modelo_completo,
                scripts=self.scripts,
            )
            prompt_utilizador = construir_prompt_utilizador(self.pedido, bloco_anexos)

            if self.isInterruptionRequested():
                return

            if provedor == "ollama":
                texto = ollama.chamar(
                    nome_modelo,
                    f"{prompt_sistema}\n\nPedido do utilizador:\n{prompt_utilizador}",
                    imagens,
                    self.config,
                )
            elif provedor == "gemini":
                texto = gemini.chamar(
                    nome_modelo,
                    self.chaves.get("GEMINI_API_KEY"),
                    prompt_sistema,
                    prompt_utilizador,
                    imagens,
                    self.config,
                )
            elif provedor == "groq":
                texto = openai_compat.chamar(
                    openai_compat.GROQ_URL,
                    self.chaves.get("GROQ_API_KEY"),
                    nome_modelo,
                    prompt_sistema,
                    prompt_utilizador,
                    imagens,
                    self.config,
                )
            elif provedor == "deepseek":
                texto = openai_compat.chamar(
                    openai_compat.DEEPSEEK_URL,
                    self.chaves.get("DEEPSEEK_API_KEY"),
                    nome_modelo,
                    prompt_sistema,
                    prompt_utilizador,
                    [],
                    self.config,
                )
            else:
                raise ErroProvider(f"Provedor desconhecido: {provedor}")

            self.resultado_pronto.emit(extrair_json_resposta(texto))

        except ErroProvider as exc:
            self.erro_ocorrido.emit(str(exc))
        except Exception as exc:  # salvaguarda: nunca deixar a UI pendurada
            self.erro_ocorrido.emit(f"Erro inesperado: {exc}")
