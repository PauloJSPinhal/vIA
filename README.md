# vIA

Um assistente de desktop leve e nativo (PySide6 / Qt 6) que atua como canal direto entre pedidos em linguagem natural e a execução segura da sua biblioteca pessoal de scripts (`.sh` e `.py`), permitindo também conversar e analisar documentos, código e imagens.

Concebido para funcionar desde portáteis modestos com 4 GB de RAM (usando modelos ultraleves locais via **Ollama**) até workstations com GPU dedicada ou APIs externas (**Gemini**, **Groq** e **DeepSeek**).

## Funcionalidades Principais

* **Router Inteligente de Scripts:** Mapeia pedidos em linguagem natural para os seus scripts locais e extrai automaticamente argumentos (caminhos de ficheiros, dispositivos `/dev/sdX`, etc.).
* **Execução Segura com Confirmação Visual:** Nenhum script corre sem aprovação explícita. Scripts marcados como destrutivos exibem um alerta crítico com confirmação adicional e o comando completo é mostrado antes de executar. A saída (`stdout`/`stderr`) aparece em tempo real e o processo pode ser interrompido a qualquer momento.
* **Tempo Limite de Execução:** Scripts que excedem o tempo configurado são terminados automaticamente (`terminate`, com `kill` após 3 s). Pode definir 0 para desativar o limite.
* **Suporte Híbrido (Local + Nuvem):**
  * **Ollama Local:** Deteta automaticamente todos os modelos instalados via `/api/tags`.
  * **APIs Externas:** Lê as chaves `GEMINI_API_KEY`, `GROQ_API_KEY` e `DEEPSEEK_API_KEY` do ambiente e descobre os modelos realmente disponíveis nos endpoints `/models` de cada serviço.
* **Descoberta Automática de Modelos (sem catálogos embutidos):** No primeiro arranque a aplicação consulta o Ollama e as APIs configuradas e preenche o seletor apenas com o que existe. Se instalares novos modelos ou adicionares chaves, o botão **Atualizar Modelos** volta a fazer a descoberta.
* **Diagnóstico de Hardware:** Analisa CPU, RAM disponível e GPU (`nvidia-smi`) e mostra a informação na interface e no contexto enviado à IA.
* **Chaves nunca guardadas em disco:** As chaves são lidas apenas das variáveis de ambiente e nunca são escritas em JSON, logs ou URLs. Os ficheiros de configuração são gravados com permissões `0600` e a pasta com `0700`.
* **Análise de Múltiplos Ficheiros (Drag & Drop):** Permite anexar ou arrastar imagens (`.jpg`, `.png`, `.webp`), documentos `.pdf` (via `pdftotext` ou `pypdf`), logs e código para análise, com limites de tamanho e proteção contra binários.
* **Gestor Gráfico de Scripts & Regras:** Adicione, edite ou remova scripts e ajuste o *system prompt*, temperatura e tempos limite sem editar código.
* **Integração Nativa & XDG:** Guarda todas as configurações em `~/.config/via/` (ou `$XDG_CONFIG_HOME/via`). Configurações antigas em `~/.config/assistente/` são migradas automaticamente no primeiro arranque.

## Estrutura do Projeto

```text
vIA/
├── src/
│   ├── main.py             # Ponto de entrada da aplicação
│   └── via/
│       ├── app.py          # Bootstrap Qt
│       ├── constants.py    # Caminhos e limites (sem modelos embutidos)
│       ├── config.py       # Persistência, validação e migração
│       ├── discovery.py    # Descoberta de modelos (Ollama + APIs /models)
│       ├── hardware.py     # Diagnóstico de hardware e chaves
│       ├── prompt.py       # Construção dos prompts
│       ├── respostas.py    # Parse JSON e capacidades de visão
│       ├── workers.py      # Threads de IA e download de modelos
│       ├── providers/      # Conectores (Ollama, Gemini, Groq, DeepSeek)
│       ├── parsers/        # Leitores de anexos (PDF, imagens, texto/código)
│       └── ui/             # Componentes gráficos PySide6
├── assets/
│   └── icons/              # Ícones da aplicação (via.svg / via.png)
├── scripts_exemplo/        # Exemplos de scripts.json e config.json
├── tests/                  # Testes unitários do núcleo
├── docs/                   # Documentação técnica (ARQUITETURA.md)
├── script/                 # install.sh e uninstall.sh
├── via                     # Launcher executável
├── LICENSE                 # Licença MIT
├── requirements.txt        # Dependências Python
└── README.md
```

