"""Icon ứng dụng vẽ bằng QPainter (không cần file ảnh kèm theo)."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap


def make_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 64.0

    # Trang giấy bên trái (PDF - đỏ)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#d32f2f"))
    p.drawRoundedRect(QRectF(4 * s, 6 * s, 34 * s, 44 * s), 4 * s, 4 * s)
    # Trang giấy bên phải (DOCX - xanh)
    p.setBrush(QColor("#1565c0"))
    p.drawRoundedRect(QRectF(26 * s, 14 * s, 34 * s, 44 * s), 4 * s, 4 * s)

    # Mũi tên
    arrow = QPainterPath()
    arrow.moveTo(30 * s, 36 * s)
    arrow.lineTo(44 * s, 36 * s)
    arrow.lineTo(44 * s, 30 * s)
    arrow.lineTo(54 * s, 40 * s)
    arrow.lineTo(44 * s, 50 * s)
    arrow.lineTo(44 * s, 44 * s)
    arrow.lineTo(30 * s, 44 * s)
    arrow.closeSubpath()
    p.setBrush(QColor("white"))
    p.drawPath(arrow)

    # Chữ "Z"
    font = QFont("Segoe UI", max(1, int(14 * s)))
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("white"))
    p.drawText(QRectF(4 * s, 6 * s, 22 * s, 22 * s), Qt.AlignCenter, "Z")
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(make_pixmap(size))
    return icon
