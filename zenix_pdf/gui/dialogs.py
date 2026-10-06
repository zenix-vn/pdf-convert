from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QWidget

from .. import APP_NAME, __version__


def ask_password(parent: QWidget, filename: str, attempt: int) -> str | None:
    """Hiện hộp thoại nhập mật khẩu. Trả về None nếu người dùng huỷ."""
    label = f"File '{filename}' được bảo vệ bằng mật khẩu.\nNhập mật khẩu:"
    if attempt > 1:
        label = f"Sai mật khẩu (lần {attempt - 1}).\n" + label
    text, ok = QInputDialog.getText(
        parent, "Nhập mật khẩu PDF", label, QLineEdit.EchoMode.Password
    )
    return text if ok else None


def show_about(parent: QWidget):
    QMessageBox.about(
        parent,
        f"Giới thiệu {APP_NAME}",
        f"<h3>{APP_NAME} {__version__}</h3>"
        "<p>Chuyển đổi PDF sang Word (DOCX).</p>"
        "<p>Sử dụng: pdf2docx, PyMuPDF, PySide6.</p>",
    )