## Requisitos

* **Sistema Operativo:** Linux (testado em Debian)
* **Python:** 3.10+
* **Dependências Python:** `PySide6` e `pypdf` (listadas em `requirements.txt`)
* **Motor Local (opcional, recomendado):** [Ollama](https://ollama.com/) a correr localmente (`http://localhost:11434`)
* **Utilitários opcionais:**
  * `poppler-utils` (`pdftotext`) para extração rápida de texto de ficheiros PDF.
  * `pypdf` (incluído em `requirements.txt`) como alternativa quando não existe `pdftotext`.

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

1. Clone o repositório:

```bash
git clone https://github.com/PauloJSPinhal/vIA.git
cd vIA
```

2. Execute o instalador (cria o comando `via` e o atalho no menu de aplicações):

```bash
./script/install.sh
```

3. Execute a aplicação:

```bash
via
```

O instalador pode ser revertido com `./script/uninstall.sh` (pergunta antes de apagar configurações).

### Execução sem instalar

```bash
chmod +x via src/main.py
./via
```

Ou, diretamente a partir de `src`:

```bash
cd src && python3 -m via
```

### Primeiro arranque

1. A aplicação cria `~/.config/via/` e descobre os modelos disponíveis
   (Ollama + APIs cujas chaves estejam no ambiente). **Não instala modelos
   automaticamente.**
2. Abre o separador **Configurações**. Se houver vários modelos, o seletor
   começa vazio: escolhe um e clica em **Guardar Configurações**.
3. Se quiseres instalar um modelo local, escreve a tag no seletor
   (ex.: `modelo:tag`) e clica em **Instalar Ollama (Pull)**. No fim, a lista
   é atualizada automaticamente.
4. Para voltar a procurar modelos depois de instalares mais algum ou de
   definires novas chaves, clica em **Atualizar Modelos**.

## Configuração de Chaves API Externas (Opcional)

Se pretender utilizar modelos externos, exporte as chaves no seu `~/.profile` ou `~/.zshenv` (para que fiquem disponíveis também ao lançar pelo menu gráfico):

```bash
export GEMINI_API_KEY="a_sua_chave_gemini"
export GROQ_API_KEY="a_sua_chave_groq"
export DEEPSEEK_API_KEY="a_sua_chave_deepseek"
```

> **Importante:** o vIA **não guarda chaves nem palavras-passe em plaintext**.
> As variáveis acima são lidas do ambiente em cada arranque/atualização e só
> existem em memória durante a sessão. A aplicação também remove campos
> sensíveis (`api_key`, `token`, `password`, etc.) antes de qualquer escrita
> em disco, e nunca envia a chave na URL (usa cabeçalhos HTTP).
>
> As variáveis só ficam disponíveis em processos iniciados depois de serem
> exportadas. Se acabaste de as definir, fecha e volta a abrir o vIA (ou
> lança-o a partir de um terminal com essas variáveis) e clica em
> **Atualizar Modelos**.

## Estrutura de Configuração

Ao iniciar pela primeira vez, o **vIA** cria a pasta `~/.config/via/` com dois ficheiros JSON editáveis tanto pela interface gráfica como manualmente:

* `~/.config/via/config.json` — Guarda o modelo ativo (vazio até escolheres um), temperatura, tempos limite e as regras de comportamento da IA.
* `~/.config/via/scripts.json` — Catálogo dos scripts registados, caminhos, descrições e flags de segurança (`args` e `perigoso`).

Os ficheiros são criados com permissões `0600` e a pasta com `0700`.

> **Migração:** se existir configuração da versão antiga em `~/.config/assistente/`,
> os ficheiros são copiados automaticamente para `~/.config/via/` no primeiro
> arranque, sem apagar os originais.

Exemplos dos dois ficheiros estão em `scripts_exemplo/`.

## Descoberta de Modelos

No arranque, e sempre que clicas em **Atualizar Modelos** (separador
Configurações), a aplicação:

1. Consulta `http://localhost:11434/api/tags` e lista os modelos Ollama instalados (com tamanho).
2. Se `GEMINI_API_KEY` existir, consulta `GET /v1beta/models` e inclui apenas os modelos com `generateContent` (exclui imagem/áudio/TTS/embeddings).
3. Se `GROQ_API_KEY` existir, consulta `GET https://api.groq.com/openai/v1/models` e exclui modelos de áudio/embeddings/moderação.
4. Se `DEEPSEEK_API_KEY` existir, consulta `GET https://api.deepseek.com/models`.

Cada provedor é consultado em paralelo; a falha de um não impede os restantes.
A lista é reconstruída de cada vez — não há catálogo de modelos no código.

- Se existir apenas **um** modelo, é adotado automaticamente.
- Se existirem **vários**, o seletor fica sem seleção; escolhe um e guarda.
- Se o modelo guardado já não existir, a aplicação avisa e pede para escolher outro.
- Modelos com capacidade de visão são identificados pelo nome/tipo no seletor; anexar imagens a um modelo sem visão mostra um erro claro.

## Sugestões de Modelos (referência manual)

O vIA não embute catálogos; a tabela seguinte serve apenas como referência
para instalar modelos via Ollama ou usar uma API.

| Perfil de Hardware | Modelo Sugerido | Consumo Aprox. | Notas |
| :--- | :--- | :--- | :--- |
| **Portátil básico (4 GB RAM)** | `qwen2.5:0.5b` | ~400 MB RAM | Resposta rápida em CPUs antigos; ideal como router de scripts. |
| **Portátil padrão (8 GB RAM)** | `qwen2.5-coder:1.5b` | ~1.1 GB RAM | Melhor equilíbrio entre velocidade em CPU e rigor em Bash/Python. |
| **Portátil moderno (8–16 GB RAM)** | `qwen2.5-coder:3b` | ~2.0 GB RAM | Excelente compreensão de contexto e extração de argumentos. |
| **Workstation / GPU Dedicada** | `qwen2.5-coder:7b` | ~4.7 GB VRAM/RAM | Alta precisão em tarefas complexas de código. |
| **Análise de Imagens / PDFs** | Qualquer modelo com visão detetado | Depende | O seletor mostra Gemini, Groq multimodal ou Ollama com `vl`/`vision`/`llava`. |

> Como os modelos são descobertos em runtime, entradas obsoletas ou removidas
> pelos fornecedores deixam de aparecer automaticamente. Se o modelo guardado
> na configuração já não existir, a aplicação avisa e pede para escolher outro.

## Desenvolvimento e Testes

```bash
python3 -m unittest discover -s tests -v
```

Os testes cobrem o parse de respostas dos modelos, normalização/migração da
configuração, descoberta multi-provedor, sanitização de segredos, permissões
dos ficheiros, validação de scripts e limites de anexos. Não requerem servidor
gráfico nem ligação à rede (as chamadas externas são simuladas com
`unittest.mock`). Consulte `docs/ARQUITETURA.md` para o detalhe dos módulos e
do fluxo de execução.

## Segurança em Resumo

* Nenhum script corre sem confirmação e sem o comando completo visível.
* Scripts destrutivos exigem confirmação adicional.
* Execuções têm tempo limite configurável e podem ser interrompidas.
* Argumentos são passados em lista (sem `shell=True`).
* Chaves/passwords nunca são gravadas em disco; a configuração é `0600` e a
  pasta `0700`.
* Conteúdo de anexos é tratado como dados, nunca como instruções para a IA.

## Licença

Distribuído sob a licença MIT. Consulte o ficheiro [LICENSE](LICENSE) para mais informações.
