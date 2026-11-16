#!/usr/bin/env python3
import sys
import os
import re
import json
import base64
import shutil
import mimetypes
import subprocess
import urllib.request
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTextEdit, QLineEdit, QPushButton, QLabel,
    QListWidget, QFormLayout, QCheckBox, QFileDialog, QMessageBox,
    QFrame, QSplitter, QComboBox, QDoubleSpinBox, QSpinBox
)
from PySide6.QtCore import Qt, QThread, Signal, QProcess
from PySide6.QtGui import QFont

OLLAMA_BASE_URL = "http://localhost:11434"
CONFIG_DIR = Path.home() / ".config" / "assistente"
CONFIG_FILE = CONFIG_DIR / "config.json"
SCRIPTS_FILE = CONFIG_DIR / "scripts.json"

MODELO_BASE_INICIAL = "ollama:qwen2.5:0.5b"

MODELOS_EXTERNOS_DISPONIVEIS = {
    "GEMINI_API_KEY": [
        ("gemini:gemini-2.5-flash", "Gemini 2.5 Flash (Visão + Texto - Rápido)"),
        ("gemini:gemini-2.5-pro", "Gemini 2.5 Pro (Visão + Raciocínio Avançado)")
    ],
    "GROQ_API_KEY": [
        ("groq:llama-3.2-90b-vision-preview", "Groq Llama 3.2 90B Vision (Visão + Texto)"),
        ("groq:llama-3.2-11b-vision-preview", "Groq Llama 3.2 11B Vision (Visão + Texto Rápido)"),
        ("groq:llama-3.3-70b-versatile", "Groq Llama 3.3 70B (Apenas Texto)")
    ],
    "DEEPSEEK_API_KEY": [
        ("deepseek:deepseek-chat", "DeepSeek Chat V3 (Texto / Código)"),
        ("deepseek:deepseek-reasoner", "DeepSeek R1 Reasoner (Raciocínio Complexo)")
    ]
}

DEFAULT_CONFIG = {
    "modelo": MODELO_BASE_INICIAL,
    "temperatura": 0.3,
    "timeout": 90,
    "regras": (
        "És um assistente de terminal Linux útil e direto. Comunicas sempre em português de Portugal.\n"
        "1. Se o pedido (ou os ficheiros anexados) corresponder à execução de um dos scripts locais disponíveis, "
        "define \"acao\": \"executar\", indica o nome exato do script e extrai o argumento (como o caminho do ficheiro).\n"
        "2. Se o utilizador perguntar qual o melhor modelo Ollama local para esta máquina ou pedir para instalar um modelo local, "
        "analisa o hardware e define \"acao\": \"instalar_modelo\" com uma tag exata do catálogo local.\n"
        "3. Se o utilizador anexar imagens, PDFs ou ficheiros de texto/código para analisar, responde de forma clara, "
        "técnica e estruturada sobre o conteúdo desses ficheiros.\n"
        "4. Para qualquer outra pergunta ou conversa, responde de forma útil, natural e variada."
    )
}

DEFAULT_SCRIPTS = {
    "audio-reset": {
        "caminho": "/mnt/dados/Projetos/1_Scripts/Audio-Reset/src/audio-reset.sh",
        "descricao": "Reinicia o servidor de som (WirePlumber/PipeWire) quando o áudio encrava ou deixa de dar.",
        "args": False,
        "perigoso": False
    }
}

GUIA_MODELOS_HARDWARE = """
Catálogo de referência de modelos Ollama locais (usa APENAS estas tags exatas se recomendares instalação local):
- qwen2.5:0.5b (~400 MB RAM): Máquinas muito fracas (<= 4 GB RAM). Router básico.
- llama3.2:1b (~1.3 GB RAM): Máquinas de 4 a 8 GB RAM. Boa fluidez em português.
- qwen2.5-coder:1.5b (~1.1 GB RAM): Máquinas de 8 GB RAM sem GPU. Melhor equilíbrio para Bash e Python.
- qwen2.5-coder:3b (~2.0 GB RAM): Portáteis com 8 a 16 GB RAM. Superior em código e raciocínio.
- qwen2.5vl:3b (~2.5 GB RAM): Modelo local leve com suporte a análise de imagens.
- qwen2.5-coder:7b (~4.7 GB RAM/VRAM): Workstations (>= 16 GB RAM ou GPU dedicada). Programação avançada.
- deepseek-r1:7b (~4.7 GB RAM/VRAM): Workstations (>= 16 GB RAM ou GPU dedicada). Raciocínio lógico.
"""


