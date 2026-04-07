from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from shell.bootstrap import bootstrap_application


def main() -> int:
    app = QApplication(sys.argv)
    context = bootstrap_application(app)
    context.window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
