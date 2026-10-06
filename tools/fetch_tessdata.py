"""Tải dữ liệu OCR tiếng Việt (Tesseract LSTM, bản "best") vào zenix_pdf/resources/tessdata.

Chạy một lần trước khi chạy app / đóng gói .exe:  python tools/fetch_tessdata.py
"""

import sys
import urllib.request
from pathlib import Path

URL = "https://github.com/tesseract-ocr/tessdata_best/raw/main/script/Vietnamese.traineddata"
DEST = Path(__file__).resolve().parents[1] / "zenix_pdf" / "resources" / "tessdata"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    DEST.mkdir(parents=True, exist_ok=True)
    target = DEST / "Vietnamese.traineddata"
    if target.is_file() and target.stat().st_size > 1_000_000 and "--force" not in sys.argv:
        print(f"Đã có: {target}")
        return 0
    print(f"Đang tải {URL} ...")
    tmp = target.with_suffix(".part")
    urllib.request.urlretrieve(URL, tmp)
    tmp.replace(target)
    print(f"Xong: {target} ({target.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