# --- Diagnóstico de Hardware e Chaves ---
def obter_info_hardware():
    ram_total_gb = 0.0
    ram_disp_gb = 0.0
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for linha in f:
                if linha.startswith("MemTotal:"):
                    ram_total_gb = round(int(linha.split()[1]) / (1024 * 1024), 1)
                elif linha.startswith("MemAvailable:"):
                    ram_disp_gb = round(int(linha.split()[1]) / (1024 * 1024), 1)
    except Exception:
        pass

    cpu_modelo = "Desconhecido"
    cpu_cores = os.cpu_count() or 1
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
            for linha in f:
                if "model name" in linha:
                    bruto = linha.split(":", 1)[1].strip()
                    limpo = re.sub(r"\(R\)|\(TM\)|\bCPU\b", "", bruto)
                    cpu_modelo = re.sub(r"\s+", " ", limpo).strip()
                    break
    except Exception:
        pass

    gpu_info = "Sem GPU dedicada (apenas CPU)"
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                text=True, timeout=3
            ).strip()
            if out:
                partes = [p.strip() for p in out.split(",")]
                nome_gpu = partes[0] if partes[0].startswith("NVIDIA") else f"NVIDIA {partes[0]}"
                vram = partes[1] if len(partes) > 1 else ""
                gpu_info = f"{nome_gpu} ({vram})" if vram else nome_gpu
        except Exception:
            pass

    return (
        f"CPU: {cpu_modelo} ({cpu_cores} threads) | "
        f"RAM: {ram_disp_gb} GB livres / {ram_total_gb} GB total | "
        f"GPU: {gpu_info}"
    )


def obter_modelos_ollama():
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=3) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
            return [m["name"] for m in dados.get("models", [])]
    except Exception:
        return []


def detetar_chaves_ambiente():
    estado = {}
    for chave in ["GEMINI_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY"]:
        val = os.environ.get(chave, "").strip()
        estado[chave] = val if val else None
    return estado


# --- Leitura e Preparação de Ficheiros Anexados ---
def preparar_anexos(caminhos):
    imagens = []
    textos_anexos = []

    for caminho_str in caminhos:
        p = Path(caminho_str)
        if not p.exists() or not p.is_file():
            continue

        ext = p.suffix.lower()
        mime, _ = mimetypes.guess_type(str(p))

        # 1. Imagens
        if ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"] or (mime and mime.startswith("image/")):
            mime_final = mime if mime else "image/jpeg"
            with open(p, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            imagens.append({
                "nome": p.name,
                "caminho": str(p),
                "mime": mime_final,
                "b64": b64
            })
            textos_anexos.append(f"[Imagem anexada: {p.name} | Caminho: {p}]")

        # 2. PDFs (tenta pdftotext nativo ou pypdf)
        elif ext == ".pdf":
            conteudo_pdf = ""
            if shutil.which("pdftotext"):
                try:
                    conteudo_pdf = subprocess.check_output(
                        ["pdftotext", "-layout", str(p), "-"],
                        text=True, stderr=subprocess.DEVNULL, timeout=15
                    )
                except Exception:
                    pass
            if not conteudo_pdf:
                try:
                    import pypdf
                    reader = pypdf.PdfReader(str(p))
                    conteudo_pdf = "\n".join(page.extract_text() or "" for page in reader.pages)
                except Exception:
                    conteudo_pdf = "(Não foi possível extrair texto deste PDF — pode ser um PDF digitalizado como imagem)."

            textos_anexos.append(
                f"--- Conteúdo do PDF '{p.name}' (Caminho: {p}) ---\n{conteudo_pdf[:25000]}\n--- Fim do PDF ---"
            )

        # 3. Ficheiros de texto, código, logs, CSV, JSON, etc.
        else:
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    conteudo = f.read(30000)
                textos_anexos.append(
                    f"--- Conteúdo do ficheiro '{p.name}' (Caminho: {p}) ---\n{conteudo}\n--- Fim do ficheiro ---"
                )
            except Exception as e:
                textos_anexos.append(f"[Ficheiro '{p.name}' (Caminho: {p}) - erro ao ler: {e}]")

    return imagens, "\n\n".join(textos_anexos)


# --- Persistência em ~/.config/assistente/ ---
def garantir_diretorio_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def carregar_config():
    garantir_diretorio_config()
    if not CONFIG_FILE.exists():
        guardar_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = {**DEFAULT_CONFIG, **json.load(f)}
            # Migração suave caso o modelo antigo não tenha prefixo
            if ":" in cfg["modelo"] and not cfg["modelo"].startswith(("ollama:", "gemini:", "groq:", "deepseek:")):
                cfg["modelo"] = f"ollama:{cfg['modelo']}"
            return cfg
    except Exception:
        return DEFAULT_CONFIG.copy()


def guardar_config(cfg):
    garantir_diretorio_config()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)


def carregar_scripts():
    garantir_diretorio_config()
    if not SCRIPTS_FILE.exists():
        guardar_scripts(DEFAULT_SCRIPTS)
        return DEFAULT_SCRIPTS.copy()
    try:
        with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_SCRIPTS.copy()


