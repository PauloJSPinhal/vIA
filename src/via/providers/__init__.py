"""Conectores de modelos (Ollama local e APIs externas)."""

from via.providers import gemini, ollama, openai_compat
from via.providers.base import ErroProvider

__all__ = ["ErroProvider", "gemini", "ollama", "openai_compat"]
