"""Leitura e preparação de ficheiros anexados (imagens, PDFs, texto/código)."""

import base64
import shutil
import subprocess
from pathlib import Path

from via import constants as C

EXTENSOES_IMAGEM = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


def _parece_binario(amostra: bytes) -> bool:
    """Heurística simples para não despejar binários na prompt."""
    if b"\x00" in amostra:
        return True
    try:
        amostra.decode("utf-8")
        return False
    except UnicodeDecodeError:
        pass
    texto = amostra.decode("latin-1", errors="replace")
    imprimiveis = sum(1 for c in texto if c.isprintable() or c in "\n\r\t")
    return (imprimiveis / max(len(texto), 1)) < 0.75


def _ler_texto(caminho: Path) -> tuple[str, bool]:
    """Lê até :data:`C.TAMANHO_MAX_TEXTO` caracteres. Devolve (texto, truncado)."""
    with open(caminho, "r", encoding="utf-8", errors="replace") as f:
        conteudo = f.read(C.TAMANHO_MAX_TEXTO + 1)
    truncado = len(conteudo) > C.TAMANHO_MAX_TEXTO
    return conteudo[:C.TAMANHO_MAX_TEXTO], truncado


def _ler_pdf(caminho: Path) -> str:
    if shutil.which("pdftotext"):
        try:
            saida = subprocess.check_output(
                ["pdftotext", "-layout", str(caminho), "-"],
                text=True, stderr=subprocess.DEVNULL, timeout=15,
            )
            if saida.strip():
                return saida
        except (OSError, subprocess.SubprocessError):
            pass

    try:
        import pypdf  # dependência opcional
        reader = pypdf.PdfReader(str(caminho))
        return "\n".join((pagina.extract_text() or "") for pagina in reader.pages)
    except ImportError:
        return (
            "(Não foi possível extrair texto: instala 'poppler-utils' (pdftotext) "
            "ou 'pypdf' com 'pip install pypdf'.)"
        )
    except Exception:
        return (
            "(Não foi possível extrair texto deste PDF — pode ser um documento "
            "digitalizado como imagem, sem OCR.)"
        )


def preparar_anexos(caminhos: list[str]) -> tuple[list[dict], str, list[str]]:
    """Converte anexos em (imagens base64, bloco de texto, avisos).

    Aplica limites de tamanho/quantidade e ignora ficheiros binários
    desconhecidos em vez de os injetar na prompt como texto corrompido.
    """
    imagens: list[dict] = []
    textos_anexos: list[str] = []
    avisos: list[str] = []

    for caminho_str in caminhos:
        caminho = Path(caminho_str).expanduser()
        if not caminho.is_file():
            avisos.append(f"Ignorado (não é um ficheiro válido): {caminho_str}")
            continue

        extensao = caminho.suffix.lower()

        # 1. Imagens (formatos suportados pela maioria dos modelos de visão)
        if extensao in EXTENSOES_IMAGEM:
            if len(imagens) >= C.MAX_IMAGENS:
                avisos.append(
                    f"Ignorada '{caminho.name}': limite de {C.MAX_IMAGENS} imagens por pedido."
                )
                continue
            try:
                tamanho = caminho.stat().st_size
            except OSError as exc:
                avisos.append(f"Erro ao ler '{caminho.name}': {exc}")
                continue
            if tamanho > C.TAMANHO_MAX_IMAGEM:
                avisos.append(
                    f"Ignorada '{caminho.name}': excede o limite de "
                    f"{C.TAMANHO_MAX_IMAGEM // (1024 * 1024)} MB."
                )
                continue
            try:
                with open(caminho, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
            except OSError as exc:
                avisos.append(f"Erro ao ler '{caminho.name}': {exc}")
                continue
            imagens.append({
                "nome": caminho.name,
                "caminho": str(caminho),
                "mime": EXTENSOES_IMAGEM[extensao],
                "b64": b64,
            })
            textos_anexos.append(f"[Imagem anexada: {caminho.name} | Caminho: {caminho}]")
            continue

        # 2. PDFs
        if extensao == ".pdf":
            conteudo = _ler_pdf(caminho)
            truncado = len(conteudo) > C.TAMANHO_MAX_PDF
            conteudo = conteudo[:C.TAMANHO_MAX_PDF]
            nota = "\n[... conteúdo truncado ...]" if truncado else ""
            textos_anexos.append(
                f"--- Conteúdo do PDF '{caminho.name}' (Caminho: {caminho}) ---\n"
                f"{conteudo}{nota}\n--- Fim do PDF ---"
            )
            continue

        # 3. Texto / código / logs
        try:
            with open(caminho, "rb") as f:
                amostra = f.read(4096)
        except OSError as exc:
            avisos.append(f"Erro ao ler '{caminho.name}': {exc}")
            continue

        if _parece_binario(amostra):
            avisos.append(
                f"Ignorado '{caminho.name}': conteúdo binário não suportado para análise."
            )
            continue

        try:
            conteudo, truncado = _ler_texto(caminho)
        except OSError as exc:
            avisos.append(f"Erro ao ler '{caminho.name}': {exc}")
            continue

        nota = "\n[... conteúdo truncado ...]" if truncado else ""
        textos_anexos.append(
            f"--- Conteúdo do ficheiro '{caminho.name}' (Caminho: {caminho}) ---\n"
            f"{conteudo}{nota}\n--- Fim do ficheiro ---"
        )

    return imagens, "\n\n".join(textos_anexos), avisos
