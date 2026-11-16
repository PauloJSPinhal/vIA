# vIA

Um assistente de desktop leve e nativo (PySide6 / Qt 6) que atua como canal direto entre pedidos em linguagem natural e a execução segura da sua biblioteca pessoal de scripts (`.sh` e `.py`), permitindo também conversar e analisar documentos, código e imagens.

Concebido para funcionar desde portáteis modestos com 4 GB de RAM (usando modelos ultraleves locais via **Ollama**) até workstations com GPU dedicada ou APIs externas (**Gemini**, **Groq** e **DeepSeek**).

## Funcionalidades Principais

* **Router Inteligente de Scripts:** Mapeia pedidos em linguagem natural para os seus scripts locais e extrai automaticamente argumentos (caminhos de ficheiros, dispositivos `/dev/sdX`, etc.).
* **Execução Segura com Confirmação Visual:** Nenhum script corre sem aprovação explícita. Scripts marcados como destrutivos (ex: formatação de discos) exibem um aviso crítico antes da execução, com saída de terminal em tempo real (`stdout`/`stderr`).
* **Suporte Híbrido (Local + Nuvem):**
  * **Ollama Local:** Instalação automática de um modelo base (`qwen2.5:0.5b`) no primeiro arranque caso não exista nenhum instalado.
  * **APIs Externas:** Deteta automaticamente as variáveis de ambiente `GEMINI_API_KEY`, `GROQ_API_KEY` e `DEEPSEEK_API_KEY` e disponibiliza os respetivos modelos no seletor.
* **Diagnóstico de Hardware & Gestão de Modelos:** Analisa CPU, RAM disponível e GPU (`nvidia-smi`) para recomendar e descarregar o modelo Ollama mais adequado à máquina atual diretamente pela interface.
* **Análise de Múltiplos Ficheiros (Drag & Drop):** Permite anexar ou arrastar imagens (`.jpg`, `.png`, `.webp`), documentos `.pdf` (via `pdftotext` ou `pypdf`), logs e código para análise.
* **Gestor Gráfico de Scripts & Regras:** Adicione, edite ou remova scripts e ajuste o *system prompt*, temperatura e *timeout* sem editar código.
* **Integração Nativa & XDG:** Adapta-se automaticamente ao tema claro/escuro e fontes do ambiente gráfico Linux e guarda todas as configurações em `~/.config/via/`.

## Estrutura do Projeto

```text
vIA/
├── src/
│   ├── via/
│   │   ├── providers/      # Conectores de modelos (Ollama, Gemini, Groq, DeepSeek)
│   │   ├── parsers/        # Leitores de anexos (PDF, imagens, texto/código)
│   │   └── ui/             # Componentes gráficos PySide6
│   └── via.py              # Ponto de entrada principal da aplicação
├── assets/
│   └── icons/              # Ícones e recursos gráficos
├── scripts_exemplo/        # Exemplos de configuração e scripts
├── tests/                  # Testes unitários
├── docs/                   # Documentação técnica
├── via                     # Launcher executável
├── requirements.txt        # Dependências Python
└── README.md
```

## Requisitos

* **Sistema Operativo:** Linux (testado em Debian)
* **Python:** 3.10+
* **Dependências Python:** `PySide6` (listadas em `requirements.txt`)
* **Motor Local (opcional, recomendado):** [Ollama](https://ollama.com/) a correr localmente (`http://localhost:11434`)
* **Utilitários opcionais:**
  * `poppler-utils` (`pdftotext`) para extração rápida de texto de ficheiros PDF.

### Instalação das dependências (Debian / Ubuntu)

```bash
sudo apt update
sudo apt install python3-pyside6.qtwidgets python3-pyside6.qtcore python3-pyside6.qtgui poppler-utils
```

*(Alternativamente, num ambiente virtual Python: `pip install -r requirements.txt`)*

Para suporte a modelos locais offline, instale o Ollama:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

## Instalação e Utilização

1. Clone o repositório e verifique as permissões de execução:

```bash
git clone https://github.com/PauloJSPinhal/vIA.git
cd vIA
chmod +x via src/via.py
```

2. (Opcional) Crie um link simbólico para o lançar a partir de qualquer lugar:

```bash
mkdir -p ~/.local/bin
ln -sf "$(pwd)/via" ~/.local/bin/via
```

3. Execute a aplicação:

```bash
via
```

## Configuração de Chaves API Externas (Opcional)

Se pretender utilizar modelos externos (necessários para análise de imagens caso não utilize um modelo de visão local como o `qwen2.5vl:3b`), exporte as chaves no seu `~/.profile` ou `~/.zshenv` (para que fiquem disponíveis também ao lançar pelo menu gráfico):

```bash
export GEMINI_API_KEY="a_sua_chave_gemini"
export GROQ_API_KEY="a_sua_chave_groq"
export DEEPSEEK_API_KEY="a_sua_chave_deepseek"
```

## Estrutura de Configuração

Ao iniciar pela primeira vez, o **vIA** cria a pasta `~/.config/via/` com dois ficheiros JSON editáveis tanto pela interface gráfica como manualmente:

* `~/.config/via/config.json` — Guarda o modelo ativo, temperatura, *timeout* e as regras de comportamento da IA.
* `~/.config/via/scripts.json` — Catálogo dos scripts registados, caminhos, descrições e flags de segurança (`args` e `perigoso`).

## Modelos Recomendados por Perfil de Máquina

| Perfil de Hardware | Modelo Sugerido | Consumo Aprox. | Notas |
| :--- | :--- | :--- | :--- |
| **Portátil básico (4 GB RAM)** | `ollama:qwen2.5:0.5b` | ~400 MB RAM | Resposta rápida em CPUs antigos; ideal como router de scripts. |
| **Portátil padrão (8 GB RAM)** | `ollama:qwen2.5-coder:1.5b` | ~1.1 GB RAM | Melhor equilíbrio entre velocidade em CPU e rigor em Bash/Python. |
| **Portátil moderno (8–16 GB RAM)** | `ollama:qwen2.5-coder:3b` | ~2.0 GB RAM | Excelente compreensão de contexto e extração de argumentos. |
| **Workstation / GPU Dedicada** | `ollama:qwen2.5-coder:7b` | ~4.7 GB VRAM/RAM | Alta precisão em tarefas complexas de código. |
| **Análise de Imagens / PDFs** | `gemini:gemini-2.5-flash` | Cloud (API) | Sem consumo de RAM local; suporte nativo a visão e OCR. |

## Licença

Distribuído sob a licença MIT. Consulte o ficheiro `LICENSE` para mais informações.