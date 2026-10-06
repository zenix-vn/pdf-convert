# Zenix PDF Convert — Tài liệu thiết kế & kỹ thuật

> Ứng dụng desktop chuyển đổi PDF sang Word (DOCX), viết bằng **Python**, dùng thư viện **pdf2docx** (nền tảng **PyMuPDF**) và giao diện **PySide6** (Qt 6).

---

## 1. Tổng quan

### 1.1. Mục tiêu

- Chuyển file PDF sang DOCX, giữ bố cục càng sát bản gốc càng tốt: đoạn văn, font, màu chữ, bảng, hình ảnh, header/footer, nhiều cột.
- Giao diện đồ hoạ đơn giản, dùng được ngay không cần dòng lệnh.
- Hỗ trợ chuyển **nhiều file cùng lúc** (batch), chọn **khoảng trang**, mở file PDF có **mật khẩu**.
- Giao diện không bị "đơ" khi đang convert (xử lý ở luồng nền), có thanh tiến trình và log.
- Đóng gói thành file `.exe` chạy độc lập trên Windows.

### 1.2. Phạm vi (ngoài phạm vi)

- **Không** OCR: PDF dạng ảnh scan sẽ chỉ ra DOCX chứa ảnh, không có chữ chỉnh sửa được (xem mục 10).
- **Không** chuyển ngược DOCX → PDF.
- **Không** chỉnh sửa nội dung PDF.

### 1.3. Đối tượng sử dụng

Người dùng văn phòng cần chỉnh sửa lại tài liệu PDF trong Microsoft Word / LibreOffice.

---

## 2. Công nghệ sử dụng

| Thành phần | Thư viện | Phiên bản đề xuất | Vai trò |
|---|---|---|---|
| Ngôn ngữ | Python | 3.10 – 3.12 | Runtime |
| Engine chuyển đổi | `pdf2docx` | ≥ 0.5.8 | Phân tích layout PDF và sinh DOCX |
| Đọc PDF | `PyMuPDF` (`fitz`/`pymupdf`) | ≥ 1.23 | Được pdf2docx dùng để đọc text, ảnh, vector; app dùng thêm để đọc số trang, kiểm tra mật khẩu, render thumbnail |
| Ghi DOCX | `python-docx` | (cài kèm pdf2docx) | Sinh file Word |
| Giao diện | `PySide6` | ≥ 6.6 | Cửa sổ, widget, luồng nền (`QThread`) |
| Đóng gói | `PyInstaller` | ≥ 6.0 | Tạo file thực thi `.exe` |

### 2.1. Cách pdf2docx hoạt động (tóm tắt)

1. **Đọc** trang PDF bằng PyMuPDF → lấy ra các khối text (span, font, size, màu), ảnh, đường vector.
2. **Phân tích layout**: gom span thành dòng, dòng thành đoạn; nhận diện bảng (từ đường kẻ khung hoặc từ căn lề), nhận diện cột, header/footer.
3. **Sinh DOCX** bằng python-docx: đoạn văn, bảng, ảnh, section, khoảng cách lề.

API cơ bản:

```python
from pdf2docx import Converter

cv = Converter("input.pdf")            # có thể truyền password="..."
cv.convert("output.docx", start=0, end=None)   # start/end: chỉ số trang, bắt đầu từ 0
cv.close()
```

Các tham số hay dùng của `convert()`:

| Tham số | Ý nghĩa |
|---|---|
| `start`, `end` | Khoảng trang (0-based, `end` không bao gồm) |
| `pages` | Danh sách trang cụ thể, ví dụ `[0, 2, 5]` |
| `multi_processing` | `True` để dùng nhiều tiến trình (nhanh hơn với file lớn). **Chỉ dùng được với `start`/`end`**, không dùng được cùng `pages` — app tự chuyển khoảng trang liên tục sang `start`/`end`, và tắt đa tiến trình nếu khoảng trang không liên tục |
| `cpu_count` | Số tiến trình khi bật `multi_processing` |

---

## 3. Chức năng

