"""Lõi chuyển đổi PDF -> DOCX, bọc pdf2docx. Không phụ thuộc Qt."""

import logging
from pathlib import Path

from pdf2docx import Converter

from ..utils.paths import resolve_output_path
from .models import ConvertJob, ConvertOptions
from .page_range import parse_page_range

log = logging.getLogger(__name__)


def _page_kwargs(pages: list[int] | None, multi_processing: bool) -> dict:
    """pdf2docx chỉ hỗ trợ đa tiến trình với khoảng trang liên tục (start/end)."""
    if pages is None:
        return {"multi_processing": multi_processing}
    contiguous = pages == list(range(pages[0], pages[-1] + 1))
    if contiguous:
        return {"start": pages[0], "end": pages[-1] + 1, "multi_processing": multi_processing}
    if multi_processing:
        log.warning("Khoảng trang không liên tục: tắt chế độ đa tiến trình cho file này.")
    return {"pages": pages, "multi_processing": False}


class PdfConverterService:
    def convert(self, job: ConvertJob, options: ConvertOptions) -> Path:
        pages = parse_page_range(options.page_spec, job.page_count)
        out = resolve_output_path(job.pdf_path, options.output_dir, options.overwrite)
        out.parent.mkdir(parents=True, exist_ok=True)

        cv = Converter(str(job.pdf_path), password=job.password)
        try:
            try:
                cv.convert(str(out), **_page_kwargs(pages, options.multi_processing))
            except PermissionError as e:
                raise PermissionError(
                    f"Không ghi được file đích (có thể đang mở trong Word): {out}"
                ) from e
        finally:
            cv.close()

        job.output_path = out
        return out