def guardar_scripts(scripts):
    garantir_diretorio_config()
    with open(SCRIPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(scripts, f, indent=4, ensure_ascii=False)


# --- Worker para Pull / Instalação de Modelos Ollama ---
class PullModeloWorker(QThread):
    progresso = Signal(str)
    concluido = Signal(bool, str)

    def __init__(self, nome_modelo):
        super().__init__()
        self.nome_modelo = nome_modelo.replace("ollama:", "")

    def run(self):
        try:
            payload = json.dumps({"name": self.nome_modelo, "stream": True}).encode("utf-8")
            req = urllib.request.Request(
                f"{OLLAMA_BASE_URL}/api/pull",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            ultimo_status = ""
            with urllib.request.urlopen(req, timeout=600) as resp:
                for linha in resp:
                    if not linha:
                        continue
                    evento = json.loads(linha.decode("utf-8"))
                    if "error" in evento:
                        self.concluido.emit(False, evento["error"])
                        return
                    status = evento.get("status", "")
                    total = evento.get("total", 0)
                    completed = evento.get("completed", 0)
                    if total > 0:
                        pct = int((completed / total) * 100)
                        msg = f"{status}: {pct}%"
                    else:
                        msg = status
                    if msg and msg != ultimo_status:
                        self.progresso.emit(msg)
                        ultimo_status = msg
            self.concluido.emit(True, f"ollama:{self.nome_modelo}")
        except Exception as e:
            self.concluido.emit(False, str(e))


# --- Worker Unificado (Ollama Local + Gemini / Groq / DeepSeek) ---
class AssistenteWorker(QThread):
    resultado_pronto = Signal(dict)
    erro_ocorrido = Signal(str)

    def __init__(self, pedido, anexos, scripts, config, hardware_info, modelos_ollama, chaves):
        super().__init__()
        self.pedido = pedido
        self.anexos = anexos
        self.scripts = scripts
        self.config = config
        self.hardware_info = hardware_info
        self.modelos_ollama = modelos_ollama
        self.chaves = chaves

    def extrair_json_resposta(self, texto):
        # Remove blocos <think> do DeepSeek-R1 se existirem
        limpo = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL).strip()
        # Remove marcadores markdown ```json ... ```
        limpo = re.sub(r"^```(?:json)?\s*|\s*```$", "", limpo, flags=re.MULTILINE).strip()
        try:
            return json.loads(limpo)
        except Exception:
            # Fallback caso o modelo responda texto livre
            return {
                "acao": "conversar",
                "script": None,
                "argumento": "",
                "modelo_recomendado": None,
                "resposta": limpo
            }

    def run(self):
        try:
            imagens, bloco_anexos = preparar_anexos(self.anexos)
            modelo_completo = self.config["modelo"]

            if ":" in modelo_completo:
                provedor, nome_modelo = modelo_completo.split(":", 1)
            else:
                provedor, nome_modelo = "ollama", modelo_completo

            # Validação de suporte a imagem
            if imagens:
                suporta_visao = (
                    provedor in ["gemini", "groq"] and "vision" in nome_modelo or provedor == "gemini"
                ) or (
                    provedor == "ollama" and any(k in nome_modelo.lower() for k in ["vl", "vision", "llava", "minicpm"])
                )
                if not suporta_visao:
                    self.erro_ocorrido.emit(
                        f"O modelo ativo '{modelo_completo}' não suporta análise de imagens. "
                        "Muda para um modelo Gemini (ex: gemini:gemini-2.5-flash), Groq Vision ou Ollama 'qwen2.5vl:3b' nas Configurações."
                    )
                    return

            catalogo_texto = "\n".join(
                [f"- {nome}: {info['descricao']}" for nome, info in self.scripts.items()]
            ) or "Nenhum script configurado."

            instalados_str = ", ".join(self.modelos_ollama) if self.modelos_ollama else "Nenhum detetado"

            prompt_sistema = f"""{self.config['regras']}

Informação desta máquina:
- Hardware: {self.hardware_info}
- Modelo ativo: {modelo_completo}
- Modelos Ollama instalados localmente: {instalados_str}

{GUIA_MODELOS_HARDWARE}

Scripts locais disponíveis:
{catalogo_texto}

Responde EXCLUSIVAMENTE em JSON válido com este formato exato:
{{
  "acao": "executar" ou "instalar_modelo" ou "conversar",
  "script": "nome_exato_do_script" ou null,
  "argumento": "argumento extraído do pedido ou caminho do ficheiro anexado" ou "",
  "modelo_recomendado": "tag_exata_ollama (ex: qwen2.5-coder:1.5b)" ou null,
  "resposta": "a tua resposta completa e detalhada ao utilizador"
}}"""

            prompt_utilizador = self.pedido
            if bloco_anexos:
                prompt_utilizador += f"\n\nFicheiros anexados pelo utilizador:\n{bloco_anexos}"

            if provedor == "ollama":
                decisao = self.chamar_ollama(nome_modelo, prompt_sistema, prompt_utilizador, imagens)
            elif provedor == "gemini":
                decisao = self.chamar_gemini(nome_modelo, prompt_sistema, prompt_utilizador, imagens)
            elif provedor == "groq":
                decisao = self.chamar_openai_compativel(
                    "https://api.groq.com/openai/v1/chat/completions",
                    self.chaves.get("GROQ_API_KEY"),
                    nome_modelo, prompt_sistema, prompt_utilizador, imagens
                )
            elif provedor == "deepseek":
                decisao = self.chamar_openai_compativel(
                    "https://api.deepseek.com/chat/completions",
                    self.chaves.get("DEEPSEEK_API_KEY"),
                    nome_modelo, prompt_sistema, prompt_utilizador, []
                )
            else:
                raise ValueError(f"Fornecedor desconhecido: {provedor}")

            self.resultado_pronto.emit(decisao)
        except Exception as e:
            self.erro_ocorrido.emit(str(e))

    def chamar_ollama(self, modelo, sys_prompt, user_prompt, imagens):
        payload_dict = {
            "model": modelo,
            "prompt": f"{sys_prompt}\n\nPedido do utilizador: {user_prompt}",
            "stream": False,
            "options": {
                "temperature": self.config["temperatura"],
                "repeat_penalty": 1.2
            }
        }
        if "deepseek-r1" not in modelo.lower():
            payload_dict["format"] = "json"
        if imagens:
            payload_dict["images"] = [img["b64"] for img in imagens]

        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/generate",
            data=json.dumps(payload_dict).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=self.config["timeout"]) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
            return self.extrair_json_resposta(dados.get("response", ""))

    def chamar_gemini(self, modelo, sys_prompt, user_prompt, imagens):
        api_key = self.chaves.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Variável de ambiente GEMINI_API_KEY não encontrada.")

        parts = [{"text": f"{sys_prompt}\n\nPedido do utilizador:\n{user_prompt}"}]
        for img in imagens:
            parts.append({
                "inline_data": {
                    "mime_type": img["mime"],
                    "data": img["b64"]
                }
            })

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": self.config["temperatura"],
                "responseMimeType": "application/json"
            }
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=self.config["timeout"]) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
            texto = dados["candidates"][0]["content"]["parts"][0]["text"]
            return self.extrair_json_resposta(texto)

    def chamar_openai_compativel(self, url, api_key, modelo, sys_prompt, user_prompt, imagens):
        if not api_key:
            raise ValueError(f"Chave API em falta para o modelo {modelo}.")

        if imagens:
            user_content = [{"type": "text", "text": user_prompt}]
            for img in imagens:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{img['mime']};base64,{img['b64']}"}
                })
        else:
            user_content = user_prompt

        payload = {
            "model": modelo,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": self.config["temperatura"]
        }
        if "reasoner" not in modelo.lower():
            payload["response_format"] = {"type": "json_object"}

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "AssistenteLocal/1.0"
            }
        )
        with urllib.request.urlopen(req, timeout=self.config["timeout"]) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
            texto = dados["choices"][0]["message"]["content"]
            return self.extrair_json_resposta(texto)