| # | Chức năng | Mô tả |
|---|---|---|
| F1 | Thêm file | Nút "Thêm file", hoặc **kéo – thả** file `.pdf` vào cửa sổ |
| F2 | Danh sách file | Bảng hiển thị: tên file, số trang, trạng thái (Chờ / Đang xử lý / Xong / Lỗi), nút xoá |
| F3 | Thư mục đầu ra | Mặc định: cùng thư mục với file PDF; có thể chọn thư mục khác |
| F4 | Khoảng trang | Tất cả trang, hoặc nhập dạng `1-3, 5, 8-10` (1-based cho người dùng) |
| F5 | Mật khẩu | Phát hiện PDF bị mã hoá → hiện hộp thoại nhập mật khẩu |
| F6 | Chuyển đổi | Chạy nền, có thanh tiến trình theo **file** và theo **trang** |
| F7 | Huỷ | Dừng sau file hiện tại (xem mục 6.3) |
| F8 | Log | Khung log hiển thị tiến trình, cảnh báo, lỗi |
| F9 | Mở kết quả | Sau khi xong: nút "Mở file" / "Mở thư mục" |
| F10 | Ghi đè | Tuỳ chọn: ghi đè / tự đổi tên (`file (1).docx`) nếu file đích đã tồn tại |
| F11 | Ghi nhớ cài đặt | Lưu thư mục đầu ra, tuỳ chọn lần trước bằng `QSettings` |

---

## 4. Kiến trúc

### 4.1. Sơ đồ tổng thể

```
┌────────────────────────────── Main thread (Qt GUI) ──────────────────────────────┐
│                                                                                  │
│   MainWindow ──► FileTableModel (danh sách job)                                  │
│       │                                                                          │
│       │  start(jobs, options)                     signals: progress, log,        │
│       ▼                                                    file_done, finished   │
│   ConvertController ◄───────────────────────────────────────────────┐            │
└───────┼──────────────────────────────────────────────────────────────┼───────────┘
        │ moveToThread / QThread                                       │
┌───────▼──────────────────────── Worker thread ───────────────────────┴───────────┐
│   ConvertWorker                                                                  │
│     for job in jobs:                                                             │
│        PdfConverterService.convert(job)  ──► pdf2docx.Converter ──► PyMuPDF      │
│        QtLogHandler bắt log của pdf2docx  ──► emit progress(page/total)          │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2. Nguyên tắc

- **Tách lớp**: phần lõi chuyển đổi (`core/`) không import Qt → có thể dùng lại cho CLI hoặc test độc lập.
- **GUI không bao giờ gọi pdf2docx trực tiếp** trên main thread; mọi tác vụ nặng chạy trong `QThread`.
- Giao tiếp giữa worker và GUI **chỉ qua Signal/Slot** (thread-safe trong Qt).

---

## 5. Cấu trúc thư mục

```
zenix-pdf-convert/
├── doc.md
├── README.md
├── requirements.txt
├── requirements-dev.txt        # + pytest, pyinstaller
├── main.py                     # entry point (GUI, hoặc --convert cho dòng lệnh)
├── zenix_pdf.spec              # cấu hình PyInstaller
├── zenix_pdf/
│   ├── __init__.py             # APP_NAME, __version__
│   ├── cli.py                  # chế độ dòng lệnh dùng chung core/
│   ├── core/                   # không phụ thuộc Qt
│   │   ├── models.py           # ConvertJob, ConvertOptions, JobStatus
│   │   ├── page_range.py       # parse "1-3, 5" -> [0,1,2,4]
│   │   ├── pdf_info.py         # số trang, mật khẩu, phát hiện PDF scan (PyMuPDF)
│   │   └── converter.py        # PdfConverterService bọc pdf2docx
│   ├── gui/
│   │   ├── main_window.py      # MainWindow
│   │   ├── file_table.py       # FileTableModel (QAbstractTableModel)
│   │   ├── worker.py           # ConvertWorker + QtLogHandler
│   │   ├── dialogs.py          # hộp thoại mật khẩu, Giới thiệu
│   │   ├── icon.py             # icon vẽ bằng QPainter
│   │   └── resources/icon.ico  # sinh bởi tools/make_icon.py
│   └── utils/
│       ├── paths.py            # tên file đích, tránh trùng, thư mục AppData
│       ├── logging_setup.py    # RotatingFileHandler
│       └── settings.py         # wrapper QSettings
├── tools/
│   └── make_icon.py
└── tests/                      # PDF mẫu được sinh tự động bằng PyMuPDF (conftest.py)
    ├── test_page_range.py
    ├── test_paths.py
    └── test_converter.py
```

---

## 6. Thiết kế chi tiết

### 6.1. Model dữ liệu — `core/models.py`

```python
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class JobStatus(Enum):
    PENDING = "Chờ"
    RUNNING = "Đang xử lý"
    DONE = "Xong"
    FAILED = "Lỗi"
    CANCELLED = "Đã huỷ"


