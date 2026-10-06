import docx
import pytest

from zenix_pdf.core.converter import PdfConverterService, _page_kwargs
from zenix_pdf.core.models import ConvertJob, ConvertOptions
from zenix_pdf.core.pdf_info import inspect_pdf


def _text(path) -> str:
    return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)


def test_inspect(make_pdf):
    info = inspect_pdf(make_pdf(pages=4))
    assert info.page_count == 4
    assert not info.needs_password
    assert not info.is_scanned


def test_inspect_password(make_pdf):
    pdf = make_pdf(password="secret")
    assert inspect_pdf(pdf).needs_password
    assert inspect_pdf(pdf, "wrong").needs_password
    info = inspect_pdf(pdf, "secret")
    assert not info.needs_password and info.page_count == 3


def test_inspect_not_pdf(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"this is not a pdf")
    with pytest.raises(Exception):
        inspect_pdf(bad)


def test_convert_all_pages(make_pdf):
    pdf = make_pdf(pages=3)
    job = ConvertJob(pdf_path=pdf, page_count=3)
    out = PdfConverterService().convert(job, ConvertOptions())
    assert out == pdf.with_suffix(".docx") and out.exists()
    text = _text(out)
    assert "Trang 1" in text and "Trang 3" in text


def test_convert_page_range_and_output_dir(make_pdf, tmp_path):
    pdf = make_pdf(pages=5)
    job = ConvertJob(pdf_path=pdf, page_count=5)
    opts = ConvertOptions(output_dir=tmp_path / "out", page_spec="2, 4")
    out = PdfConverterService().convert(job, opts)
    assert out.parent == tmp_path / "out"
    text = _text(out)
    assert "Trang 2" in text and "Trang 4" in text
    assert "Trang 1" not in text and "Trang 3" not in text


def test_convert_with_password(make_pdf):
    pdf = make_pdf(password="secret")
    job = ConvertJob(pdf_path=pdf, page_count=3, password="secret")
    out = PdfConverterService().convert(job, ConvertOptions())
    assert "Trang 2" in _text(out)


def test_page_kwargs():
    assert _page_kwargs(None, True) == {"multi_processing": True}
    assert _page_kwargs([1, 2, 3], True) == {"start": 1, "end": 4, "multi_processing": True}
    assert _page_kwargs([0, 2], True) == {"pages": [0, 2], "multi_processing": False}
