"""Arranque da aplicação vIA."""

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from via import constants as C
from via.config import migrar_config_legada
from via.ui.main_window import ViaWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(C.APP_ID)
    app.setApplicationDisplayName(C.APP_NOME)
    app.setApplicationVersion(C.APP_VERSAO)
    app.setOrganizationName(C.APP_NOME)
    app.setDesktopFileName("vIA")

    raiz_projeto = Path(__file__).resolve().parents[2]
    icone = raiz_projeto / "assets" / "icons" / "via.svg"
    if icone.is_file():
        app.setWindowIcon(QIcon(str(icone)))

    migrados = migrar_config_legada()
    janela = ViaWindow(migrados_config=migrados)
    janela.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