@dataclass
class ConvertOptions:
    output_dir: Path | None = None     # None = cùng thư mục với PDF
    page_spec: str = ""                # "" = tất cả trang, ví dụ "1-3, 5"
    overwrite: bool = False
    multi_processing: bool = False


@dataclass
class ConvertJob:
    pdf_path: Path
    page_count: int = 0
    password: str | None = None
    output_path: Path | None = None
    status: JobStatus = JobStatus.PENDING
    error: str = ""
```

### 6.2. Lõi chuyển đổi — `core/converter.py`

```python
from pathlib import Path
from pdf2docx import Converter

from .models import ConvertJob, ConvertOptions
from .page_range import parse_page_range
from ..utils.paths import resolve_output_path


class PdfConverterService:
    def convert(self, job: ConvertJob, options: ConvertOptions) -> Path:
        out = resolve_output_path(job.pdf_path, options.output_dir, options.overwrite)
        pages = parse_page_range(options.page_spec, job.page_count)  # None = tất cả

        cv = Converter(str(job.pdf_path), password=job.password)
        try:
            cv.convert(
                str(out),
                pages=pages,
                multi_processing=options.multi_processing,
            )
        finally:
            cv.close()

        job.output_path = out
        return out
```

`core/pdf_info.py` dùng PyMuPDF để lấy thông tin trước khi convert:

```python
import pymupdf  # hoặc: import fitz


def inspect_pdf(path, password=None) -> tuple[int, bool]:
    """Trả về (số trang, cần mật khẩu?)."""
    with pymupdf.open(path) as doc:
        if doc.needs_pass:
            if not password or not doc.authenticate(password):
                return 0, True
        return doc.page_count, False
```

`core/page_range.py` — quy tắc:

- Đầu vào người dùng **1-based**: `"1-3, 5, 8-10"`.
- Đầu ra **0-based**, đã sắp xếp, loại trùng: `[0, 1, 2, 4, 7, 8, 9]`.
- Chuỗi rỗng → `None` (convert toàn bộ).
- Trang vượt quá `page_count` hoặc cú pháp sai → `ValueError` với thông báo rõ ràng để GUI hiển thị.

### 6.3. Luồng nền — `gui/worker.py`

pdf2docx không có callback tiến trình, nhưng có ghi log theo từng trang dạng `(i/n) Page x`, **hai lượt**: sau `[3/4] Parsing pages...` và sau `[4/4] Creating pages...` (tiêu đề bước có mã màu ANSI cần lọc bỏ). Ứng dụng gắn một `logging.Handler` riêng (chỉ nhận log từ luồng worker) để chuyển log thành Signal Qt; tiến trình trang được quy về thang `0..2n` (lượt phân tích là nửa đầu, lượt tạo DOCX là nửa sau).

> Đoạn code dưới đây là bản rút gọn; xem bản đầy đủ tại `zenix_pdf/gui/worker.py`.

```python
import logging
import re
from PySide6.QtCore import QObject, Signal, Slot

from zenix_pdf.core.converter import PdfConverterService
from zenix_pdf.core.models import JobStatus

_PAGE_RE = re.compile(r"\((\d+)/(\d+)\)")


class QtLogHandler(logging.Handler):
    def __init__(self, worker: "ConvertWorker"):
        super().__init__(logging.INFO)
        self.worker = worker

    def emit(self, record):
        msg = record.getMessage()
        self.worker.log.emit(msg)
        if m := _PAGE_RE.search(msg):
            self.worker.page_progress.emit(int(m.group(1)), int(m.group(2)))


class ConvertWorker(QObject):
    log = Signal(str)
    page_progress = Signal(int, int)        # (trang hiện tại, tổng)
    file_started = Signal(int)              # index trong danh sách
    file_finished = Signal(int, bool, str)  # index, thành công?, output/lỗi
    finished = Signal()

    def __init__(self, jobs, options):
        super().__init__()
        self.jobs, self.options = jobs, options
        self._cancel = False
        self.service = PdfConverterService()

    def cancel(self):
        self._cancel = True

    @Slot()
    def run(self):
        handler = QtLogHandler(self)
        root = logging.getLogger()
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        try:
            for i, job in enumerate(self.jobs):
                if self._cancel:
                    job.status = JobStatus.CANCELLED
                    continue
                self.file_started.emit(i)
                try:
                    out = self.service.convert(job, self.options)
                    job.status = JobStatus.DONE
                    self.file_finished.emit(i, True, str(out))
                except Exception as e:
                    job.status, job.error = JobStatus.FAILED, str(e)
                    self.file_finished.emit(i, False, str(e))
        finally:
            root.removeHandler(handler)
            self.finished.emit()
