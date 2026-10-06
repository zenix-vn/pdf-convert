import os
from pathlib import Path


def resolve_output_path(pdf_path: Path, output_dir: Path | None, overwrite: bool) -> Path:
    """baocao.pdf -> <output_dir|thư mục PDF>/baocao.docx; tránh trùng bằng ' (1)', ' (2)'..."""
    pdf_path = Path(pdf_path)
    folder = Path(output_dir) if output_dir else pdf_path.parent
    target = folder / f"{pdf_path.stem}.docx"
    if overwrite or not target.exists():
        return target
    i = 1
    while True:
        candidate = folder / f"{pdf_path.stem} ({i}).docx"
        if not candidate.exists():
            return candidate
        i += 1


def is_writable_dir(path: Path) -> bool:
    path = Path(path)
    return path.is_dir() and os.access(path, os.W_OK)


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share"
    d = Path(base) / "ZenixPdfConvert"
    d.mkdir(parents=True, exist_ok=True)
    return d
