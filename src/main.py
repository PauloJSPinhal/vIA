#!/usr/bin/env python3
"""Ponto de entrada do vIA.

Executa a aplicação a partir da pasta ``src`` (permite ``import via``).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from via.app import main  # noqa: E402  (import após ajuste do sys.path)

if __name__ == "__main__":
    sys.exit(main())
