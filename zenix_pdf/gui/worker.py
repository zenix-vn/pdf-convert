"""Luồng nền chạy pdf2docx, giao tiếp với GUI qua Signal."""

import logging
import re

from PySide6.QtCore import QObject, Signal, Slot

from ..core.converter import PdfConverterService
from ..core.models import ConvertJob, ConvertOptions

log = logging.getLogger(__name__)

# pdf2docx ghi log mỗi trang dạng "(3/12) Page 3", lặp 2 lượt:
# "[3/4] Parsing pages..." rồi "[4/4] Creating pages..."
_PAGE_RE = re.compile(r"^\((\d+)/(\d+)\)")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class QtLogHandler(logging.Handler):
    """Chuyển log của pdf2docx thành Signal Qt (chỉ log phát sinh từ luồng worker).

    Tiến trình trang được quy về thang 0..2n: lượt phân tích chiếm nửa đầu,
    lượt tạo trang DOCX chiếm nửa sau.
    """

    def __init__(self, worker: "ConvertWorker", thread_id: int):
        super().__init__(logging.INFO)
        self.worker = worker
        self.thread_id = thread_id
        self._creating = False

    def emit(self, record: logging.LogRecord):
        if record.thread != self.thread_id:
            return
        try:
            msg = _ANSI_RE.sub("", record.getMessage())
        except Exception:
            return
        if "[3/4]" in msg or msg.startswith("Start to convert"):
            self._creating = False
        elif "[4/4]" in msg:
            self._creating = True

        if m := _PAGE_RE.match(msg):
            i, n = int(m.group(1)), int(m.group(2))
            self.worker.page_progress.emit(i + (n if self._creating else 0), 2 * n)
            return  # không đẩy từng dòng trang vào log GUI cho đỡ rối
        if record.levelno >= logging.WARNING:
            msg = f"{record.levelname}: {msg}"
        self.worker.log.emit(msg)


class ConvertWorker(QObject):
    log = Signal(str)
    page_progress = Signal(int, int)  # (trang hiện tại, tổng)
    file_started = Signal(int)  # index trong danh sách job
    file_finished = Signal(int, bool, str)  # index, thành công?, đường dẫn output / lỗi
    finished = Signal(bool)  # cancelled?

    def __init__(self, items: list[tuple[int, ConvertJob]], options: ConvertOptions):
        super().__init__()
        self.items = items
        self.options = options
        self._cancel = False
        self.service = PdfConverterService()

    def cancel(self):
        self._cancel = True

    @Slot()
    def run(self):
        import threading

        handler = QtLogHandler(self, threading.get_ident())
        root = logging.getLogger()
        root.addHandler(handler)
        if root.level > logging.INFO or root.level == logging.NOTSET:
            root.setLevel(logging.INFO)
        try:
            for index, job in self.items:
                if self._cancel:
                    break
                self.file_started.emit(index)
                self.log.emit(f"Bắt đầu: {job.pdf_path.name}")
                try:
                    out = self.service.convert(job, self.options)
                    self.file_finished.emit(index, True, str(out))
                except Exception as e:
                    log.exception("Convert failed: %s", job.pdf_path)
                    self.file_finished.emit(index, False, str(e) or type(e).__name__)
        finally:
            root.removeHandler(handler)
            self.finished.emit(self._cancel)