# --- Janela Principal ---
class AssistenteWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = carregar_config()
        self.scripts = carregar_scripts()
        self.hardware_info = obter_info_hardware()
        self.chaves = detetar_chaves_ambiente()

        self.anexos_pendentes = []
        self.acao_pendente = None

        self.setAcceptDrops(True)
        self.setWindowTitle(f"Assistente ({self.config['modelo']})")
        self.resize(900, 620)

        self.processo = QProcess(self)
        self.processo.readyReadStandardOutput.connect(self.ler_stdout)
        self.processo.readyReadStandardError.connect(self.ler_stderr)
        self.processo.finished.connect(self.processo_terminado)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.setup_tab_terminal()
        self.setup_tab_scripts()
        self.setup_tab_config()

        self.verificar_modelo_inicial()

    # ==========================================
    # SUPORTE DRAG & DROP DE FICHEIROS
    # ==========================================
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        ficheiros = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if ficheiros:
            self.adicionar_anexos(ficheiros)

    # ==========================================
    # VERIFICAÇÃO / INSTALAÇÃO INICIAL OLLAMA
    # ==========================================
    def verificar_modelo_inicial(self):
        modelo_atual = self.config["modelo"]
        if modelo_atual.startswith("ollama:"):
            nome_limpo = modelo_atual.split(":", 1)[1]
            instalados = obter_modelos_ollama()
            if nome_limpo not in instalados:
                self.escrever_consola(f"[Sistema] Modelo local '{nome_limpo}' não encontrado. A instalar...")
                self.iniciar_instalacao_modelo(nome_limpo, ativar_no_fim=True)

    def iniciar_instalacao_modelo(self, nome_modelo, ativar_no_fim=True):
        self.input_pedido.setEnabled(False)
        self.btn_enviar.setEnabled(False)
        self.pull_worker = PullModeloWorker(nome_modelo)
        self.pull_worker.progresso.connect(lambda msg: self.lbl_status.setText(f"A instalar {nome_modelo} -> {msg}"))
        self.pull_worker.concluido.connect(lambda ok, info: self.finalizar_instalacao_modelo(ok, info, ativar_no_fim))
        self.pull_worker.start()

    def finalizar_instalacao_modelo(self, sucesso, info, ativar_no_fim):
        self.input_pedido.setEnabled(True)
        self.btn_enviar.setEnabled(True)
        self.input_pedido.setFocus()

        if sucesso:
            self.escrever_consola(f"[Sistema] Modelo '{info}' instalado com sucesso!")
            self.atualizar_lista_modelos_unificada()
            if ativar_no_fim:
                self.selecionar_modelo_combo(info)
                self.config["modelo"] = info
                guardar_config(self.config)
                self.setWindowTitle(f"Assistente ({info})")
                self.escrever_consola(f"[Sistema] Modelo ativo alterado para '{info}'.")
        else:
            self.escrever_consola(f"[Erro ao instalar modelo]: {info}")

        self.lbl_status.setText(f"Modelo ativo: {self.config['modelo']} | Config: ~/.config/assistente/")

    # ==========================================
    # SEPARADOR 1: TERMINAL ASSISTENTE
    # ==========================================
    def setup_tab_terminal(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Barra superior
        top_bar = QHBoxLayout()
        self.lbl_status = QLabel(f"Modelo ativo: {self.config['modelo']} | Config: ~/.config/assistente/")
        top_bar.addWidget(self.lbl_status)
        top_bar.addStretch()

        btn_limpar = QPushButton("Limpar Consola")
        btn_limpar.clicked.connect(self.limpar_consola)
        top_bar.addWidget(btn_limpar)
        layout.addLayout(top_bar)

        # Consola de saída
        self.consola = QTextEdit()
        self.consola.setReadOnly(True)
        fonte_mono = QFont("Monospace", 10)
        fonte_mono.setStyleHint(QFont.StyleHint.TypeWriter)
        self.consola.setFont(fonte_mono)
        layout.addWidget(self.consola)

        # Barra de Anexos (oculta quando vazia)
        self.painel_anexos = QFrame()
        self.painel_anexos.setFrameShape(QFrame.Shape.StyledPanel)
        anexos_layout = QHBoxLayout(self.painel_anexos)
        anexos_layout.setContentsMargins(6, 4, 6, 4)

        self.lbl_anexos = QLabel()
        self.lbl_anexos.setWordWrap(True)
        anexos_layout.addWidget(self.lbl_anexos, 1)

        btn_limpar_anexos = QPushButton("Limpar Anexos")
        btn_limpar_anexos.clicked.connect(self.limpar_anexos)
        anexos_layout.addWidget(btn_limpar_anexos)

        self.painel_anexos.hide()
        layout.addWidget(self.painel_anexos)

        # Painel de Confirmação (para scripts ou instalação de modelos)
        self.painel_confirmacao = QFrame()
        self.painel_confirmacao.setFrameShape(QFrame.Shape.StyledPanel)
        conf_layout = QHBoxLayout(self.painel_confirmacao)

        self.lbl_comando = QLabel()
        self.lbl_comando.setWordWrap(True)
        conf_layout.addWidget(self.lbl_comando, 1)

        self.btn_executar = QPushButton("Confirmar")
        self.btn_executar.clicked.connect(self.confirmar_acao)
        conf_layout.addWidget(self.btn_executar)

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.clicked.connect(self.cancelar_acao)
        conf_layout.addWidget(self.btn_cancelar)

        self.painel_confirmacao.hide()
        layout.addWidget(self.painel_confirmacao)

        # Barra inferior de pedido + botão anexar
        input_layout = QHBoxLayout()

        btn_anexar = QPushButton("+ Ficheiro(s)")
        btn_anexar.setToolTip("Anexar imagens, PDFs ou ficheiros de texto/código (também podes arrastar para a janela)")
        btn_anexar.clicked.connect(self.selecionar_anexos)
        input_layout.addWidget(btn_anexar)

        self.input_pedido = QLineEdit()
        self.input_pedido.setPlaceholderText("Escreve o teu pedido ou arrasta ficheiros para aqui...")
        self.input_pedido.returnPressed.connect(self.enviar_pedido)
        input_layout.addWidget(self.input_pedido, 1)

        self.btn_enviar = QPushButton("Enviar")
        self.btn_enviar.clicked.connect(self.enviar_pedido)
        input_layout.addWidget(self.btn_enviar)

        layout.addLayout(input_layout)
        self.tabs.addTab(tab, "Terminal Assistente")

        chaves_ativas = [k.replace("_API_KEY", "") for k, v in self.chaves.items() if v]
        apis_str = ", ".join(chaves_ativas) if chaves_ativas else "Nenhuma externa (apenas Ollama)"
        self.escrever_consola(f"Hardware: {self.hardware_info}")
        self.escrever_consola(f"APIs externas detetadas: {apis_str}\n" + "-" * 65)

    def selecionar_anexos(self):
        ficheiros, _ = QFileDialog.getOpenFileNames(
            self,
            "Selecionar Ficheiro(s) para Analisar",
            str(Path.home()),
            "Todos os ficheiros (*);;Imagens (*.png *.jpg *.jpeg *.webp);;Documentos PDF (*.pdf);;Scripts/Texto (*.sh *.py *.txt *.log *.json *.csv)"
        )
        if ficheiros:
            self.adicionar_anexos(ficheiros)

    def adicionar_anexos(self, ficheiros):
        for f in ficheiros:
            if f not in self.anexos_pendentes:
                self.anexos_pendentes.append(f)
        nomes = [Path(f).name for f in self.anexos_pendentes]
        self.lbl_anexos.setText(f"Anexados ({len(nomes)}): " + ", ".join(nomes))
        self.painel_anexos.show()
        self.input_pedido.setFocus()

    def limpar_anexos(self):
        self.anexos_pendentes.clear()
        self.painel_anexos.hide()

    # ==========================================
    # SEPARADOR 2: GERIR SCRIPTS
    # ==========================================
    def setup_tab_scripts(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("Scripts Registados:"))
        self.lista_scripts = QListWidget()
        self.lista_scripts.currentTextChanged.connect(self.carregar_script_formulario)
        left_layout.addWidget(self.lista_scripts)

        btn_novo = QPushButton("+ Novo Script")
        btn_novo.clicked.connect(self.limpar_formulario)
        left_layout.addWidget(btn_novo)
        splitter.addWidget(left_widget)

        right_widget = QWidget()
        form_layout = QFormLayout(right_widget)

        self.edit_nome = QLineEdit()
        self.edit_nome.setPlaceholderText("ex: convertpdfA")
        form_layout.addRow("Identificador:", self.edit_nome)

        caminho_layout = QHBoxLayout()
        self.edit_caminho = QLineEdit()
        self.edit_caminho.setPlaceholderText("/caminho/para/o/script.sh")
        btn_procurar = QPushButton("Procurar...")
        btn_procurar.clicked.connect(self.procurar_ficheiro)
        caminho_layout.addWidget(self.edit_caminho)
        caminho_layout.addWidget(btn_procurar)
        form_layout.addRow("Caminho:", caminho_layout)

        self.edit_descricao = QTextEdit()
        self.edit_descricao.setMaximumHeight(100)
        self.edit_descricao.setPlaceholderText(
            "Descreve o que o script faz, quando deve ser usado e se precisa de argumentos..."
        )
        form_layout.addRow("Descrição (para a IA):", self.edit_descricao)

        self.chk_args = QCheckBox("Aceita argumentos (ex: caminho de ficheiro, /dev/sdX)")
        form_layout.addRow("", self.chk_args)

        self.chk_perigoso = QCheckBox("Operação destrutiva / crítica (mostra alerta extra)")
        form_layout.addRow("", self.chk_perigoso)

        botoes_layout = QHBoxLayout()
        btn_guardar = QPushButton("Guardar Script")
        btn_guardar.clicked.connect(self.guardar_script_formulario)
        botoes_layout.addWidget(btn_guardar)

        btn_apagar = QPushButton("Remover")
        btn_apagar.clicked.connect(self.remover_script_formulario)
        botoes_layout.addWidget(btn_apagar)

        form_layout.addRow("", botoes_layout)
        splitter.addWidget(right_widget)

        splitter.setSizes([240, 640])
        layout.addWidget(splitter)
        self.tabs.addTab(tab, "Gerir Scripts")

        self.atualizar_lista_scripts()

    # ==========================================
    # SEPARADOR 3: CONFIGURAÇÕES & MODELOS
    # ==========================================
    def setup_tab_config(self):
        tab = QWidget()
        layout = QFormLayout(tab)

        lbl_hw = QLabel(self.hardware_info)
        lbl_hw.setWordWrap(True)
        layout.addRow("Hardware Local:", lbl_hw)

        # Estado das chaves API detetadas
        status_chaves = []
        for k, v in self.chaves.items():
            estado = "Ativa" if v else "Não definida"
            status_chaves.append(f"{k}: {estado}")
        lbl_chaves = QLabel(" | ".join(status_chaves))
        lbl_chaves.setWordWrap(True)
        layout.addRow("Chaves Ambiente:", lbl_chaves)

        # Combo unificada (Ollama + Externos)
        modelo_layout = QHBoxLayout()
        self.combo_modelo = QComboBox()
        self.combo_modelo.setEditable(True)
        modelo_layout.addWidget(self.combo_modelo, 1)

        btn_instalar = QPushButton("Instalar Ollama (Pull)")
        btn_instalar.setToolTip("Descarrega um modelo local Ollama (ex: qwen2.5-coder:1.5b)")
        btn_instalar.clicked.connect(self.instalar_modelo_config_ui)
        modelo_layout.addWidget(btn_instalar)

        btn_refresh = QPushButton("Atualizar Lista")
        btn_refresh.clicked.connect(self.atualizar_lista_modelos_unificada)
        modelo_layout.addWidget(btn_refresh)
        layout.addRow("Modelo Ativo:", modelo_layout)

        self.spin_temp = QDoubleSpinBox()
        self.spin_temp.setRange(0.0, 1.0)
        self.spin_temp.setSingleStep(0.1)
        self.spin_temp.setValue(self.config["temperatura"])
        layout.addRow("Temperatura (0.1 = rigoroso):", self.spin_temp)

        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(10, 600)
        self.spin_timeout.setSuffix(" segundos")
        self.spin_timeout.setValue(self.config["timeout"])
        layout.addRow("Tempo limite (Timeout):", self.spin_timeout)

        self.edit_regras = QTextEdit()
        self.edit_regras.setPlainText(self.config["regras"])
        layout.addRow("Regras / Instruções da IA:", self.edit_regras)

        btns_layout = QHBoxLayout()
        btn_guardar = QPushButton("Guardar Configurações")
        btn_guardar.clicked.connect(self.guardar_config_ui)
        btns_layout.addWidget(btn_guardar)

        btn_repor = QPushButton("Repor Padrão")
        btn_repor.clicked.connect(self.repor_config_ui)
        btns_layout.addWidget(btn_repor)
        layout.addRow("", btns_layout)

        self.tabs.addTab(tab, "Configurações")
        self.atualizar_lista_modelos_unificada()

    # ==========================================
    # MÉTODOS DO TERMINAL & EXECUÇÃO
    # ==========================================
    def escrever_consola(self, texto):
        self.consola.append(texto)
        self.consola.verticalScrollBar().setValue(self.consola.verticalScrollBar().maximum())

    def limpar_consola(self):
        self.consola.clear()
        self.escrever_consola("Consola limpa.\n" + "-" * 65)

    def enviar_pedido(self):
        pedido = self.input_pedido.text().strip()
        if not pedido and not self.anexos_pendentes:
            return
        if not pedido and self.anexos_pendentes:
            pedido = "Analisa o(s) ficheiro(s) anexado(s) e explica o seu conteúdo."

        self.cancelar_acao()
        anexos_atuais = list(self.anexos_pendentes)
        self.limpar_anexos()

        self.input_pedido.clear()
        self.input_pedido.setEnabled(False)
        self.btn_enviar.setEnabled(False)

        info_anexos = f" [+ {len(anexos_atuais)} ficheiro(s)]" if anexos_atuais else ""
        self.escrever_consola(f"\nTu{info_anexos} > {pedido}")

        instalados = obter_modelos_ollama()
        self.worker = AssistenteWorker(
            pedido, anexos_atuais, self.scripts, self.config,
            self.hardware_info, instalados, self.chaves
        )
        self.worker.resultado_pronto.connect(self.tratar_resposta_ia)
        self.worker.erro_ocorrido.connect(self.tratar_erro_ia)
        self.worker.start()

    def tratar_resposta_ia(self, decisao):
        self.input_pedido.setEnabled(True)
        self.btn_enviar.setEnabled(True)
        self.input_pedido.setFocus()

        resposta = decisao.get("resposta", "")
        self.escrever_consola(f"IA > {resposta}")

        acao = decisao.get("acao")

        if acao == "executar":
            nome_script = decisao.get("script")
            arg = decisao.get("argumento", "").strip()

            if nome_script not in self.scripts:
                self.escrever_consola(f"[!] Script '{nome_script}' não existe no catálogo.")
                return

            info = self.scripts[nome_script]
            caminho = info["caminho"]
            interpretador = "python3" if caminho.endswith(".py") else "bash"

            cmd = [caminho]
            if info.get("args") and arg:
                cmd.append(arg)

            self.acao_pendente = ("script", interpretador, cmd)
            aviso = "  [ATENÇÃO: OPERAÇÃO DESTRUTIVA]" if info.get("perigoso") else ""
            self.btn_executar.setText("Executar Script")
            self.lbl_comando.setText(f"Executar: {interpretador} {' '.join(cmd)}{aviso}")
            self.painel_confirmacao.show()

        elif acao == "instalar_modelo":
            modelo_rec = (decisao.get("modelo_recomendado") or "").strip()
            if not modelo_rec:
                return
            nome_limpo = modelo_rec.replace("ollama:", "")
            instalados = obter_modelos_ollama()
            self.acao_pendente = ("modelo", f"ollama:{nome_limpo}")
            if nome_limpo in instalados:
                self.btn_executar.setText("Ativar Modelo")
                self.lbl_comando.setText(f"O modelo local '{nome_limpo}' já está instalado. Ativar agora?")
            else:
                self.btn_executar.setText("Instalar e Ativar")
                self.lbl_comando.setText(f"Descarregar e ativar o modelo local '{nome_limpo}' via Ollama?")
            self.painel_confirmacao.show()

    def tratar_erro_ia(self, erro):
        self.input_pedido.setEnabled(True)
        self.btn_enviar.setEnabled(True)
        self.input_pedido.setFocus()
        self.escrever_consola(f"[Erro]: {erro}")

    def confirmar_acao(self):
        if not self.acao_pendente:
            return
        acao = self.acao_pendente
        self.painel_confirmacao.hide()
        self.acao_pendente = None

        if acao[0] == "script":
            _, interpretador, cmd = acao
            self.escrever_consola(f"\n--- A executar: {interpretador} {' '.join(cmd)} ---")
            self.processo.start(interpretador, cmd)
        elif acao[0] == "modelo":
            _, modelo_id = acao
            nome_limpo = modelo_id.replace("ollama:", "")
            instalados = obter_modelos_ollama()
            if nome_limpo in instalados:
                self.finalizar_instalacao_modelo(True, modelo_id, ativar_no_fim=True)
            else:
                self.escrever_consola(f"\n--- A descarregar modelo '{nome_limpo}' ---")
                self.iniciar_instalacao_modelo(nome_limpo, ativar_no_fim=True)

    def cancelar_acao(self):
        self.painel_confirmacao.hide()
        self.acao_pendente = None

    def ler_stdout(self):
        dados = self.processo.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self.consola.insertPlainText(dados)
        self.consola.verticalScrollBar().setValue(self.consola.verticalScrollBar().maximum())

    def ler_stderr(self):
        dados = self.processo.readAllStandardError().data().decode("utf-8", errors="replace")
        self.consola.insertPlainText(dados)
        self.consola.verticalScrollBar().setValue(self.consola.verticalScrollBar().maximum())

    def processo_terminado(self, exit_code):
        self.escrever_consola(f"\n--- Terminado (código {exit_code}) ---")

    # ==========================================
    # MÉTODOS DO GESTOR DE SCRIPTS
    # ==========================================
    def atualizar_lista_scripts(self):
        self.lista_scripts.clear()
        self.lista_scripts.addItems(sorted(self.scripts.keys()))

    def limpar_formulario(self):
        self.lista_scripts.clearSelection()
        self.edit_nome.clear()
        self.edit_caminho.clear()
        self.edit_descricao.clear()
        self.chk_args.setChecked(False)
        self.chk_perigoso.setChecked(False)
        self.edit_nome.setFocus()

    def carregar_script_formulario(self, nome):
        if not nome or nome not in self.scripts:
            return
        info = self.scripts[nome]
        self.edit_nome.setText(nome)
        self.edit_caminho.setText(info.get("caminho", ""))
        self.edit_descricao.setPlainText(info.get("descricao", ""))
        self.chk_args.setChecked(info.get("args", False))
        self.chk_perigoso.setChecked(info.get("perigoso", False))

    def procurar_ficheiro(self):
        ficheiro, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Script", str(Path.home()), "Scripts (*.sh *.py);;Todos (*)"
        )
        if ficheiro:
            self.edit_caminho.setText(ficheiro)
            if not self.edit_nome.text():
                self.edit_nome.setText(Path(ficheiro).stem)

    def guardar_script_formulario(self):
        nome = self.edit_nome.text().strip()
        caminho = self.edit_caminho.text().strip()
        descricao = self.edit_descricao.toPlainText().strip()

        if not nome or not caminho or not descricao:
            QMessageBox.warning(self, "Campos em falta", "Preenche o identificador, o caminho e a descrição.")
            return

        self.scripts[nome] = {
            "caminho": caminho,
            "descricao": descricao,
            "args": self.chk_args.isChecked(),
            "perigoso": self.chk_perigoso.isChecked()
        }
        guardar_scripts(self.scripts)
        self.atualizar_lista_scripts()
        self.escrever_consola(f"[Sistema] Script '{nome}' guardado em ~/.config/assistente/scripts.json.")

    def remover_script_formulario(self):
        nome = self.edit_nome.text().strip()
        if nome in self.scripts:
            del self.scripts[nome]
            guardar_scripts(self.scripts)
            self.atualizar_lista_scripts()
            self.limpar_formulario()
            self.escrever_consola(f"[Sistema] Script '{nome}' removido.")

    # ==========================================
    # MÉTODOS DAS CONFIGURAÇÕES
    # ==========================================
    def atualizar_lista_modelos_unificada(self):
        self.chaves = detetar_chaves_ambiente()
        modelo_atual = self.config["modelo"]

        self.combo_modelo.clear()

        # 1. Modelos locais Ollama
        for m in obter_modelos_ollama():
            self.combo_modelo.addItem(f"[Local Ollama] {m}", f"ollama:{m}")

        # 2. Modelos externos conforme chaves detetadas no ambiente
        for env_var, lista_modelos in MODELOS_EXTERNOS_DISPONIVEIS.items():
            if self.chaves.get(env_var):
                for modelo_id, label in lista_modelos:
                    self.combo_modelo.addItem(f"[API] {label}", modelo_id)

        self.selecionar_modelo_combo(modelo_atual)

    def selecionar_modelo_combo(self, modelo_id):
        idx = self.combo_modelo.findData(modelo_id)
        if idx >= 0:
            self.combo_modelo.setCurrentIndex(idx)
        else:
            self.combo_modelo.setCurrentText(modelo_id)

    def obter_modelo_selecionado_combo(self):
        idx = self.combo_modelo.currentIndex()
        if idx >= 0 and self.combo_modelo.currentText() == self.combo_modelo.itemText(idx):
            data = self.combo_modelo.itemData(idx)
            if data:
                return data
        texto = self.combo_modelo.currentText().strip()
        if ":" not in texto:
            return f"ollama:{texto}"
        return texto

    def instalar_modelo_config_ui(self):
        modelo_id = self.obter_modelo_selecionado_combo()
        if not modelo_id.startswith("ollama:"):
            QMessageBox.information(
                self, "Modelo Externo",
                "Os modelos de API externa (Gemini, Groq, DeepSeek) não precisam de instalação local — basta selecionar e guardar."
            )
            return
        nome_limpo = modelo_id.split(":", 1)[1]
        self.tabs.setCurrentIndex(0)
        self.escrever_consola(f"\n--- A descarregar modelo Ollama '{nome_limpo}' ---")
        self.iniciar_instalacao_modelo(nome_limpo, ativar_no_fim=True)

    def guardar_config_ui(self):
        modelo_id = self.obter_modelo_selecionado_combo()
        if not modelo_id:
            QMessageBox.warning(self, "Modelo inválido", "Seleciona ou escreve um modelo.")
            return

        self.config["modelo"] = modelo_id
        self.config["temperatura"] = round(self.spin_temp.value(), 2)
        self.config["timeout"] = self.spin_timeout.value()
        self.config["regras"] = self.edit_regras.toPlainText().strip()

        guardar_config(self.config)
        self.setWindowTitle(f"Assistente ({self.config['modelo']})")
        self.lbl_status.setText(f"Modelo ativo: {self.config['modelo']} | Config: ~/.config/assistente/")
        self.escrever_consola(f"[Sistema] Modelo ativo guardado: {self.config['modelo']}")

    def repor_config_ui(self):
        self.selecionar_modelo_combo(DEFAULT_CONFIG["modelo"])
        self.spin_temp.setValue(DEFAULT_CONFIG["temperatura"])
        self.spin_timeout.setValue(DEFAULT_CONFIG["timeout"])
        self.edit_regras.setPlainText(DEFAULT_CONFIG["regras"])


if __name__ == "__main__":
    app = QApplication(sys.argv)
    janela = AssistenteWindow()
    janela.show()
    sys.exit(app.exec())
