import sys
from pathlib import Path

import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _make_pdf(path: Path, pages: int, password: str | None = None) -> Path:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Trang {i + 1}", fontsize=18)
        page.insert_text((72, 110), "Tiếng Việt có dấu: Xin chào thế giới", fontsize=12,
                         fontname="helv")
    kwargs = {}
    if password:
        kwargs = dict(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw=password,
            owner_pw=password + "_owner",
        )
    doc.save(str(path), **kwargs)
    doc.close()
    return path


@pytest.fixture
def make_pdf(tmp_path):
    def factory(name="sample.pdf", pages=3, password=None):
        return _make_pdf(tmp_path / name, pages, password)

    return factory
