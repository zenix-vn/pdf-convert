"""Lõi chuyển đổi PDF -> DOCX, bọc pdf2docx. Không phụ thuộc Qt."""

import logging
import tempfile
from collections.abc import Callable
from pathlib import Path

import pymupdf
from pdf2docx import Converter

from ..utils.paths import resolve_output_path
from .models import ConvertJob, ConvertOptions
from .page_range import parse_page_range

log = logging.getLogger(__name__)


class ConvertCancelled(Exception):
    pass


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


def _pages_needing_ocr(job: ConvertJob, pages: list[int] | None) -> list[int]:
    from .ocr import page_needs_ocr

    with pymupdf.open(str(job.pdf_path)) as doc:
        if doc.needs_pass:
            doc.authenticate(job.password or "")
        selected = pages if pages is not None else range(doc.page_count)
        return [p for p in selected if page_needs_ocr(doc[p])]


def _normalize_ocr_text(docx_path: Path):
    """Font Times New Roman dùng chung glyph cho '-'/soft hyphen và space/nbsp nên chữ dựng
    lại từ OCR bị trích ngược thành U+00AD/U+00A0 (Word ẩn soft hyphen) -> đổi về ký tự thường."""
    import docx
    from docx.oxml.ns import qn

    document = docx.Document(str(docx_path))
    changed = False
    for t in document.element.body.iter(qn("w:t")):
        if t.text and ("­" in t.text or " " in t.text):
            t.text = t.text.replace("­", "-").replace(" ", " ")
            changed = True
    if changed:
        document.save(str(docx_path))


class PdfConverterService:
    def __init__(self):
        self._ocr_engine = None

    def _engine(self):
        if self._ocr_engine is None:
            from .ocr import OcrEngine

            self._ocr_engine = OcrEngine()
        return self._ocr_engine

    def convert(self, job: ConvertJob, options: ConvertOptions,
                cancelled: Callable[[], bool] | None = None) -> Path:
        pages = parse_page_range(options.page_spec, job.page_count)
        out = resolve_output_path(job.pdf_path, options.output_dir, options.overwrite)
        out.parent.mkdir(parents=True, exist_ok=True)

        ocr_pages = _pages_needing_ocr(job, pages) if options.ocr else []
        if ocr_pages:
            self._convert_with_ocr(job, pages, ocr_pages, out, options, cancelled)
        else:
            self._run_pdf2docx(str(job.pdf_path), job.password, out,
                               _page_kwargs(pages, options.multi_processing))

        job.output_path = out
        return out

    def _convert_with_ocr(self, job, pages, ocr_pages, out, options, cancelled):
        engine = self._engine()
        log.info("PDF dạng ảnh/chữ vector: nhận dạng chữ (OCR) %d trang...", len(ocr_pages))

        def progress(i: int, n: int):
            log.info("[OCR] (%d/%d)", i, n)

        with pymupdf.open(str(job.pdf_path)) as src:
            if src.needs_pass:
                src.authenticate(job.password or "")
            selected = pages if pages is not None else list(range(src.page_count))
            rebuilt = engine.build_document(src, selected, progress, cancelled)
        if cancelled and cancelled():
            rebuilt.close()
            raise ConvertCancelled("Đã huỷ")

        with tempfile.TemporaryDirectory(prefix="zenix_ocr_") as tmp:
            tmp_pdf = Path(tmp) / "ocr.pdf"
            rebuilt.save(str(tmp_pdf), garbage=3, deflate=True)
            rebuilt.close()
            self._run_pdf2docx(str(tmp_pdf), None, out,
                               {"multi_processing": options.multi_processing})
        _normalize_ocr_text(out)

    @staticmethod
    def _run_pdf2docx(pdf: str, password: str | None, out: Path, kwargs: dict):
        cv = Converter(pdf, password=password)
        try:
            try:
                cv.convert(str(out), **kwargs)
            except PermissionError as e:
                raise PermissionError(
                    f"Không ghi được file đích (có thể đang mở trong Word): {out}"
                ) from e
        finally:
            cv.close()
