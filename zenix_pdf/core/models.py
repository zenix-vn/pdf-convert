from dataclasses import dataclass
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
    output_dir: Path | None = None  # None = cùng thư mục với PDF
    page_spec: str = ""  # "" = tất cả trang, ví dụ "1-3, 5"
    overwrite: bool = False
    multi_processing: bool = False
    ocr: bool = True  # tự nhận dạng chữ (OCR) cho trang dạng ảnh / chữ vector


@dataclass
class ConvertJob:
    pdf_path: Path
    page_count: int = 0
    password: str | None = None
    output_path: Path | None = None
    status: JobStatus = JobStatus.PENDING
    error: str = ""
    is_scanned: bool = False