```

**Về chức năng Huỷ**: `pdf2docx.Converter.convert()` là một lời gọi chặn, không có cơ chế dừng giữa chừng. Phiên bản đầu (v1) huỷ **giữa các file**. Nếu cần huỷ ngay lập tức, phương án v2 là chạy mỗi job trong một tiến trình con (`multiprocessing.Process` hoặc `QProcess` gọi CLI nội bộ) và `terminate()` khi người dùng bấm Huỷ, sau đó xoá file DOCX dở dang.

Khởi chạy từ GUI:

```python
from PySide6.QtCore import QThread

self.thread = QThread(self)
self.worker = ConvertWorker(jobs, options)
self.worker.moveToThread(self.thread)
self.thread.started.connect(self.worker.run)
self.worker.finished.connect(self.thread.quit)
self.worker.finished.connect(self.worker.deleteLater)
self.thread.finished.connect(self.thread.deleteLater)

self.worker.log.connect(self.append_log)
self.worker.page_progress.connect(self.on_page_progress)
self.worker.file_started.connect(self.on_file_started)
self.worker.file_finished.connect(self.on_file_finished)
self.thread.start()
```

### 6.4. Giao diện — `gui/main_window.py`

**Bố cục cửa sổ chính:**

```
┌─ Zenix PDF Convert ──────────────────────────────────────────────┐
│  [+ Thêm file]  [Xoá]  [Xoá tất cả]                              │
│ ┌──────────────────────────────────────────────────────────────┐ │
│ │ Tên file             │ Số trang │ Trạng thái │ Kết quả       │ │
│ │ baocao_2025.pdf      │    12    │ Xong       │ Mở            │ │
│ │ hopdong.pdf          │     4    │ Đang xử lý │               │ │
│ │ ...  (kéo thả file PDF vào đây)                              │ │
│ └──────────────────────────────────────────────────────────────┘ │
│  Thư mục lưu: (•) Cùng thư mục PDF  ( ) [D:\Output     ] [...]   │
│  Trang:       [ 1-3, 5            ]  (để trống = tất cả)         │
│  [x] Ghi đè file đã có    [ ] Đa tiến trình (file lớn)           │
│                                                                  │
│  File:  [██████████░░░░░░░░░░]  2/5                              │
│  Trang: [██████████████░░░░░░]  9/12                             │
│                                       [ Huỷ ]  [ Chuyển đổi ]    │
│ ┌─ Log ────────────────────────────────────────────────────────┐ │
│ │ [17:40:02] (9/12) Page 9                                     │ │
│ └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

**Widget sử dụng:**

| Vùng | Widget |
|---|---|
| Danh sách file | `QTableView` + `FileTableModel(QAbstractTableModel)` |
| Chọn file | `QFileDialog.getOpenFileNames(filter="PDF (*.pdf)")` |
| Kéo – thả | override `dragEnterEvent` / `dropEvent`, lọc đuôi `.pdf` |
| Thư mục lưu | `QRadioButton` ×2 + `QLineEdit` + `QFileDialog.getExistingDirectory` |
| Khoảng trang | `QLineEdit` + validate khi bấm Chuyển đổi |
| Tiến trình | `QProgressBar` ×2 |
| Log | `QPlainTextEdit` (read-only, `setMaximumBlockCount(2000)`) |
| Mật khẩu | `QInputDialog.getText(..., QLineEdit.Password)` |
| Mở kết quả | `QDesktopServices.openUrl(QUrl.fromLocalFile(path))` |

**Trạng thái nút:**

| Trạng thái app | Thêm/Xoá file | Tuỳ chọn | Chuyển đổi | Huỷ |
|---|---|---|---|---|
| Rảnh, danh sách rỗng | ✔ | ✔ | ✖ | ✖ |
| Rảnh, có file | ✔ | ✔ | ✔ | ✖ |
| Đang chạy | ✖ | ✖ | ✖ | ✔ |

**Xử lý đóng cửa sổ khi đang chạy** (`closeEvent`): hỏi xác nhận → gọi `worker.cancel()` → chờ `thread.wait()` rồi mới thoát, tránh lỗi "QThread destroyed while running".

### 6.5. Luồng xử lý khi thêm file

