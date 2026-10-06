import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Qt, Slot
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..core.models import ConvertJob, ConvertOptions, JobStatus
from ..core.page_range import parse_page_range
from ..core.pdf_info import inspect_pdf
from ..utils.paths import is_writable_dir
from ..utils.settings import AppSettings
from .dialogs import ask_password, show_about
from .file_table import FileTableModel
from .icon import app_icon
from .worker import ConvertWorker

log = logging.getLogger(__name__)

MAX_PASSWORD_ATTEMPTS = 3


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = AppSettings()
        self.model = FileTableModel(self)
        self._thread: QThread | None = None
        self._worker: ConvertWorker | None = None
        self._close_after_finish = False
        self._total = 0
        self._processed = 0
        self._ok = 0

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setAcceptDrops(True)
        self.resize(860, 640)

        self._build_ui()
        self._build_menu()
        self._load_settings()
        self._update_buttons()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget(self)
        root = QVBoxLayout(central)

        # Thanh công cụ file
        bar = QHBoxLayout()
        self.btn_add = QPushButton("+ Thêm file")
        self.btn_remove = QPushButton("Xoá")
        self.btn_clear = QPushButton("Xoá tất cả")
        self.btn_open_file = QPushButton("Mở file")
        self.btn_open_folder = QPushButton("Mở thư mục")
        for b in (self.btn_add, self.btn_remove, self.btn_clear):
            bar.addWidget(b)
        bar.addStretch(1)
        bar.addWidget(self.btn_open_file)
        bar.addWidget(self.btn_open_folder)
        root.addLayout(bar)

        # Bảng file
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        self.drop_hint = QLabel("Kéo thả file hoặc thư mục PDF vào cửa sổ này")
        self.drop_hint.setAlignment(Qt.AlignCenter)
        self.drop_hint.setStyleSheet("color: gray; padding: 4px;")

        table_box = QWidget()
        tl = QVBoxLayout(table_box)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(self.table)
        tl.addWidget(self.drop_hint)

        # Tuỳ chọn
        self.options_box = QGroupBox("Tuỳ chọn")
        grid = QGridLayout(self.options_box)

        self.rb_same_dir = QRadioButton("Cùng thư mục với PDF")
        self.rb_custom_dir = QRadioButton("Thư mục khác:")
        self._dir_group = QButtonGroup(self)
        self._dir_group.addButton(self.rb_same_dir)
        self._dir_group.addButton(self.rb_custom_dir)
        self.ed_output = QLineEdit()
        self.ed_output.setPlaceholderText("Chọn thư mục lưu file DOCX")
        self.btn_browse = QPushButton("...")
        self.btn_browse.setFixedWidth(36)

        out_row = QHBoxLayout()
        out_row.addWidget(self.rb_same_dir)
        out_row.addWidget(self.rb_custom_dir)
        out_row.addWidget(self.ed_output, 1)
        out_row.addWidget(self.btn_browse)
        grid.addWidget(QLabel("Thư mục lưu:"), 0, 0)
        grid.addLayout(out_row, 0, 1)

        self.ed_pages = QLineEdit()
        self.ed_pages.setPlaceholderText("Để trống = tất cả trang. Ví dụ: 1-3, 5, 8-10")
        grid.addWidget(QLabel("Trang:"), 1, 0)
        grid.addWidget(self.ed_pages, 1, 1)

        self.cb_overwrite = QCheckBox("Ghi đè file DOCX đã có")
        self.cb_multi = QCheckBox("Đa tiến trình (nhanh hơn với file lớn)")
        self.cb_multi.setToolTip(
            "Dùng nhiều nhân CPU. Khi bật, thanh tiến trình theo trang sẽ không cập nhật."
        )
        cb_row = QHBoxLayout()
        cb_row.addWidget(self.cb_overwrite)
        cb_row.addWidget(self.cb_multi)
        cb_row.addStretch(1)
        grid.addLayout(cb_row, 2, 1)

        # Tiến trình
        self.pb_files = QProgressBar()
        self.pb_files.setFormat("%v/%m file")
        self.pb_pages = QProgressBar()
        self.pb_pages.setFormat("%p%")
        prog = QGridLayout()
        prog.addWidget(QLabel("File:"), 0, 0)
        prog.addWidget(self.pb_files, 0, 1)
        prog.addWidget(QLabel("File hiện tại:"), 1, 0)
        prog.addWidget(self.pb_pages, 1, 1)

        act_row = QHBoxLayout()
        self.lbl_status = QLabel("")
        act_row.addWidget(self.lbl_status, 1)
        self.btn_cancel = QPushButton("Huỷ")
        self.btn_convert = QPushButton("Chuyển đổi")
        self.btn_convert.setDefault(True)
        self.btn_convert.setMinimumWidth(120)
        self.btn_convert.setStyleSheet("font-weight: bold;")
        act_row.addWidget(self.btn_cancel)
        act_row.addWidget(self.btn_convert)

        # Log
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        log_box = QGroupBox("Log")
        ll = QVBoxLayout(log_box)
        ll.setContentsMargins(4, 4, 4, 4)
        ll.addWidget(self.log_view)

        top = QWidget()
        tv = QVBoxLayout(top)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.addWidget(table_box, 1)
        tv.addWidget(self.options_box)
        tv.addLayout(prog)
        tv.addLayout(act_row)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(top)
        splitter.addWidget(log_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

        self.setCentralWidget(central)

        # Kết nối
        self.btn_add.clicked.connect(self.on_add_files)
        self.btn_remove.clicked.connect(self.on_remove_selected)
        self.btn_clear.clicked.connect(self.on_clear)
        self.btn_open_file.clicked.connect(self.on_open_result)
        self.btn_open_folder.clicked.connect(self.on_open_folder)
        self.btn_browse.clicked.connect(self.on_browse_output)
        self.btn_convert.clicked.connect(self.on_convert)
        self.btn_cancel.clicked.connect(self.on_cancel)
        self.rb_same_dir.toggled.connect(self._update_buttons)
        self.table.doubleClicked.connect(lambda _: self.on_open_result())
        self.table.selectionModel().selectionChanged.connect(self._update_buttons)
        self.model.rowsInserted.connect(self._update_buttons)
        self.model.rowsRemoved.connect(self._update_buttons)
        self.model.modelReset.connect(self._update_buttons)

    def _build_menu(self):
        m_file = self.menuBar().addMenu("&File")
        act_add = QAction("Thêm file...", self)
        act_add.setShortcut(QKeySequence.Open)
        act_add.triggered.connect(self.on_add_files)
        act_quit = QAction("Thoát", self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_add)
        m_file.addSeparator()
        m_file.addAction(act_quit)

        act_del = QAction("Xoá file đã chọn", self)
        act_del.setShortcut(QKeySequence.Delete)
        act_del.triggered.connect(self.on_remove_selected)
        self.table.addAction(act_del)
        self.table.setContextMenuPolicy(Qt.ActionsContextMenu)

        m_help = self.menuBar().addMenu("&Trợ giúp")
        act_about = QAction("Giới thiệu", self)
        act_about.triggered.connect(lambda: show_about(self))
        m_help.addAction(act_about)

    # ------------------------------------------------------------ settings
    def _load_settings(self):
        s = self.settings
        (self.rb_custom_dir if s.use_custom_output else self.rb_same_dir).setChecked(True)
        self.ed_output.setText(s.output_dir)
        self.cb_overwrite.setChecked(s.overwrite)
        self.cb_multi.setChecked(s.multi_processing)
        if s.geometry is not None:
            self.restoreGeometry(s.geometry)

    def _save_settings(self):
        s = self.settings
        s.use_custom_output = self.rb_custom_dir.isChecked()
        s.output_dir = self.ed_output.text().strip()
        s.overwrite = self.cb_overwrite.isChecked()
        s.multi_processing = self.cb_multi.isChecked()
        s.geometry = self.saveGeometry()

    # ------------------------------------------------------------- state
    @property
    def is_running(self) -> bool:
        return self._worker is not None

    @Slot()
    def _update_buttons(self, *args):
        running = self.is_running
        has_jobs = bool(self.model.jobs)
        has_sel = bool(self.table.selectionModel().selectedRows())
        self.btn_add.setEnabled(not running)
        self.btn_remove.setEnabled(not running and has_sel)
        self.btn_clear.setEnabled(not running and has_jobs)
        self.options_box.setEnabled(not running)
        self.btn_convert.setEnabled(not running and has_jobs)
        self.btn_cancel.setEnabled(running)
        self.setAcceptDrops(not running)
        custom = self.rb_custom_dir.isChecked()
        self.ed_output.setEnabled(custom)
        self.btn_browse.setEnabled(custom)
        job = self._current_job()
        self.btn_open_file.setEnabled(bool(job and job.status == JobStatus.DONE))
        self.btn_open_folder.setEnabled(job is not None)
        self.drop_hint.setVisible(not has_jobs)

    def _current_job(self) -> ConvertJob | None:
        idx = self.table.currentIndex()
        if idx.isValid() and idx.row() < len(self.model.jobs):
            return self.model.jobs[idx.row()]
        return None

    def append_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{ts}] {msg}")

    # -------------------------------------------------------- add files
    @Slot()
    def on_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Chọn file PDF", self.settings.last_open_dir, "PDF (*.pdf)"
        )
        if files:
            self.settings.last_open_dir = str(Path(files[0]).parent)
            self.add_paths([Path(f) for f in files])

    def add_paths(self, paths: list[Path]):
        pdfs: list[Path] = []
        for p in paths:
            if p.is_dir():
                pdfs.extend(sorted(x for x in p.rglob("*") if x.suffix.lower() == ".pdf"))
            elif p.suffix.lower() == ".pdf":
                pdfs.append(p)
            else:
                self.append_log(f"Bỏ qua (không phải PDF): {p.name}")

        for pdf in pdfs:
            if self.model.contains(pdf):
                self.append_log(f"Đã có trong danh sách: {pdf.name}")
                continue
            job = self._inspect(pdf)
            if job:
                self.model.add_job(job)
                msg = f"Đã thêm: {pdf.name} ({job.page_count} trang)"
                if job.is_scanned:
                    msg += " — cảnh báo: PDF dạng ảnh, kết quả sẽ không chỉnh sửa được chữ"
                self.append_log(msg)

    def _inspect(self, pdf: Path) -> ConvertJob | None:
        try:
            info = inspect_pdf(pdf)
            password = None
            attempt = 1
            while info.needs_password:
                if attempt > MAX_PASSWORD_ATTEMPTS:
                    self.append_log(f"Bỏ qua (sai mật khẩu quá {MAX_PASSWORD_ATTEMPTS} lần): {pdf.name}")
                    return None
                password = ask_password(self, pdf.name, attempt)
                if password is None:
                    self.append_log(f"Bỏ qua (không nhập mật khẩu): {pdf.name}")
                    return None
                info = inspect_pdf(pdf, password)
                attempt += 1
        except Exception as e:
            log.exception("Cannot open %s", pdf)
            self.append_log(f"Lỗi mở file {pdf.name}: {e}")
            return None
        return ConvertJob(
            pdf_path=pdf,
            page_count=info.page_count,
            password=password,
            is_scanned=info.is_scanned,
        )

    # ---------------------------------------------------- drag & drop
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.is_running:
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.add_paths(paths)

    # -------------------------------------------------- list actions
    @Slot()
    def on_remove_selected(self):
        if self.is_running:
            return
        rows = [i.row() for i in self.table.selectionModel().selectedRows()]
        self.model.remove_rows(rows)

    @Slot()
    def on_clear(self):
        self.model.clear()

    @Slot()
    def on_open_result(self):
        job = self._current_job()
        if job and job.status == JobStatus.DONE and job.output_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(job.output_path)))

    @Slot()
    def on_open_folder(self):
        job = self._current_job()
        if not job:
            return
        folder = job.output_path.parent if job.output_path else job.pdf_path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    @Slot()
    def on_browse_output(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu", self.ed_output.text())
        if d:
            self.ed_output.setText(d)

    # ------------------------------------------------------- convert
    def _build_options(self) -> ConvertOptions | None:
        output_dir = None
        if self.rb_custom_dir.isChecked():
            text = self.ed_output.text().strip()
            if not text:
                QMessageBox.warning(self, APP_NAME, "Vui lòng chọn thư mục lưu.")
                return None
            output_dir = Path(text)
            if not output_dir.exists():
                try:
                    output_dir.mkdir(parents=True)
                except OSError as e:
                    QMessageBox.warning(self, APP_NAME, f"Không tạo được thư mục:\n{e}")
                    return None
            if not is_writable_dir(output_dir):
                QMessageBox.warning(self, APP_NAME, "Không có quyền ghi vào thư mục đã chọn.")
                return None
        return ConvertOptions(
            output_dir=output_dir,
            page_spec=self.ed_pages.text().strip(),
            overwrite=self.cb_overwrite.isChecked(),
            multi_processing=self.cb_multi.isChecked(),
        )

    @Slot()
    def on_convert(self):
        if self.is_running or not self.model.jobs:
            return
        options = self._build_options()
        if options is None:
            return
        self._save_settings()
        self.model.reset_statuses()

        # Validate khoảng trang cho từng file (số trang mỗi file khác nhau)
        items: list[tuple[int, ConvertJob]] = []
        for i, job in enumerate(self.model.jobs):
            try:
                parse_page_range(options.page_spec, job.page_count)
            except ValueError as e:
                job.status, job.error = JobStatus.FAILED, str(e)
                self.model.refresh_row(i)
                self.append_log(f"{job.pdf_path.name}: {e}")
                continue
            items.append((i, job))

        self._total = len(self.model.jobs)
        self._processed = self._total - len(items)
        self._ok = 0
        self.pb_files.setRange(0, self._total)
        self.pb_files.setValue(self._processed)
        self.pb_pages.setRange(0, 1)
        self.pb_pages.setValue(0)

        if not items:
            self._show_summary(cancelled=False)
            return

        self._thread = QThread(self)
        self._worker = ConvertWorker(items, options)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log.connect(self.append_log)
        self._worker.page_progress.connect(self.on_page_progress)
        self._worker.file_started.connect(self.on_file_started)
        self._worker.file_finished.connect(self.on_file_finished)
        self._worker.finished.connect(self.on_all_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self.lbl_status.setText("Đang chuyển đổi...")
        self._update_buttons()
        self._thread.start()

    @Slot()
    def on_cancel(self):
        if self._worker:
            self._worker.cancel()
            self.btn_cancel.setEnabled(False)
            self.lbl_status.setText("Đang huỷ... (chờ file hiện tại xong)")
            self.append_log("Yêu cầu huỷ: sẽ dừng sau file hiện tại.")

    @Slot(int, int)
    def on_page_progress(self, current: int, total: int):
        self.pb_pages.setRange(0, total)
        self.pb_pages.setValue(current)

    @Slot(int)
    def on_file_started(self, index: int):
        job = self.model.jobs[index]
        job.status = JobStatus.RUNNING
        self.model.refresh_row(index)
        self.table.selectRow(index)
        self.pb_pages.setRange(0, 0 if self.cb_multi.isChecked() else 1)
        self.pb_pages.setValue(0)

    @Slot(int, bool, str)
    def on_file_finished(self, index: int, ok: bool, result: str):
        job = self.model.jobs[index]
        if ok:
            job.status = JobStatus.DONE
            job.output_path = Path(result)
            self._ok += 1
            self.append_log(f"Xong: {job.pdf_path.name} → {result}")
        else:
            job.status = JobStatus.FAILED
            job.error = result
            self.append_log(f"Lỗi: {job.pdf_path.name}: {result}")
        self.model.refresh_row(index)
        self._processed += 1
        self.pb_files.setValue(self._processed)
        if self.pb_pages.maximum() == 0:
            self.pb_pages.setRange(0, 1)
        self.pb_pages.setValue(self.pb_pages.maximum())
        self._update_buttons()

    @Slot(bool)
    def on_all_finished(self, cancelled: bool):
        for i, job in enumerate(self.model.jobs):
            if job.status in (JobStatus.PENDING, JobStatus.RUNNING) and cancelled:
                job.status = JobStatus.CANCELLED
                self.model.refresh_row(i)
        self._worker = None
        self._thread = None
        self._update_buttons()
        if self._close_after_finish:
            self.close()
            return
        self._show_summary(cancelled)

    def _show_summary(self, cancelled: bool):
        failed = sum(1 for j in self.model.jobs if j.status == JobStatus.FAILED)
        msg = f"Hoàn tất {self._ok}/{self._total} file"
        if failed:
            msg += f", {failed} lỗi"
        if cancelled:
            msg += " (đã huỷ)"
        self.lbl_status.setText(msg)
        self.append_log(msg)
        if failed:
            QMessageBox.warning(self, APP_NAME, msg + ".\nXem chi tiết trong cột Kết quả / Log.")
        else:
            QMessageBox.information(self, APP_NAME, msg + ".")

    # ---------------------------------------------------------- close
    def closeEvent(self, event):
        if self.is_running:
            reply = QMessageBox.question(
                self,
                APP_NAME,
                "Đang chuyển đổi. Huỷ và thoát sau khi file hiện tại hoàn tất?",
            )
            if reply == QMessageBox.Yes:
                self._close_after_finish = True
                self.on_cancel()
            event.ignore()
            return
        self._save_settings()
        event.accept()
