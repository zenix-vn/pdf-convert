"""Chế độ dòng lệnh: main.py --convert a.pdf b.pdf [-o OUT] [-p "1-3"] [--overwrite] [--mp] [--no-ocr]"""

import argparse
import logging
import sys
from pathlib import Path

from .core.converter import PdfConverterService
from .core.models import ConvertJob, ConvertOptions
from .core.pdf_info import inspect_pdf

log = logging.getLogger(__name__)


def _out(msg: str):
    # Bản .exe dạng windowed không có console (sys.stdout = None) -> chỉ ghi log file
    log.info(msg)
    if sys.stdout is not None:
        print(msg)


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="ZenixPdfConvert --convert")
    ap.add_argument("pdfs", nargs="+", type=Path)
    ap.add_argument("-o", "--output-dir", type=Path)
    ap.add_argument("-p", "--pages", default="")
    ap.add_argument("--password")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--mp", action="store_true", help="đa tiến trình")
    ap.add_argument("--no-ocr", action="store_true", help="không OCR trang dạng ảnh")
    args = ap.parse_args(argv)

    opts = ConvertOptions(args.output_dir, args.pages, args.overwrite, args.mp, not args.no_ocr)
    service = PdfConverterService()
    failed = 0
    for pdf in args.pdfs:
        try:
            info = inspect_pdf(pdf, args.password)
            if info.needs_password:
                raise ValueError("PDF cần mật khẩu (dùng --password)")
            job = ConvertJob(pdf_path=pdf, page_count=info.page_count, password=args.password)
            out = service.convert(job, opts)
            _out(f"OK  {pdf} -> {out}")
        except Exception as e:
            failed += 1
            _out(f"ERR {pdf}: {e}")
    return 1 if failed else 0