```
Người dùng chọn/kéo file
   └─► lọc .pdf, bỏ file trùng trong danh sách
        └─► inspect_pdf(path)
              ├─ cần mật khẩu → hiện PasswordDialog
              │     ├─ đúng  → lưu job.password, lấy số trang
              │     └─ huỷ/sai 3 lần → bỏ qua file, ghi log
              ├─ lỗi mở file (hỏng) → ghi log, bỏ qua
              └─ OK → thêm ConvertJob vào FileTableModel
```

### 6.6. Luồng xử lý khi bấm "Chuyển đổi"

1. Validate khoảng trang với **từng** file (số trang mỗi file khác nhau). File nào không hợp lệ → đánh dấu Lỗi, không chặn các file khác.
2. Kiểm tra thư mục đầu ra tồn tại và có quyền ghi.
3. Khoá giao diện, reset thanh tiến trình.
4. Tạo `QThread` + `ConvertWorker`, bắt đầu chạy.
5. Mỗi `file_finished` → cập nhật dòng trong bảng, tăng thanh tiến trình file.
6. `finished` → mở khoá giao diện, hiện thông báo tổng kết: *"Hoàn tất 4/5 file, 1 lỗi"*.

### 6.7. Đặt tên file đầu ra — `utils/paths.py`

- `D:\docs\baocao.pdf` → `D:\docs\baocao.docx` (hoặc `<output_dir>\baocao.docx`).
- Nếu đã tồn tại và **không** ghi đè → `baocao (1).docx`, `baocao (2).docx`, ...
- Nếu file đích đang mở trong Word (bị khoá) → báo lỗi rõ ràng: *"File đích đang được mở bởi chương trình khác"*.

---

## 7. Xử lý lỗi

| Tình huống | Cách phát hiện | Xử lý |
|---|---|---|
| File không phải PDF / hỏng | `pymupdf.open()` ném lỗi | Bỏ qua, ghi log |
| Sai mật khẩu | `doc.authenticate()` trả `0` | Hỏi lại, tối đa 3 lần |
| Khoảng trang sai | `parse_page_range` ném `ValueError` | Thông báo, đánh dấu file Lỗi |
| Không ghi được file đích | `PermissionError` | Đánh dấu Lỗi, gợi ý đóng Word |
| Lỗi bên trong pdf2docx | `Exception` chung | Đánh dấu Lỗi, ghi traceback vào file log |
| PDF scan (không có text) | Kiểm tra `page.get_text()` rỗng trên vài trang đầu | Cảnh báo: "PDF dạng ảnh, kết quả không chỉnh sửa được chữ" |

Ngoài log trên giao diện, ứng dụng ghi log chi tiết ra file:
`%LOCALAPPDATA%\ZenixPdfConvert\logs\app.log` (dùng `RotatingFileHandler`, 1 MB × 3 file).

---

## 8. Cài đặt & chạy (môi trường phát triển)

### 8.1. `requirements.txt`

```
pdf2docx>=0.5.8
PyMuPDF>=1.23
PySide6>=6.6
```

Dev:

```
pytest
pyinstaller>=6.0
```

### 8.2. Các bước

```powershell
# Tạo môi trường ảo
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Cài thư viện
pip install -r requirements.txt

# Chạy ứng dụng
python main.py
```

### 8.3. `main.py`

```python
import sys
from PySide6.QtWidgets import QApplication
from zenix_pdf.gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Zenix PDF Convert")
    app.setOrganizationName("Zenix")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

> **Lưu ý Windows + multiprocessing**: nếu bật `multi_processing=True` trong bản đóng gói `.exe`, phải gọi `multiprocessing.freeze_support()` ở đầu `main()`, nếu không mỗi tiến trình con sẽ mở thêm một cửa sổ app.

---

## 9. Đóng gói (PyInstaller)

```powershell
pyinstaller --noconfirm --windowed --name ZenixPdfConvert `
  --icon zenix_pdf\gui\resources\icon.ico `
  --add-data "zenix_pdf\gui\resources;zenix_pdf\gui\resources" `
  --collect-all pdf2docx `
  main.py
