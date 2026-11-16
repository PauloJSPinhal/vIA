# Arquitetura do vIA

## Objetivo

O vIA é uma aplicação desktop Linux (PySide6/Qt 6) que:

1. Descobre em runtime os modelos realmente disponíveis (Ollama local e APIs
   externas cujas chaves estejam no ambiente);
2. Traduz pedidos em linguagem natural para a execução de scripts locais
   (`.sh`/`.py`), sempre com confirmação explícita do utilizador;
3. Conversa e analisa ficheiros anexados (imagens, PDFs, texto/código).

Não existem catálogos de modelos embutidos no código: o seletor é reconstruído
a cada arranque e sempre que o utilizador clica em **Atualizar Modelos**.

## Estrutura de módulos

```text
src/
├── main.py                  # Ponto de entrada (ajusta sys.path e chama via.app)
├── via/
│   ├── app.py               # Bootstrap Qt (QApplication, ícone, migração)
│   ├── constants.py         # Caminhos XDG, limites, valores por omissão
│   ├── config.py            # Persistência atómica + migração + sanitização
│   ├── discovery.py         # Descoberta paralela de modelos
│   ├── hardware.py          # CPU/RAM/GPU e deteção de chaves de ambiente
│   ├── prompt.py            # Construção do prompt de sistema/utilizador
│   ├── respostas.py         # Parse da resposta JSON + capacidades de visão
│   ├── workers.py           # QThread: descoberta, IA e pull de modelos
│   ├── parsers/
│   │   └── anexos.py        # Imagens -> base64, PDF -> texto, texto/código
│   ├── providers/
│   │   ├── base.py          # Cliente HTTP + ErroProvider (mensagens em PT)
│   │   ├── ollama.py        # /api/tags, /api/generate, /api/pull
│   │   ├── gemini.py        # /v1beta/models e generateContent
│   │   └── openai_compat.py # Groq e DeepSeek (chat e /models)
│   └── ui/
│       └── main_window.py   # Janela principal (3 separadores)
└── tests/test_core.py       # Testes do núcleo (sem GUI)
```

## Descoberta de modelos

`discovery.descobrir_modelos(chaves)` executa as fontes **em paralelo**
(`ThreadPoolExecutor`), com `DESCOBERTA_TIMEOUT` por fonte:

| Provedor | Chamada | Filtro |
| :--- | :--- | :--- |
| Ollama | `GET /api/tags` | Nenhum; mostra nome e tamanho |
| Gemini | `GET /v1beta/models` (header `x-goog-api-key`) | Apenas `supportedGenerationMethods` com `generateContent`; exclui imagem/áudio/TTS/embeddings |
| Groq | `GET https://api.groq.com/openai/v1/models` | Exclui `whisper`, `tts`, `guard`, `embed`, `rerank`, `orpheus`, `moderation` |
| DeepSeek | `GET https://api.deepseek.com/models` | Nenhum |

Regras:

- A falha de um provedor gera um aviso e não impede os restantes.
- Se não existir nenhuma chave, apenas o Ollama é consultado.
- A lista é apresentada como `ModeloDisponivel` (`modelo_id`, `nome`, `provedor`,
  `detalhe`) e formatada por `ModeloDisponivel.rotulo`
  (ex.: `[Local] qwen2.5-coder:1.5b — 0.9 GB`).
- Se a configuração não tiver modelo e houver exatamente um disponível, é
  adotado automaticamente; com vários, o utilizador escolhe e guarda.
- Modelos guardados que já não sejam descobertos geram um aviso (não são
  substituídos silenciosamente).

## Fluxo de um pedido

```text
QLineEdit / drag&drop
        │
        ▼
ViaWindow.enviar_pedido()
        │  cria
        ▼
AssistenteWorker (QThread)
        ├── preparar_anexos() ── imagens base64 / texto / PDF
        ├── construir_prompt_sistema() ── regras + hardware + scripts
        ├── provedor escolhido (ollama | gemini | groq | deepseek)
        ├── extrair_json_resposta()
        └── signal resultado_pronto(dict)
        │
        ▼
ViaWindow.tratar_resposta_ia()
        ├── acao == "executar"  -> painel de confirmação -> QProcess
        └── acao == "conversar" -> apenas mostra a resposta
```

### Contrato de resposta do modelo

```json
{
  "acao": "executar | conversar",
  "script": "nome_do_script ou null",
  "argumento": "texto ou \"\"",
  "resposta": "texto para o utilizador"
}
```

`respostas.extrair_json_resposta()` normaliza a saída:

- remove blocos `<think>…</think>` (DeepSeek-R1) e cercas markdown;
- tenta extrair um objeto JSON embutido em texto livre;
- garante tipos e chaves obrigatórias;
- qualquer `acao` desconhecida (incluindo a antiga `instalar_modelo`) passa a
  `conversar`.

## Persistência e segredos

| Caminho | Conteúdo | Permissões |
| :--- | :--- | :--- |
| `$XDG_CONFIG_HOME/via/config.json` | Modelo, temperatura, timeouts, regras | `0600` |
| `$XDG_CONFIG_HOME/via/scripts.json` | Catálogo de scripts | `0600` |
| `$XDG_CONFIG_HOME/via/` | Pasta de configuração | `0700` |
| `~/.config/assistente/` | Localização antiga (migrada por cópia) | — |

**Chaves API nunca são persistidas.** São lidas de `GEMINI_API_KEY`,
`GROQ_API_KEY` e `DEEPSEEK_API_KEY` a cada descoberta/pedido e usadas apenas em
memória. Antes de qualquer escrita em disco, `config._remover_segredos()`
remove recursivamente campos como `api_key`, `token`, `password` e `secret`.
A chave da Gemini é enviada no cabeçalho `x-goog-api-key` (nunca na URL).

Escritas usam ficheiro temporário + `fsync` + `os.replace` (atómico). Um JSON
inválido é preservado como `config.json.invalido` antes de se repor o padrão.

## Segurança da execução

- `QProcess` recebe o programa e os argumentos em **lista** (nunca `shell=True`).
- O comando completo é mostrado com `shlex.join` antes de qualquer execução.
- Scripts com `perigoso: true` exigem uma confirmação adicional.
- O caminho do script é validado antes da confirmação (tem de existir).
- Argumentos são truncados a 4096 caracteres; scripts marcados com `args: false`
  ignoram o argumento extraído.
- `timeout_script` (0 = sem limite) termina o processo com `terminate()` e,
  após 3 s, `kill()`.
- O utilizador pode parar o processo a qualquer momento (“Parar Execução”).
- O conteúdo de anexos é enviado explicitamente como **dados**, e o prompt
  instrui o modelo a ignorar instruções embutidas nesses ficheiros.

## Limites de anexos

| Recurso | Limite |
| :--- | :--- |
| Texto/código | 30 000 caracteres |
| PDF | 25 000 caracteres |
| Imagem | 10 MB, máximo 8 por pedido |
| Anexos por pedido | 20 |

Ficheiros binários desconhecidos são ignorados com aviso em vez de injetados
na prompt como texto corrompido.

## Testes

```bash
python3 -m unittest discover -s tests -v
```

Os testes não requerem servidor gráfico nem rede (as chamadas de descoberta são
simuladas com `unittest.mock`): cobrem parse de respostas, normalização e
migração de configuração, sanitização de segredos, permissões dos ficheiros,
descoberta de modelos, validação de scripts, limites de anexos e prompts.
