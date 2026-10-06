from zenix_pdf.utils.paths import resolve_output_path


def test_same_dir(tmp_path):
    pdf = tmp_path / "baocao.pdf"
    assert resolve_output_path(pdf, None, False) == tmp_path / "baocao.docx"


def test_custom_dir(tmp_path):
    out = tmp_path / "out"
    assert resolve_output_path(tmp_path / "a.pdf", out, False) == out / "a.docx"


def test_avoid_duplicates(tmp_path):
    pdf = tmp_path / "baocao.pdf"
    (tmp_path / "baocao.docx").touch()
    assert resolve_output_path(pdf, None, False) == tmp_path / "baocao (1).docx"
    (tmp_path / "baocao (1).docx").touch()
    assert resolve_output_path(pdf, None, False) == tmp_path / "baocao (2).docx"


def test_overwrite(tmp_path):
    pdf = tmp_path / "baocao.pdf"
    (tmp_path / "baocao.docx").touch()
    assert resolve_output_path(pdf, None, True) == tmp_path / "baocao.docx"