```

- `--windowed`: không hiện cửa sổ console.
- `--collect-all pdf2docx`: đảm bảo kèm đủ module con của pdf2docx.
- Dùng chế độ **one-folder** (mặc định) để khởi động nhanh; `--onefile` tiện phân phối nhưng mở chậm hơn do phải giải nén mỗi lần.
- Kích thước thực tế: **~255 MB** (one-folder). Trong đó OpenCV `cv2` ~110 MB — phụ thuộc bắt buộc của pdf2docx, không bỏ được; Qt ~45 MB; PyMuPDF ~38 MB. `zenix_pdf.spec` đã loại các module/DLL Qt không dùng (QtQuick, QtQml, QtPdf, QtNetwork, `opengl32sw.dll`, bản dịch...), giảm từ ~304 MB.
- Khuyến nghị build bằng `pyinstaller --noconfirm zenix_pdf.spec` (file spec đã gồm toàn bộ tuỳ chọn ở trên).
- Kiểm tra bản build trên máy Windows "sạch" (không cài Python).

Tuỳ chọn: tạo bộ cài bằng **Inno Setup** từ thư mục `dist\ZenixPdfConvert\`.

---

## 10. Hạn chế đã biết

| Hạn chế | Nguyên nhân | Hướng xử lý |
|---|---|---|
| PDF scan không ra chữ | pdf2docx chỉ đọc lớp text có sẵn | v2: tích hợp OCR (Tesseract / `ocrmypdf`) trước khi convert |
| Bố cục phức tạp (text box chồng, văn bản xoay, biểu đồ vector) có thể lệch | Giới hạn thuật toán phân tích layout | Ghi chú cho người dùng; thử lại với `multi_processing=False` |
| Bảng không có đường kẻ đôi khi bị nhận thành đoạn văn | Nhận diện bảng dựa trên vector/căn lề | Chấp nhận ở v1 |
| Font không có trên máy hiển thị khác bản gốc | DOCX chỉ lưu tên font, không nhúng | Cài font tương ứng hoặc thay font trong Word |
| Không huỷ được giữa một file | `convert()` là lời gọi chặn | v2: chạy trong tiến trình con (mục 6.3) |
| File rất lớn (hàng trăm trang) tốn RAM | Phân tích toàn bộ trang | Bật đa tiến trình, hoặc chia nhỏ khoảng trang |

---

## 11. Kiểm thử

### 11.1. Unit test (`pytest`)

- `test_page_range.py`: `"1-3,5"`, `" 2 - 4 "`, `"5-3"` (lỗi), `"0"` (lỗi), vượt số trang, chuỗi rỗng.
- `test_paths.py`: tạo tên `(1)`, `(2)` khi trùng; ghi đè.
- `test_converter.py`: convert các PDF mẫu trong `tests/samples/`, kiểm tra file DOCX tạo ra mở được bằng `python-docx` và có số đoạn > 0.

### 11.2. Bộ PDF mẫu nên có

- Văn bản thuần, tiếng Việt có dấu (kiểm tra Unicode/font).
- Có bảng kẻ khung và bảng không kẻ khung.
- Có hình ảnh, header/footer, 2 cột.
- PDF có mật khẩu.
- PDF scan.
- PDF lớn (≥ 200 trang) để kiểm tra hiệu năng và độ mượt của GUI.

### 11.3. Kiểm thử thủ công GUI

- Kéo thả nhiều file, có lẫn file không phải PDF.
- Đóng cửa sổ khi đang convert.
- File đích đang mở trong Word.
- Thư mục đầu ra không có quyền ghi.

---

## 12. Lộ trình phát triển

| Phiên bản | Nội dung |
|---|---|
| **v1.0** | Batch convert, khoảng trang, mật khẩu, tiến trình, log, đóng gói `.exe`, CLI cơ bản (`--convert`) |
| v1.1 | Xem trước thumbnail trang PDF (render bằng PyMuPDF `page.get_pixmap()`), giao diện sáng/tối |
| v2.0 | Huỷ tức thì (tiến trình con), OCR cho PDF scan |
| v2.1 | Đa ngôn ngữ giao diện (Việt/Anh) bằng Qt Linguist |

---

## 13. Giấy phép thư viện

Cần lưu ý khi phân phối, đặc biệt nếu dùng cho mục đích thương mại:

| Thư viện | Giấy phép | Ghi chú |
|---|---|---|
| PyMuPDF | **AGPL-3.0** hoặc thương mại (Artifex) | Phân phối phần mềm đóng mã nguồn cần mua license thương mại |
| pdf2docx | GPL-3.0 | Phần mềm phân phối kèm phải tương thích GPL |
| PySide6 | LGPL-3.0 | Dùng được trong phần mềm thương mại nếu tuân thủ LGPL (liên kết động) |
| python-docx | MIT | — |

> Tóm lại: nếu phát hành **mã nguồn mở** (GPL/AGPL) thì không vướng; nếu phát hành **mã nguồn đóng / thương mại** thì cần license thương mại cho PyMuPDF và xem xét lại pdf2docx.
