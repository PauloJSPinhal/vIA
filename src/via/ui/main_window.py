"""Janela principal do vIA (PySide6)."""

import shlex
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from via import constants as C
from via.config import (
    carregar_config,
    carregar_scripts,
    guardar_config,
    guardar_scripts,
    nome_script_valido,
    normalizar_modelo,
)
from via.hardware import chave_em_falta, detetar_chaves_ambiente, obter_info_hardware
from via.workers import AssistenteWorker, DescobertaModelosWorker, PullModeloWorker


def _caminho_curto(caminho: Path) -> str:
    try:
        return "~/" + str(caminho.relative_to(Path.home()))
    except ValueError:
        return str(caminho)


class ViaWindow(QMainWindow):
    def __init__(self, migrados_config: list[str] | None = None):
        super().__init__()

        self.config = carregar_config()
        self.scripts = carregar_scripts()
        self.migrados_config = migrados_config or []
        self.hardware_info = obter_info_hardware()
        self.chaves = detetar_chaves_ambiente()

        self.anexos_pendentes: list[str] = []
        self.acao_pendente = None
        self.script_selecionado: str | None = None
        self._confirmacao_perigosa = False
        self.modelos_disponiveis = []
        self.worker: AssistenteWorker | None = None
        self.pull_worker: PullModeloWorker | None = None
        self._worker_modelos: DescobertaModelosWorker | None = None

        self.setAcceptDrops(True)
        self.setWindowTitle(f"{C.APP_NOME} ({self.config['modelo']})")
        self.resize(960, 680)

        # --- Execução de scripts em subprocesso ---
        self.processo = QProcess(self)
        self.processo.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.processo.readyReadStandardOutput.connect(self.ler_stdout)
        self.processo.readyReadStandardError.connect(self.ler_stderr)
        self.processo.finished.connect(self.processo_terminado)
        self.processo.errorOccurred.connect(self.processo_erro)

        self.timer_timeout = QTimer(self)
        self.timer_timeout.setSingleShot(True)
        self.timer_timeout.timeout.connect(self.parar_processo_por_timeout)

        self.timer_kill = QTimer(self)
        self.timer_kill.setSingleShot(True)
        self.timer_kill.timeout.connect(self.forcar_fim_processo)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.setup_tab_terminal()
        self.setup_tab_scripts()
        self.setup_tab_config()

        self.atualizar_lista_modelos_unificada()

    # ==================================================================
    # Drag & drop
    # ==================================================================
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        ficheiros = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if ficheiros:
            self.adicionar_anexos(ficheiros)

    # ==================================================================
    # Estado / utilidades
    # ==================================================================
    def _texto_status(self) -> str:
        modelo = self.config["modelo"] or "(nenhum)"
        return (
            f"Modelo ativo: {modelo} | "
            f"Config: {_caminho_curto(C.CONFIG_DIR)}"
        )

    def escrever_consola(self, texto: str):
        self.consola.append(texto)
        barra = self.consola.verticalScrollBar()
        barra.setValue(barra.maximum())

    def limpar_consola(self):
        self.consola.clear()
        self.escrever_consola("Consola limpa.\n" + "-" * 65)

    # ==================================================================
    # Separador 1: terminal assistente
    # ==================================================================
    def setup_tab_terminal(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        top_bar = QHBoxLayout()
        self.lbl_status = QLabel(self._texto_status())
        top_bar.addWidget(self.lbl_status)
        top_bar.addStretch()

        self.btn_parar = QPushButton("Parar Execução")
        self.btn_parar.setEnabled(False)
        self.btn_parar.clicked.connect(self.parar_execucao)
        top_bar.addWidget(self.btn_parar)

        btn_limpar = QPushButton("Limpar Consola")
        btn_limpar.clicked.connect(self.limpar_consola)
        top_bar.addWidget(btn_limpar)
        layout.addLayout(top_bar)

        self.consola = QTextEdit()
        self.consola.setReadOnly(True)
        fonte_mono = QFont("Monospace", 10)
        fonte_mono.setStyleHint(QFont.StyleHint.TypeWriter)
        self.consola.setFont(fonte_mono)
        layout.addWidget(self.consola)

        # Barra de anexos (oculta quando vazia)
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

        # Painel de confirmação (scripts ou instalação de modelos)
        self.painel_confirmacao = QFrame()
        self.painel_confirmacao.setFrameShape(QFrame.Shape.StyledPanel)
        conf_layout = QVBoxLayout(self.painel_confirmacao)
        conf_linha = QHBoxLayout()

        self.lbl_comando = QLabel()
        self.lbl_comando.setWordWrap(True)
        conf_linha.addWidget(self.lbl_comando, 1)

        self.btn_executar = QPushButton("Confirmar")
        self.btn_executar.clicked.connect(self.confirmar_acao)
        conf_linha.addWidget(self.btn_executar)

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.clicked.connect(self.cancelar_acao)
        conf_linha.addWidget(self.btn_cancelar)

        conf_layout.addLayout(conf_linha)

        # Confirmação explícita apenas para scripts marcados como perigosos.
        self.chk_risco = QCheckBox(
            "Compreendo que esta operação é destrutiva e pode causar perda de dados."
        )
        self.chk_risco.toggled.connect(self._atualizar_estado_confirmacao)
        self.chk_risco.hide()
        conf_layout.addWidget(self.chk_risco)

        self.painel_confirmacao.hide()
        layout.addWidget(self.painel_confirmacao)

        # Barra inferior: anexar + pedido + enviar
        input_layout = QHBoxLayout()

        btn_anexar = QPushButton("+ Ficheiro(s)")
        btn_anexar.setToolTip(
            "Anexar imagens, PDFs ou ficheiros de texto/código "
            "(também podes arrastar para a janela)"
        )
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

        # Mensagens iniciais
        self.escrever_consola(f"{C.APP_NOME} {C.APP_VERSAO} | Config: {_caminho_curto(C.CONFIG_DIR)}")
        if self.migrados_config:
            self.escrever_consola(
                f"[Sistema] Configuração migrada de {_caminho_curto(C.CONFIG_LEGADO_DIR)}: "
                + ", ".join(self.migrados_config)
            )
        self.escrever_consola(f"Hardware: {self.hardware_info}")

        chaves_ativas = [k.replace("_API_KEY", "") for k, v in self.chaves.items() if v]
        apis_str = ", ".join(chaves_ativas) if chaves_ativas else "Nenhuma externa (apenas Ollama)"
        self.escrever_consola(f"APIs externas detetadas: {apis_str}\n" + "-" * 65)

        faltante = chave_em_falta(self.config["modelo"], self.chaves)
        if faltante:
            self.escrever_consola(
                f"[Aviso] O modelo ativo requer a variável {faltante}, que não está definida. "
                "Os pedidos irão falhar até a configurares."
            )

    def selecionar_anexos(self):
        ficheiros, _ = QFileDialog.getOpenFileNames(
            self,
            "Selecionar Ficheiro(s) para Analisar",
            str(Path.home()),
            "Todos os ficheiros (*);;Imagens (*.png *.jpg *.jpeg *.webp);;"
            "Documentos PDF (*.pdf);;Scripts/Texto (*.sh *.py *.txt *.log *.json *.csv)",
        )
        if ficheiros:
            self.adicionar_anexos(ficheiros)

    def adicionar_anexos(self, ficheiros: list[str]):
        for ficheiro in ficheiros:
            caminho = Path(ficheiro).expanduser()
            if not caminho.is_file():
                self.escrever_consola(f"[Aviso] Ignorado (não é um ficheiro): {ficheiro}")
                continue
            if len(self.anexos_pendentes) >= C.MAX_ANEXOS:
                self.escrever_consola(
                    f"[Aviso] Limite de {C.MAX_ANEXOS} anexos por pedido atingido."
                )
                break
            if str(caminho) not in self.anexos_pendentes:
                self.anexos_pendentes.append(str(caminho))

        if not self.anexos_pendentes:
            return
        nomes = [Path(f).name for f in self.anexos_pendentes]
        self.lbl_anexos.setText(f"Anexados ({len(nomes)}): " + ", ".join(nomes))
        self.painel_anexos.show()
        self.input_pedido.setFocus()

    def limpar_anexos(self):
        self.anexos_pendentes.clear()
        self.painel_anexos.hide()

    # ==================================================================
    # Separador 2: gerir scripts
    # ==================================================================
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
        self.edit_nome.setPlaceholderText("ex: audio-reset")
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

        self.chk_perigoso = QCheckBox("Operação destrutiva / crítica (exige confirmação extra)")
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

    # ==================================================================
    # Separador 3: configurações & modelos
    # ==================================================================
    def setup_tab_config(self):
        tab = QWidget()
        layout = QFormLayout(tab)

        lbl_hw = QLabel(self.hardware_info)
        lbl_hw.setWordWrap(True)
        layout.addRow("Hardware Local:", lbl_hw)

        self.lbl_chaves = QLabel()
        self.lbl_chaves.setWordWrap(True)
        layout.addRow("Chaves Ambiente:", self.lbl_chaves)

        lbl_aviso_chaves = QLabel(
            "As chaves são lidas das variáveis de ambiente e nunca são guardadas em disco."
        )
        lbl_aviso_chaves.setWordWrap(True)
        layout.addRow("", lbl_aviso_chaves)
        self._atualizar_chaves_ui()

        modelo_layout = QHBoxLayout()
        self.combo_modelo = QComboBox()
        self.combo_modelo.setEditable(True)
        if self.combo_modelo.lineEdit() is not None:
            self.combo_modelo.lineEdit().setPlaceholderText("Seleciona um modelo descoberto…")
        modelo_layout.addWidget(self.combo_modelo, 1)

        self.btn_instalar_modelo = QPushButton("Instalar Ollama (Pull)")
        self.btn_instalar_modelo.setToolTip(
            "Escreve uma tag Ollama no seletor (ex: modelo:tag) e descarrega-a"
        )
        self.btn_instalar_modelo.clicked.connect(self.instalar_modelo_config_ui)
        modelo_layout.addWidget(self.btn_instalar_modelo)

        self.btn_refresh_modelos = QPushButton("Atualizar Modelos")
        self.btn_refresh_modelos.clicked.connect(
            lambda: self.atualizar_lista_modelos_unificada()
        )
        modelo_layout.addWidget(self.btn_refresh_modelos)
        layout.addRow("Modelo Ativo:", modelo_layout)

        self.spin_temp = QDoubleSpinBox()
        self.spin_temp.setRange(0.0, 2.0)
        self.spin_temp.setSingleStep(0.1)
        self.spin_temp.setValue(self.config["temperatura"])
        layout.addRow("Temperatura (0.1 = rigoroso):", self.spin_temp)

        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(10, 900)
        self.spin_timeout.setSuffix(" segundos")
        self.spin_timeout.setValue(self.config["timeout"])
        layout.addRow("Tempo limite da IA:", self.spin_timeout)

        self.spin_timeout_script = QSpinBox()
        self.spin_timeout_script.setRange(0, 3600)
        self.spin_timeout_script.setSpecialValueText("Sem limite")
        self.spin_timeout_script.setSuffix(" segundos")
        self.spin_timeout_script.setValue(self.config["timeout_script"])
        layout.addRow("Tempo limite de scripts:", self.spin_timeout_script)

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

    def _atualizar_chaves_ui(self):
        self.chaves = detetar_chaves_ambiente()
        estados = [
            f"{k}: {'Ativa' if v else 'Não definida'}"
            for k, v in self.chaves.items()
        ]
        self.lbl_chaves.setText(" | ".join(estados))

    # ==================================================================
    # Envio de pedidos e respostas
    # ==================================================================
    def enviar_pedido(self):
        pedido = self.input_pedido.text().strip()
        if not pedido and not self.anexos_pendentes:
            return
        if not pedido:
            pedido = "Analisa o(s) ficheiro(s) anexado(s) e explica o seu conteúdo."

        if self.worker is not None and self.worker.isRunning():
            return

        self.cancelar_acao()
        anexos_atuais = list(self.anexos_pendentes)
        self.limpar_anexos()

        self.input_pedido.clear()
        self.input_pedido.setEnabled(False)
        self.btn_enviar.setEnabled(False)

        info_anexos = f" [+ {len(anexos_atuais)} ficheiro(s)]" if anexos_atuais else ""
        self.escrever_consola(f"\nTu{info_anexos} > {pedido}")

        self.worker = AssistenteWorker(
            pedido,
            anexos_atuais,
            self.scripts,
            self.config,
            self.hardware_info,
            self.chaves,
            self,
        )
        self.worker.resultado_pronto.connect(self.tratar_resposta_ia)
        self.worker.erro_ocorrido.connect(self.tratar_erro_ia)
        self.worker.aviso.connect(lambda msg: self.escrever_consola(f"[Aviso] {msg}"))
        self.worker.start()

    def _reativar_input(self):
        self.input_pedido.setEnabled(True)
        self.btn_enviar.setEnabled(True)
        self.input_pedido.setFocus()

    def tratar_resposta_ia(self, decisao: dict):
        self._reativar_input()

        resposta = decisao.get("resposta") or "(sem resposta)"
        self.escrever_consola(f"IA > {resposta}")

        if decisao.get("acao") == "executar":
            self._preparar_execucao_script(decisao)

    def tratar_erro_ia(self, erro: str):
        self._reativar_input()
        self.escrever_consola(f"[Erro]: {erro}")

    def _preparar_execucao_script(self, decisao: dict):
        nome_script = decisao.get("script")
        if nome_script not in self.scripts:
            self.escrever_consola(f"[!] Script '{nome_script}' não existe no catálogo.")
            return

        info = self.scripts[nome_script]
        caminho = Path(info["caminho"]).expanduser()
        if not caminho.is_file():
            self.escrever_consola(
                f"[!] O script '{nome_script}' aponta para um ficheiro inexistente: {caminho}"
            )
            return

        argumento = (decisao.get("argumento") or "").strip()[:C.MAX_ARGUMENTO]
        if argumento and not info.get("args"):
            self.escrever_consola(
                f"[Aviso] O script '{nome_script}' está marcado como sem argumentos; "
                "o argumento extraído foi ignorado."
            )
            argumento = ""

        interpretador = sys.executable if caminho.suffix == ".py" else "bash"
        argumentos = [str(caminho)]
        if argumento:
            argumentos.append(argumento)

        self.acao_pendente = ("script", interpretador, argumentos, bool(info.get("perigoso")))
        comando = shlex.join([interpretador, *argumentos])

        if info.get("perigoso"):
            texto = f"⚠ OPERAÇÃO DESTRUTIVA ⚠\nComando:\n{comando}"
            rotulo = "Executar (operação destrutiva)"
        else:
            texto = f"Comando a executar:\n{comando}"
            rotulo = "Executar Script"

        self._mostrar_confirmacao(texto, rotulo, bool(info.get("perigoso")))

    # ==================================================================
    # Confirmação e execução
    # ==================================================================
    def _mostrar_confirmacao(self, texto: str, rotulo: str, perigoso: bool):
        self._confirmacao_perigosa = perigoso
        self.lbl_comando.setText(texto)
        self.btn_executar.setText(rotulo)
        self.chk_risco.setChecked(False)
        self.chk_risco.setVisible(perigoso)
        self.btn_executar.setEnabled(not perigoso)
        self.painel_confirmacao.show()

    def _atualizar_estado_confirmacao(self, marcado: bool):
        self.btn_executar.setEnabled(marcado if self._confirmacao_perigosa else True)

    def confirmar_acao(self):
        if not self.acao_pendente:
            return
        if self._confirmacao_perigosa and not self.chk_risco.isChecked():
            return

        acao = self.acao_pendente
        self.painel_confirmacao.hide()
        self.chk_risco.hide()
        self._confirmacao_perigosa = False
        self.acao_pendente = None

        if acao[0] == "script":
            _, interpretador, argumentos, _perigoso = acao
            self.escrever_consola(
                "\n--- A executar: " + shlex.join([interpretador, *argumentos]) + " ---"
            )
            self.processo.start(interpretador, argumentos)
            if not self.processo.waitForStarted(3000):
                self.escrever_consola("[Erro] Não foi possível iniciar o processo.")
                return
            self.btn_parar.setEnabled(True)

            limite = self.config.get("timeout_script", 0)
            if limite and limite > 0:
                self.timer_timeout.start(limite * 1000)

    def cancelar_acao(self):
        self.painel_confirmacao.hide()
        self.chk_risco.hide()
        self._confirmacao_perigosa = False
        self.acao_pendente = None

    def parar_execucao(self):
        if self.processo.state() == QProcess.ProcessState.NotRunning:
            return
        resposta = QMessageBox.question(
            self,
            "Parar execução",
            "Queres mesmo terminar o script em execução?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta == QMessageBox.StandardButton.Yes:
            self.escrever_consola("[Sistema] A terminar o processo a pedido do utilizador...")
            self._terminar_processo()

    def parar_processo_por_timeout(self):
        if self.processo.state() == QProcess.ProcessState.NotRunning:
            return
        limite = self.config.get("timeout_script", 0)
        self.escrever_consola(
            f"[Aviso] Tempo limite de {limite}s excedido. A terminar o processo..."
        )
        self._terminar_processo()

    def _terminar_processo(self):
        if self.processo.state() == QProcess.ProcessState.NotRunning:
            return
        self.processo.terminate()
        self.timer_kill.start(3000)

    def forcar_fim_processo(self):
        if self.processo.state() == QProcess.ProcessState.Running:
            self.escrever_consola("[Aviso] O processo não terminou; a forçar o encerramento.")
            self.processo.kill()

    def ler_stdout(self):
        dados = self.processo.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self.consola.moveCursor(QTextCursor.MoveOperation.End)
        self.consola.insertPlainText(dados)
        barra = self.consola.verticalScrollBar()
        barra.setValue(barra.maximum())

    def ler_stderr(self):
        dados = self.processo.readAllStandardError().data().decode("utf-8", errors="replace")
        self.consola.insertPlainText(dados)
        barra = self.consola.verticalScrollBar()
        barra.setValue(barra.maximum())

    def processo_terminado(self, exit_code: int, exit_status):
        self.timer_timeout.stop()
        self.timer_kill.stop()
        self.btn_parar.setEnabled(False)

        if exit_status == QProcess.ExitStatus.CrashExit:
            self.escrever_consola("\n--- Processo terminado/cancelado ---")
        else:
            self.escrever_consola(f"\n--- Terminado (código {exit_code}) ---")

    def processo_erro(self, erro):
        if erro == QProcess.ProcessError.FailedToStart:
            self.escrever_consola(
                "[Erro] Não foi possível iniciar o processo "
                "(verifica o interpretador e as permissões do ficheiro)."
            )

    # ==================================================================
    # Gestor de scripts
    # ==================================================================
    def atualizar_lista_scripts(self, selecionar: str | None = None):
        blocker = QSignalBlocker(self.lista_scripts)
        self.lista_scripts.clear()
        self.lista_scripts.addItems(sorted(self.scripts.keys()))
        if selecionar:
            itens = self.lista_scripts.findItems(selecionar, Qt.MatchFlag.MatchExactly)
            if itens:
                self.lista_scripts.setCurrentItem(itens[0])
        del blocker

    def limpar_formulario(self):
        self.script_selecionado = None
        self.lista_scripts.clearSelection()
        self.edit_nome.clear()
        self.edit_caminho.clear()
        self.edit_descricao.clear()
        self.chk_args.setChecked(False)
        self.chk_perigoso.setChecked(False)
        self.edit_nome.setFocus()

    def carregar_script_formulario(self, nome: str):
        if not nome or nome not in self.scripts:
            return
        info = self.scripts[nome]
        self.script_selecionado = nome
        self.edit_nome.setText(nome)
        self.edit_caminho.setText(info.get("caminho", ""))
        self.edit_descricao.setPlainText(info.get("descricao", ""))
        self.chk_args.setChecked(info.get("args", False))
        self.chk_perigoso.setChecked(info.get("perigoso", False))

    def procurar_ficheiro(self):
        ficheiro, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar Script",
            str(Path.home()),
            "Scripts (*.sh *.py);;Todos (*)",
        )
        if ficheiro:
            self.edit_caminho.setText(ficheiro)
            if not self.edit_nome.text():
                self.edit_nome.setText(Path(ficheiro).stem)

    def guardar_script_formulario(self):
        nome = self.edit_nome.text().strip()
        caminho_texto = self.edit_caminho.text().strip()
        descricao = self.edit_descricao.toPlainText().strip()

        if not nome or not caminho_texto or not descricao:
            QMessageBox.warning(
                self, "Campos em falta",
                "Preenche o identificador, o caminho e a descrição.",
            )
            return

        if not nome_script_valido(nome):
            QMessageBox.warning(
                self, "Identificador inválido",
                "Usa apenas letras, números, ponto, hífen ou underscore "
                "(ex: audio-reset, backup.sh).",
            )
            return

        caminho = Path(caminho_texto).expanduser()
        if not caminho.is_file():
            resposta = QMessageBox.question(
                self,
                "Ficheiro não encontrado",
                f"O ficheiro '{caminho}' não existe. Guardar mesmo assim?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if resposta != QMessageBox.StandardButton.Yes:
                return

        if (
            self.script_selecionado
            and self.script_selecionado != nome
            and self.script_selecionado in self.scripts
        ):
            del self.scripts[self.script_selecionado]

        self.scripts[nome] = {
            "caminho": str(caminho),
            "descricao": descricao,
            "args": self.chk_args.isChecked(),
            "perigoso": self.chk_perigoso.isChecked(),
        }
        guardar_scripts(self.scripts)
        self.script_selecionado = nome
        self.atualizar_lista_scripts(selecionar=nome)
        self.escrever_consola(
            f"[Sistema] Script '{nome}' guardado em {_caminho_curto(C.SCRIPTS_FILE)}."
        )

    def remover_script_formulario(self):
        nome = self.script_selecionado or self.edit_nome.text().strip()
        if nome not in self.scripts:
            return

        resposta = QMessageBox.question(
            self,
            "Remover script",
            f"Remover '{nome}' do catálogo?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return

        del self.scripts[nome]
        guardar_scripts(self.scripts)
        self.atualizar_lista_scripts()
        self.limpar_formulario()
        self.escrever_consola(f"[Sistema] Script '{nome}' removido.")

    # ==================================================================
    # Modelos
    # ==================================================================
    def atualizar_lista_modelos_unificada(self):
        if self._worker_modelos is not None and self._worker_modelos.isRunning():
            return

        self.btn_refresh_modelos.setEnabled(False)
        self._atualizar_chaves_ui()
        self.lbl_status.setText("A procurar modelos disponíveis...")

        self._worker_modelos = DescobertaModelosWorker(self.chaves, self)
        self._worker_modelos.concluido.connect(self._aplicar_lista_modelos)
        self._worker_modelos.start()

    def _aplicar_lista_modelos(self, modelos, avisos):
        self.btn_refresh_modelos.setEnabled(True)
        self.modelos_disponiveis = list(modelos or [])
        self._atualizar_chaves_ui()

        self.combo_modelo.clear()
        for modelo in self.modelos_disponiveis:
            self.combo_modelo.addItem(modelo.rotulo, modelo.modelo_id)

        for aviso in avisos or []:
            self.escrever_consola(f"[Aviso] {aviso}")

        if not self.modelos_disponiveis:
            self.combo_modelo.setCurrentText("")
            self.escrever_consola(
                "[Sistema] Nenhum modelo detetado. Instala um modelo no Ollama ou "
                "define uma chave API no ambiente e clica em 'Atualizar Modelos'."
            )
            self.lbl_status.setText(self._texto_status())
            return

        ids = {m.modelo_id for m in self.modelos_disponiveis}
        escolha_pendente = False

        if not self.config["modelo"]:
            if len(self.modelos_disponiveis) == 1:
                # Só há uma opção: adotá-la é inequívoco.
                self._ativar_modelo(self.modelos_disponiveis[0].modelo_id)
            else:
                self.combo_modelo.setCurrentIndex(-1)
                escolha_pendente = True
                self.escrever_consola(
                    f"[Sistema] {len(self.modelos_disponiveis)} modelos detetados. "
                    "Escolhe um no separador Configurações e clica em "
                    "'Guardar Configurações'."
                )
        elif self.config["modelo"] in ids:
            self.selecionar_modelo_combo(self.config["modelo"])
        else:
            self.selecionar_modelo_combo(self.config["modelo"])
            faltante = chave_em_falta(self.config["modelo"], self.chaves)
            if faltante:
                self.escrever_consola(
                    f"[Aviso] O modelo configurado '{self.config['modelo']}' não foi "
                    f"detetado (a variável {faltante} não está definida)."
                )
            else:
                self.escrever_consola(
                    f"[Aviso] O modelo configurado '{self.config['modelo']}' não foi "
                    "detetado. Escolhe outro modelo e guarda."
                )

        self.lbl_status.setText(self._texto_status())
        if not escolha_pendente:
            contagem: dict[str, int] = {}
            for modelo in self.modelos_disponiveis:
                contagem[modelo.provedor] = contagem.get(modelo.provedor, 0) + 1
            resumo = " | ".join(
                f"{C.NOMES_PROVEDORES.get(provedor, provedor)}: {quantidade}"
                for provedor, quantidade in contagem.items()
            )
            self.escrever_consola(
                f"[Sistema] {len(self.modelos_disponiveis)} modelo(s) disponível(is)"
                + (f" — {resumo}" if resumo else "")
                + "."
            )

    def selecionar_modelo_combo(self, modelo_id: str):
        indice = self.combo_modelo.findData(modelo_id)
        if indice >= 0:
            self.combo_modelo.setCurrentIndex(indice)
        else:
            self.combo_modelo.setCurrentText(modelo_id)

    def obter_modelo_selecionado_combo(self) -> str:
        dados = self.combo_modelo.currentData()
        if dados:
            return str(dados)
        return normalizar_modelo(self.combo_modelo.currentText())

    def _ativar_modelo(self, modelo_id: str):
        self.config["modelo"] = normalizar_modelo(modelo_id)
        guardar_config(self.config)
        self.setWindowTitle(f"{C.APP_NOME} ({self.config['modelo']})")
        self.lbl_status.setText(self._texto_status())
        self.selecionar_modelo_combo(self.config["modelo"])
        self.escrever_consola(f"[Sistema] Modelo ativo alterado para '{self.config['modelo']}'.")

    def iniciar_instalacao_modelo(self, nome_modelo: str):
        if self.pull_worker is not None and self.pull_worker.isRunning():
            QMessageBox.information(
                self, "Instalação em curso",
                "Já existe uma instalação de modelo em curso. Aguarda que termine.",
            )
            return

        self.input_pedido.setEnabled(False)
        self.btn_enviar.setEnabled(False)
        self.btn_instalar_modelo.setEnabled(False)

        self.pull_worker = PullModeloWorker(nome_modelo, self)
        self.pull_worker.progresso.connect(
            lambda msg: self.lbl_status.setText(f"A instalar {nome_modelo} -> {msg}")
        )
        self.pull_worker.concluido.connect(self.finalizar_instalacao_modelo)
        self.pull_worker.start()

    def finalizar_instalacao_modelo(self, sucesso: bool, info: str):
        self._reativar_input()
        self.btn_instalar_modelo.setEnabled(True)

        if sucesso:
            self.escrever_consola(f"[Sistema] Modelo '{info}' instalado com sucesso!")
            self._ativar_modelo(info)
            self.atualizar_lista_modelos_unificada()
        else:
            self.escrever_consola(f"[Erro ao instalar modelo]: {info}")

        self.lbl_status.setText(self._texto_status())

    def instalar_modelo_config_ui(self):
        modelo_id = self.combo_modelo.currentData()

        if modelo_id:
            if not str(modelo_id).startswith("ollama:"):
                QMessageBox.information(
                    self, "Modelo externo",
                    "Os modelos de API externa (Gemini, Groq, DeepSeek) não precisam de "
                    "instalação local — são descobertos automaticamente a partir da chave.",
                )
                return
            nome_limpo = str(modelo_id).split(":", 1)[1]
        else:
            nome_limpo = self.combo_modelo.currentText().strip()
            if nome_limpo.startswith("ollama:"):
                nome_limpo = nome_limpo.split(":", 1)[1]

        if not nome_limpo:
            QMessageBox.warning(
                self, "Tag em falta",
                "Escreve no seletor a tag Ollama que queres descarregar "
                "(ex: modelo:tag).",
            )
            return

        if " " in nome_limpo:
            QMessageBox.warning(
                self, "Tag inválida",
                "A tag do modelo não pode conter espaços.",
            )
            return

        resposta = QMessageBox.question(
            self,
            "Descarregar modelo",
            f"Descarregar o modelo Ollama '{nome_limpo}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return

        self.tabs.setCurrentIndex(0)
        self.escrever_consola(f"\n--- A descarregar modelo Ollama '{nome_limpo}' ---")
        self.iniciar_instalacao_modelo(nome_limpo)

    def guardar_config_ui(self):
        modelo_id = self.obter_modelo_selecionado_combo()

        if not modelo_id:
            resposta = QMessageBox.question(
                self,
                "Nenhum modelo selecionado",
                "Não há nenhum modelo selecionado; os pedidos não funcionarão até "
                "escolheres um modelo disponível.\n\nGuardar mesmo assim?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if resposta != QMessageBox.StandardButton.Yes:
                return

        faltante = chave_em_falta(modelo_id, self.chaves) if modelo_id else None
        if faltante:
            resposta = QMessageBox.question(
                self,
                "Chave API em falta",
                f"O modelo '{modelo_id}' requer a variável de ambiente {faltante}, "
                "que não foi detetada.\n\nGuardar mesmo assim?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if resposta != QMessageBox.StandardButton.Yes:
                return

        regras = self.edit_regras.toPlainText().strip()
        if not regras:
            QMessageBox.warning(
                self, "Regras vazias",
                "As regras da IA não podem ficar vazias.",
            )
            return

        self.config["modelo"] = normalizar_modelo(modelo_id)
        self.config["temperatura"] = round(self.spin_temp.value(), 2)
        self.config["timeout"] = self.spin_timeout.value()
        self.config["timeout_script"] = self.spin_timeout_script.value()
        self.config["regras"] = regras

        guardar_config(self.config)
        self.setWindowTitle(f"{C.APP_NOME} ({self.config['modelo']})")
        self.lbl_status.setText(self._texto_status())
        self.escrever_consola(f"[Sistema] Modelo ativo guardado: {self.config['modelo']}")

    def repor_config_ui(self):
        self.selecionar_modelo_combo(C.DEFAULT_CONFIG["modelo"])
        self.spin_temp.setValue(C.DEFAULT_CONFIG["temperatura"])
        self.spin_timeout.setValue(C.DEFAULT_CONFIG["timeout"])
        self.spin_timeout_script.setValue(C.DEFAULT_CONFIG["timeout_script"])
        self.edit_regras.setPlainText(C.DEFAULT_CONFIG["regras"])

    # ==================================================================
    # Encerramento
    # ==================================================================
    def closeEvent(self, event):
        if self.processo.state() != QProcess.ProcessState.NotRunning:
            resposta = QMessageBox.question(
                self,
                "Script em execução",
                "Há um script em execução. Terminar e sair?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if resposta != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.processo.kill()
            self.processo.waitForFinished(2000)

        for trabalhador in (self.worker, self.pull_worker, self._worker_modelos):
            if trabalhador is not None and trabalhador.isRunning():
                if hasattr(trabalhador, "cancelar"):
                    trabalhador.cancelar()
                trabalhador.requestInterruption()
                if not trabalhador.wait(1000):
                    trabalhador.terminate()
                    trabalhador.wait(500)

        event.accept()
