"""Diagnóstico de hardware e deteção de chaves de API."""

import os
import re
import shutil
import subprocess

from via import constants as C


def obter_info_hardware() -> str:
    ram_total_gb = 0.0
    ram_disp_gb = 0.0
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for linha in f:
                if linha.startswith("MemTotal:"):
                    ram_total_gb = round(int(linha.split()[1]) / (1024 * 1024), 1)
                elif linha.startswith("MemAvailable:"):
                    ram_disp_gb = round(int(linha.split()[1]) / (1024 * 1024), 1)
    except (OSError, ValueError):
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
    except (OSError, IndexError):
        pass

    gpu_info = "Sem GPU dedicada (apenas CPU)"
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                text=True, timeout=3,
            ).strip()
            if out:
                partes = [p.strip() for p in out.split(",")]
                nome_gpu = partes[0] if partes[0].startswith("NVIDIA") else f"NVIDIA {partes[0]}"
                vram = partes[1] if len(partes) > 1 else ""
                gpu_info = f"{nome_gpu} ({vram})" if vram else nome_gpu
        except (OSError, subprocess.SubprocessError):
            pass

    return (
        f"CPU: {cpu_modelo} ({cpu_cores} threads) | "
        f"RAM: {ram_disp_gb} GB livres / {ram_total_gb} GB total | "
        f"GPU: {gpu_info}"
    )


def detetar_chaves_ambiente() -> dict:
    estado = {}
    for chave in C.PROVEDORES_EXTERNOS.values():
        valor = os.environ.get(chave, "").strip()
        estado[chave] = valor or None
    return estado


def chave_em_falta(modelo: str, chaves: dict) -> str | None:
    """Devolve o nome da variável de ambiente em falta, se aplicável."""
    if not modelo:
        return None
    provedor = modelo.split(":", 1)[0] if ":" in modelo else "ollama"
    variavel = C.PROVEDORES_EXTERNOS.get(provedor)
    if variavel and not chaves.get(variavel):
        return variavel
    return None
