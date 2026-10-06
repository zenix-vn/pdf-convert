"""Đọc thông tin PDF bằng PyMuPDF trước khi chuyển đổi."""

from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass
class PdfInfo:
    page_count: int
    needs_password: bool
    is_scanned: bool = False


def inspect_pdf(path: str | Path, password: str | None = None) -> PdfInfo:
    """Trả về thông tin PDF. needs_password=True nếu file mã hoá và mật khẩu sai/thiếu.

    Ném exception nếu file không mở được (hỏng / không phải PDF).
    """
    with pymupdf.open(str(path)) as doc:
        if not doc.is_pdf:
            raise ValueError("File không phải định dạng PDF")
        if doc.needs_pass:
            if not password or not doc.authenticate(password):
                return PdfInfo(page_count=0, needs_password=True)
        return PdfInfo(
            page_count=doc.page_count,
            needs_password=False,
            is_scanned=_looks_scanned(doc),
        )


def _looks_scanned(doc, sample: int = 3) -> bool:
    """Vài trang đầu không có lớp chữ dùng được (ảnh scan/chụp hoặc chữ dạng đường vector)."""
    from .ocr import page_needs_ocr

    n = min(sample, doc.page_count)
    return n > 0 and all(page_needs_ocr(doc[i]) for i in range(n))
