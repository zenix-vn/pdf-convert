"""Phân tích chuỗi khoảng trang do người dùng nhập (1-based) thành danh sách 0-based."""

import re

_PART_RE = re.compile(r"^(\d+)\s*(?:-\s*(\d+))?$")


def parse_page_range(spec: str, page_count: int) -> list[int] | None:
    """'1-3, 5' -> [0, 1, 2, 4]. Chuỗi rỗng -> None (tất cả trang).

    Ném ValueError nếu cú pháp sai hoặc trang vượt quá page_count.
    """
    spec = (spec or "").strip()
    if not spec:
        return None

    pages: set[int] = set()
    for raw in spec.split(","):
        part = raw.strip()
        if not part:
            continue
        m = _PART_RE.match(part)
        if not m:
            raise ValueError(f"Khoảng trang không hợp lệ: '{part}'")
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        if start < 1 or end < 1:
            raise ValueError(f"Số trang phải bắt đầu từ 1: '{part}'")
        if start > end:
            raise ValueError(f"Trang đầu lớn hơn trang cuối: '{part}'")
        if end > page_count:
            raise ValueError(f"Trang {end} vượt quá số trang của file ({page_count})")
        pages.update(range(start - 1, end))

    if not pages:
        raise ValueError("Không có trang nào được chọn")
    return sorted(pages)
