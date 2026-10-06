import multiprocessing
import sys


def main():
    # Bắt buộc cho bản .exe khi bật multi_processing của pdf2docx trên Windows
    multiprocessing.freeze_support()

    from zenix_pdf.utils.logging_setup import setup_file_logging

    # Cấu hình logging trước khi import pdf2docx để basicConfig của nó không in ra console
    setup_file_logging()

    if len(sys.argv) > 1 and sys.argv[1] == "--convert":
        from zenix_pdf.cli import run

        sys.exit(run(sys.argv[2:]))

    from PySide6.QtWidgets import QApplication

    from zenix_pdf import APP_NAME, ORG_NAME

    from zenix_pdf.gui.icon import app_icon
    from zenix_pdf.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
