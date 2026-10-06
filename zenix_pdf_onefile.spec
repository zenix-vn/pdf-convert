# -*- mode: python ; coding: utf-8 -*-
# Bản 1 file duy nhất (khởi động chậm hơn do giải nén mỗi lần chạy)
# Build: pyinstaller --noconfirm zenix_pdf_onefile.spec
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("pdf2docx")

# Loại các module Qt không dùng để giảm dung lượng
excludes = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore",
    "PySide6.Qt3DRender", "PySide6.QtMultimedia", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtBluetooth",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtNetwork", "tkinter", "pytest",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)

# Bỏ DLL Qt kéo theo qua plugin nhưng app (Qt Widgets) không cần.
# Lưu ý: cv2 (OpenCV, ~110 MB) là phụ thuộc bắt buộc của pdf2docx, không bỏ được.
_DROP = (
    "opengl32sw.dll", "Qt6Quick", "Qt6Qml", "Qt6Pdf", "Qt6VirtualKeyboard",
    "Qt6OpenGL.dll", "Qt6Network.dll",
)
a.binaries = [b for b in a.binaries if not any(k in b[0] for k in _DROP)]
a.datas = [
    d for d in a.datas
    if not (d[0].startswith("PySide6\\translations") or d[0].startswith("PySide6/translations"))
    or "qtbase_vi" in d[0]
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ZenixPdfConvert-portable",
    console=False,
    upx=False,
    icon="zenix_pdf/gui/resources/icon.ico",
)
