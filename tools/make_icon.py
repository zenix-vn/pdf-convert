"""Sinh file icon.ico (dùng cho PyInstaller) từ icon vẽ bằng QPainter."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QGuiApplication  # noqa: E402

from zenix_pdf.gui.icon import make_pixmap  # noqa: E402


def main():
    app = QGuiApplication(sys.argv)  # noqa: F841 — cần cho QPixmap/QFont
    out = ROOT / "zenix_pdf" / "gui" / "resources" / "icon.ico"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not make_pixmap(256).save(str(out), "ICO"):
        raise SystemExit(f"Không ghi được {out}")
    print(f"Đã tạo {out}")


if __name__ == "__main__":
    main()
