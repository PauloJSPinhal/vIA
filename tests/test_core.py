"""Testes unitários do núcleo do vIA (sem interface gráfica)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from via import config, constants as C, discovery, respostas  # noqa: E402
from via.parsers import anexos  # noqa: E402
from via.prompt import construir_prompt_sistema, construir_prompt_utilizador  # noqa: E402
from via.providers.base import ErroProvider  # noqa: E402


class TestRespostas(unittest.TestCase):
    def test_json_com_cerca_markdown(self):
        texto = '```json\n{"acao": "conversar", "resposta": "Olá"}\n```'
        decisao = respostas.extrair_json_resposta(texto)
        self.assertEqual(decisao["acao"], "conversar")
        self.assertEqual(decisao["resposta"], "Olá")

    def test_remove_bloco_think(self):
        texto = '<think>passo interno</think>{"acao": "conversar", "resposta": "ok"}'
        self.assertEqual(respostas.extrair_json_resposta(texto)["resposta"], "ok")

    def test_texto_livre_vira_conversa(self):
        decisao = respostas.extrair_json_resposta("Não consigo responder em JSON.")
        self.assertEqual(decisao["acao"], "conversar")
        self.assertIn("Não consigo", decisao["resposta"])

    def test_json_embutido_em_prosa(self):
        texto = 'Claro! {"acao": "conversar", "resposta": "feito"} Espero ajudar.'
        self.assertEqual(respostas.extrair_json_resposta(texto)["resposta"], "feito")

    def test_acao_invalida_e_normalizada(self):
        for acao in ("executar_tudo", "instalar_modelo"):
            decisao = respostas.extrair_json_resposta(json.dumps({"acao": acao}))
            self.assertEqual(decisao["acao"], "conversar")

    def test_campos_em_falta(self):
        decisao = respostas.extrair_json_resposta('{"resposta": "só isto"}')
        self.assertIsNone(decisao["script"])
        self.assertEqual(decisao["argumento"], "")

    def test_suporta_visao(self):
        self.assertTrue(respostas.suporta_visao("gemini", "gemini-2.5-flash"))
        self.assertTrue(respostas.suporta_visao("groq", "qwen/qwen3.8-27b"))
        self.assertFalse(respostas.suporta_visao("groq", "llama-3.1-8b-instant"))
        self.assertFalse(respostas.suporta_visao("deepseek", "deepseek-chat"))
        self.assertTrue(respostas.suporta_visao("ollama", "qwen2.5vl:3b"))


class TestConfig(unittest.TestCase):
    def test_normalizar_modelo(self):
        self.assertEqual(config.normalizar_modelo("llama3.2"), "ollama:llama3.2")
        self.assertEqual(config.normalizar_modelo("ollama:qwen2.5:0.5b"), "ollama:qwen2.5:0.5b")
        self.assertEqual(config.normalizar_modelo(""), "")
        self.assertEqual(config.normalizar_modelo(None), "")

    def test_normalizar_config_limita_valores(self):
        cfg = config.normalizar_config({
            "modelo": "llama3.2",
            "temperatura": 9,
            "timeout": 1,
            "timeout_script": -5,
            "regras": "   ",
        })
        self.assertEqual(cfg["modelo"], "ollama:llama3.2")
        self.assertEqual(cfg["temperatura"], 2.0)
        self.assertEqual(cfg["timeout"], 10)
        self.assertEqual(cfg["timeout_script"], 0)
        self.assertEqual(cfg["regras"], C.DEFAULT_CONFIG["regras"])

    def test_nome_script_valido(self):
        self.assertTrue(config.nome_script_valido("audio-reset"))
        self.assertTrue(config.nome_script_valido("backup.sh"))
        self.assertFalse(config.nome_script_valido("../etc/passwd"))
        self.assertFalse(config.nome_script_valido(""))

    def test_migracao_da_pasta_antiga(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            novo = base / "via"
            antigo = base / "assistente"
            antigo.mkdir()
            (antigo / "config.json").write_text(
                '{"modelo": "llama3.2", "temperatura": 0.5}', encoding="utf-8"
            )
            (antigo / "scripts.json").write_text("{}", encoding="utf-8")

            with mock.patch.object(C, "CONFIG_DIR", novo), \
                 mock.patch.object(C, "CONFIG_FILE", novo / "config.json"), \
                 mock.patch.object(C, "SCRIPTS_FILE", novo / "scripts.json"), \
                 mock.patch.object(C, "CONFIG_LEGADO_DIR", antigo):
                migrados = config.migrar_config_legada()
                self.assertEqual(sorted(migrados), ["config.json", "scripts.json"])
                cfg = config.carregar_config()
                self.assertEqual(cfg["modelo"], "ollama:llama3.2")
                self.assertEqual(cfg["temperatura"], 0.5)

    def test_carregar_scripts_filtra_entradas_invalidas(self):
        with tempfile.TemporaryDirectory() as tmp:
            ficheiro = Path(tmp) / "scripts.json"
            ficheiro.write_text(json.dumps({
                "bom": {"caminho": "/tmp/x.sh", "descricao": "ok"},
                "sem-caminho": {"descricao": "inválido"},
                "nao-dict": "lixo",
            }), encoding="utf-8")

            with mock.patch.object(C, "CONFIG_DIR", Path(tmp)), \
                 mock.patch.object(C, "CONFIG_FILE", Path(tmp) / "config.json"), \
                 mock.patch.object(C, "SCRIPTS_FILE", ficheiro):
                scripts = config.carregar_scripts()
                self.assertEqual(list(scripts), ["bom"])
                self.assertFalse(scripts["bom"]["perigoso"])
                self.assertFalse(scripts["bom"]["args"])


class TestSegredos(unittest.TestCase):
    def test_remover_segredos_recursivo(self):
        dados = {
            "modelo": "ollama:x",
            "api_key": "SEGREDO",
            "aninhado": {"token": "SEGREDO2", "ok": 1},
            "lista": [{"password": "SEGREDO3"}, {"ok": 2}],
        }
        limpo = config._remover_segredos(dados)
        texto = json.dumps(limpo)
        self.assertNotIn("SEGREDO", texto)
        self.assertNotIn("api_key", texto)
        self.assertIn("ollama:x", texto)

    def test_guardar_config_nunca_escreve_segredos(self):
        with tempfile.TemporaryDirectory() as tmp:
            ficheiro = Path(tmp) / "config.json"
            with mock.patch.object(C, "CONFIG_DIR", Path(tmp)), \
                 mock.patch.object(C, "CONFIG_FILE", ficheiro):
                config.guardar_config({
                    **C.DEFAULT_CONFIG,
                    "modelo": "ollama:teste",
                    "api_key": "SEGREDO123",
                    "aninhado": {"token": "SEGREDO456"},
                })
                texto = ficheiro.read_text(encoding="utf-8")
                self.assertNotIn("SEGREDO123", texto)
                self.assertNotIn("SEGREDO456", texto)
                self.assertNotIn("api_key", texto)
                modo = ficheiro.stat().st_mode & 0o777
                self.assertEqual(modo, 0o600)

    def test_diretorio_config_privado(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "via"
            with mock.patch.object(C, "CONFIG_DIR", destino):
                config.garantir_diretorio_config()
                modo = destino.stat().st_mode & 0o777
                self.assertEqual(modo, 0o700)


class TestDescoberta(unittest.TestCase):
    def test_apenas_ollama_sem_chaves(self):
        with mock.patch.object(
            discovery.ollama, "listar_modelos_info",
            return_value=[{"id": "llama3.2:1b", "detalhe": "1.3 GB"}],
        ), mock.patch.object(discovery.gemini, "listar_modelos") as gemini_lista, \
           mock.patch.object(discovery.openai_compat, "listar_modelos") as openai_lista:
            modelos, avisos = discovery.descobrir_modelos({})

        gemini_lista.assert_not_called()
        openai_lista.assert_not_called()
        self.assertEqual(avisos, [])
        self.assertEqual(len(modelos), 1)
        self.assertEqual(modelos[0].modelo_id, "ollama:llama3.2:1b")
        self.assertIn("[Local]", modelos[0].rotulo)

    def test_falha_de_provedor_nao_impede_os_outros(self):
        with mock.patch.object(discovery.ollama, "listar_modelos_info", return_value=None), \
             mock.patch.object(
                 discovery.gemini, "listar_modelos",
                 side_effect=ErroProvider("chave inválida"),
             ), mock.patch.object(
                 discovery.openai_compat, "listar_modelos",
                 return_value=[{"id": "deepseek-chat"}],
             ):
            modelos, avisos = discovery.descobrir_modelos({
                "GEMINI_API_KEY": "x",
                "DEEPSEEK_API_KEY": "y",
                "GROQ_API_KEY": "z",
            })

        ids = {m.modelo_id for m in modelos}
        self.assertIn("deepseek:deepseek-chat", ids)
        self.assertTrue(any("Gemini" in aviso for aviso in avisos))
        self.assertTrue(any("Ollama" in aviso for aviso in avisos))

    def test_groq_ignora_modelos_nao_conversacionais(self):
        with mock.patch.object(discovery.ollama, "listar_modelos_info", return_value=[]), \
             mock.patch.object(
                 discovery.openai_compat, "listar_modelos",
                 return_value=[
                     {"id": "llama-3.1-8b-instant"},
                     {"id": "whisper-large-v3"},
                     {"id": "meta-llama/llama-guard-4-12b"},
                 ],
             ):
            modelos, _avisos = discovery.descobrir_modelos({"GROQ_API_KEY": "x"})

        ids = {m.modelo_id for m in modelos}
        self.assertIn("groq:llama-3.1-8b-instant", ids)
        self.assertNotIn("groq:whisper-large-v3", ids)
        self.assertNotIn("groq:meta-llama/llama-guard-4-12b", ids)

    def test_gemini_ignora_modelos_de_imagem_audio_tts(self):
        with mock.patch.object(discovery.ollama, "listar_modelos_info", return_value=[]), \
             mock.patch.object(
                 discovery.gemini, "listar_modelos",
                 return_value=[
                     {"id": "gemini-2.5-flash", "nome": "Gemini 2.5 Flash"},
                     {"id": "gemini-2.5-flash-image", "nome": "Imagem"},
                     {"id": "gemini-2.5-flash-preview-tts", "nome": "TTS"},
                 ],
             ):
            modelos, _avisos = discovery.descobrir_modelos({"GEMINI_API_KEY": "x"})

        ids = {m.modelo_id for m in modelos}
        self.assertIn("gemini:gemini-2.5-flash", ids)
        self.assertNotIn("gemini:gemini-2.5-flash-image", ids)
        self.assertNotIn("gemini:gemini-2.5-flash-preview-tts", ids)


class TestAnexos(unittest.TestCase):
    def test_texto_truncado(self):
        with tempfile.TemporaryDirectory() as tmp:
            ficheiro = Path(tmp) / "nota.txt"
            ficheiro.write_text("abcdefghij", encoding="utf-8")
            with mock.patch.object(anexos.C, "TAMANHO_MAX_TEXTO", 4):
                imagens, texto, avisos = anexos.preparar_anexos([str(ficheiro)])
            self.assertEqual(imagens, [])
            self.assertEqual(avisos, [])
            self.assertIn("abcd", texto)
            self.assertNotIn("abcdefghij", texto)
            self.assertIn("truncado", texto)

    def test_binario_ignorado(self):
        with tempfile.TemporaryDirectory() as tmp:
            ficheiro = Path(tmp) / "dados.bin"
            ficheiro.write_bytes(b"\x00\x01\x02\x03" * 100)
            imagens, texto, avisos = anexos.preparar_anexos([str(ficheiro)])
            self.assertEqual(imagens, [])
            self.assertEqual(texto, "")
            self.assertTrue(any("binário" in a for a in avisos))

    def test_imagem_demasiado_grande_ignorada(self):
        with tempfile.TemporaryDirectory() as tmp:
            ficheiro = Path(tmp) / "foto.png"
            ficheiro.write_bytes(b"x" * 32)
            with mock.patch.object(anexos.C, "TAMANHO_MAX_IMAGEM", 10):
                imagens, _texto, avisos = anexos.preparar_anexos([str(ficheiro)])
            self.assertEqual(imagens, [])
            self.assertTrue(any("limite" in a for a in avisos))

    def test_imagem_valida_em_base64(self):
        with tempfile.TemporaryDirectory() as tmp:
            ficheiro = Path(tmp) / "foto.png"
            ficheiro.write_bytes(b"\x89PNG\r\n\x1a\n")
            imagens, texto, _avisos = anexos.preparar_anexos([str(ficheiro)])
            self.assertEqual(len(imagens), 1)
            self.assertEqual(imagens[0]["mime"], "image/png")
            self.assertTrue(imagens[0]["b64"])
            self.assertIn("Imagem anexada", texto)


class TestPrompt(unittest.TestCase):
    def test_prompt_avisa_contra_instrucoes_em_anexos(self):
        prompt = construir_prompt_sistema(
            regras="Regras base",
            hardware="CPU teste",
            modelo_ativo="ollama:teste",
            scripts={"demo": {"descricao": "faz algo"}},
        )
        self.assertIn("DADOS a analisar", prompt)
        self.assertIn("- demo: faz algo", prompt)
        self.assertIn("ollama:teste", prompt)
        self.assertNotIn("modelo_recomendado", prompt)

    def test_prompt_utilizador_com_anexos(self):
        prompt = construir_prompt_utilizador("Analisa", "--- ficheiro ---")
        self.assertIn("Analisa", prompt)
        self.assertIn("--- ficheiro ---", prompt)


if __name__ == "__main__":
    unittest.main()
