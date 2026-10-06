"""OCR cho trang PDF không có lớp chữ: ảnh scan/chụp, hoặc chữ đã bị convert sang
đường vector (outline, hay gặp ở file xuất từ CorelDRAW/Illustrator).

Mỗi trang cần OCR được dựng lại thành một trang PDF "sạch" gồm chữ thật (Times New Roman),
đường kẻ bảng dạng vector, ô checkbox và ảnh cắt (logo, con dấu, chữ ký...). Sau đó pdf2docx
xử lý như PDF thường nên vẫn nhận ra bảng, đoạn văn.

OCR dùng Tesseract tích hợp sẵn trong PyMuPDF (MuPDF), chỉ cần file *.traineddata,
không cần cài Tesseract. Tải dữ liệu bằng: python tools/fetch_tessdata.py
"""

import logging
import os
import statistics
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pymupdf

log = logging.getLogger(__name__)

# Model "script/Vietnamese" (tessdata_best) nhận dấu tiếng Việt tốt hơn "vie"; kèm cả chữ Latin.
LANGUAGES = ("Vietnamese", "vie")
DEFAULT_DPI = 300

_PACKAGE_TESSDATA = Path(__file__).resolve().parents[1] / "resources" / "tessdata"

CHECKBOX = "\u25a1"  # □


# --------------------------------------------------------------------------- tài nguyên


def find_tessdata() -> tuple[Path, str] | None:
    """Tìm thư mục tessdata có model tiếng Việt. Trả về (thư mục, tên ngôn ngữ) hoặc None."""
    dirs: list[Path] = []
    if env := os.environ.get("ZENIX_TESSDATA") or os.environ.get("TESSDATA_PREFIX"):
        dirs.append(Path(env))
    dirs.append(_PACKAGE_TESSDATA)
    if base := os.environ.get("LOCALAPPDATA"):
        dirs.append(Path(base) / "ZenixPdfConvert" / "tessdata")
    try:
        if sys_dir := pymupdf.get_tessdata():
            dirs.append(Path(sys_dir))
    except Exception:  # không cài Tesseract
        pass
    for lang in LANGUAGES:
        for d in dirs:
            if (d / f"{lang}.traineddata").is_file():
                return d, lang
    return None


def _font_files() -> tuple[str, str]:
    """Font TrueType có đủ dấu tiếng Việt (thường, đậm)."""
    fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    candidates = [
        (fonts_dir / "times.ttf", fonts_dir / "timesbd.ttf"),
        (fonts_dir / "arial.ttf", fonts_dir / "arialbd.ttf"),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
         Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf")),
    ]
    for regular, bold in candidates:
        if regular.is_file():
            return str(regular), str(bold if bold.is_file() else regular)
    raise RuntimeError("Không tìm thấy font hỗ trợ tiếng Việt (Times New Roman / Arial)")


# --------------------------------------------------------------------------- phát hiện


def page_needs_ocr(page: pymupdf.Page) -> bool:
    """Trang không có lớp chữ dùng được: chỉ có ảnh, chữ đã bị chuyển thành đường vector,
    hoặc chữ ẩn (lớp OCR có sẵn của bản scan, pdf2docx bỏ qua)."""
    text_len = len("".join(page.get_text("text").split()))
    if text_len < 50:
        return bool(page.get_images()) or _path_items(page) > 2000
    if _path_items(page) > 40 * text_len:
        return True
    return _image_coverage(page) > 0.5 and (text_len < 200 or _hidden_text_ratio(page) > 0.8)


def _hidden_text_ratio(page: pymupdf.Page) -> float:
    try:
        spans = page.get_texttrace()
    except Exception:
        return 0.0
    total = sum(len(s["chars"]) for s in spans)
    hidden = sum(len(s["chars"]) for s in spans if s["type"] == 3)
    return hidden / total if total else 0.0


def _path_items(page: pymupdf.Page) -> int:
    try:
        return sum(len(d["items"]) for d in page.get_drawings())
    except Exception:
        return 0


def _image_coverage(page: pymupdf.Page) -> float:
    area = abs(page.rect)
    if not area:
        return 0.0
    covered = 0.0
    for info in page.get_image_info():
        covered += abs(pymupdf.Rect(info["bbox"]) & page.rect)
    return min(covered / area, 1.0)


# --------------------------------------------------------------------------- dựng trang


@dataclass
class _Word:
    text: str
    x0: float
    x1: float
    kind: str = "text"  # text | dots | box
    bold: bool = False
    stroke: float | None = None  # độ dày nét / cỡ chữ


@dataclass
class _Line:
    y0: float
    y1: float
    words: list[_Word] = field(default_factory=list)
    size: float = 0.0
    color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    baseline: float = 0.0
    weak: bool = False  # cỡ chữ ước lượng kém tin cậy (dòng quá ngắn)


@dataclass
class _Segment:
    """Đoạn thẳng (đường kẻ) theo toạ độ pixel."""

    x0: float
    y0: float
    x1: float
    y1: float
    width: float
    color: tuple[float, float, float]


class OcrEngine:
    def __init__(self, tessdata: Path | None = None, language: str | None = None,
                 dpi: int = DEFAULT_DPI):
        if tessdata is None:
            found = find_tessdata()
            if not found:
                raise RuntimeError(
                    "Thiếu dữ liệu OCR tiếng Việt (Vietnamese.traineddata). "
                    "Chạy: python tools/fetch_tessdata.py"
                )
            tessdata, language = found
        self.tessdata = str(tessdata)
        self.language = language or LANGUAGES[0]
        self.dpi = dpi
        regular, bold = _font_files()
        self.font = pymupdf.Font(fontfile=regular)
        self.font_bold = pymupdf.Font(fontfile=bold)

    # ---------------------------------------------------------------- API

    def build_document(self, src: pymupdf.Document, pages: list[int],
                       progress: Callable[[int, int], None] | None = None,
                       cancelled: Callable[[], bool] | None = None) -> pymupdf.Document:
        """Tạo PDF mới gồm các trang `pages` của `src`; trang nào cần OCR thì được dựng lại."""
        out = pymupdf.open()
        total = len(pages)
        for i, pno in enumerate(pages, 1):
            if cancelled and cancelled():
                break
            page = src[pno]
            if page_needs_ocr(page):
                self.rebuild_page(page, out)
            else:
                out.insert_pdf(src, from_page=pno, to_page=pno)
            if progress:
                progress(i, total)
        return out

    def rebuild_page(self, page: pymupdf.Page, out: pymupdf.Document) -> pymupdf.Page:
        rect = page.rect
        pix = page.get_pixmap(dpi=self.dpi, colorspace=pymupdf.csRGB, alpha=False)
        rgb = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3).copy()
        sx, sy = rect.width / pix.width, rect.height / pix.height  # pixel -> point
        k = 1 / sx  # pixel trên mỗi point

        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        angle = _estimate_skew(gray)
        if abs(angle) >= 0.2:
            log.debug("Trang %d nghiêng %.2f°, xoay thẳng lại", page.number + 1, angle)
            rgb, gray = _rotate(rgb, angle), _rotate(gray, angle)
        ink = _ink_mask(gray, k)

        h_lines, v_lines, line_mask = _find_lines(ink, rgb, k)
        dots, dot_mask = _find_dot_leaders(ink, k)
        boxes, box_mask = _find_checkboxes(ink & ~line_mask, k)
        figures, fig_mask = _find_figures(ink & ~line_mask & ~dot_mask & ~box_mask, k)

        clean = ink & ~line_mask & ~dot_mask & ~box_mask & ~fig_mask
        if debug_dir := os.environ.get("ZENIX_OCR_DEBUG"):
            cv2.imwrite(str(Path(debug_dir) / f"clean_{page.number}.png"), 255 - clean)
        lines = self._ocr(clean, rect, sx, sy)

        new = out.new_page(width=rect.width, height=rect.height)
        for x0, y0, x1, y1 in figures:
            crop = np.ascontiguousarray(rgb[y0:y1, x0:x1])
            ok, png = cv2.imencode(".png", cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
            if ok:
                new.insert_image(pymupdf.Rect(x0 * sx, y0 * sy, x1 * sx, y1 * sy),
                                 stream=png.tobytes())
        for seg in h_lines + v_lines:
            new.draw_line((seg.x0 * sx, seg.y0 * sy), (seg.x1 * sx, seg.y1 * sy),
                          color=seg.color, width=max(seg.width * sx, 0.5))

        self._style_lines(lines, clean, rgb, ink, sx, sy, k)
        self._attach_pseudo_words(lines, dots, boxes, sx, sy)
        self._write_text(new, lines)
        return new

    # ---------------------------------------------------------------- OCR

    def _ocr(self, clean: np.ndarray, rect: pymupdf.Rect, sx: float, sy: float) -> list[_Line]:
        """OCR theo từng mảnh dòng chữ.

        Form/biểu mẫu có nhiều khoảng trống làm bộ phân tích bố cục của Tesseract gộp/cắt
        dòng sai. Vì vậy tự tách các mảnh dòng, xếp lên ảnh tạm theo từng hàng (bỏ khoảng
        trống, căn thẳng baseline), OCR một lần rồi ánh xạ toạ độ về trang gốc.
        """
        k = 1 / sx
        tiles, labels, ids = _text_tiles(clean, k)
        if not tiles:
            return []
        pad = int(6 * k)
        rows = _group_rows(tiles)
        gap = int(14 * k)
        # vị trí (left, top) mỗi mảnh trên ảnh tạm
        place: dict[int, tuple[int, int]] = {}
        row_spans: list[tuple[int, int, list[int]]] = []
        y, width = pad, 0
        # baseline mỗi mảnh (tính từ đỉnh mảnh) để căn các mảnh cùng hàng thẳng dòng
        base = {}
        for t, (x0, y0, x1, y1) in enumerate(tiles):
            own = np.isin(labels[y0:y1, x0:x1], ids[t]) & (clean[y0:y1, x0:x1] > 0)
            base[t] = _line_bands(own, 1)[0][2]
        for row in rows:
            above = max(base[t] for t in row)
            below = max(tiles[t][3] - tiles[t][1] - base[t] for t in row)
            x = pad
            for t in row:
                x0, y0, x1, y1 = tiles[t]
                place[t] = (x, y + above - base[t])
                x += (x1 - x0) + gap
            width = max(width, x - gap + pad)
            row_h = above + below
            row_spans.append((y, y + row_h, row))
            y += row_h + max(pad, int(row_h * 0.8))
        canvas = np.zeros((y + pad, width), np.uint8)
        for t, (left, top) in place.items():
            x0, y0, x1, y1 = tiles[t]
            own = np.isin(labels[y0:y1, x0:x1], ids[t])
            canvas[top:top + y1 - y0, left:left + x1 - x0][own] = clean[y0:y1, x0:x1][own]

        if debug_dir := os.environ.get("ZENIX_OCR_DEBUG"):
            cv2.imwrite(str(Path(debug_dir) / "canvas.png"), 255 - canvas)
        ok, png = cv2.imencode(".png", 255 - canvas)
        tmp = pymupdf.open()
        try:
            tpage = tmp.new_page(width=canvas.shape[1] * sx, height=canvas.shape[0] * sy)
            tpage.insert_image(tpage.rect, stream=png.tobytes())
            tp = tpage.get_textpage_ocr(language=self.language, dpi=self.dpi, full=True,
                                        tessdata=self.tessdata)
            raw = tpage.get_text("rawdict", textpage=tp)
        finally:
            tmp.close()

        if debug_dir:
            dump = [
                "".join(c["c"] for sp in ln["spans"] for c in sp["chars"])
                + f"  @{[round(v / sx) for v in ln['bbox']]}"
                for b in raw.get("blocks", []) for ln in b.get("lines", [])
            ]
            (Path(debug_dir) / "canvas.txt").write_text("\n".join(dump), encoding="utf-8")
        # gom ký tự về mảnh chứa nó, đổi toạ độ x về trang gốc
        row_tops = np.array([r[0] for r in row_spans])
        per_tile: dict[int, list[tuple[float, float, list[dict]]]] = {}
        for block in raw.get("blocks", []):
            for ln in block.get("lines", []):
                found: dict[int, list[dict]] = {}
                for sp in ln["spans"]:
                    for c in sp["chars"]:
                        bb = c["bbox"]
                        cx = (bb[0] + bb[2]) / 2 / sx
                        cy = (bb[1] + bb[3]) / 2 / sy
                        r = int(np.searchsorted(row_tops, cy + pad, side="right")) - 1
                        if r < 0:
                            continue
                        t = _tile_at(row_spans[r][2], place, tiles, cx, gap)
                        if t is None:
                            continue
                        dx = (tiles[t][0] - place[t][0]) * sx
                        found.setdefault(t, []).append(
                            {"c": c["c"], "bbox": (bb[0] + dx, 0, bb[2] + dx, 0)})
                lb = ln["bbox"]
                for t, chars in found.items():
                    per_tile.setdefault(t, []).append(((lb[1] + lb[3]) / 2, lb[3] - lb[1], chars))

        lines: list[_Line] = []
        for t, parts in per_tile.items():
            # Tesseract có thể tách một dòng thành vài "dòng" cùng độ cao -> gộp lại
            parts.sort(key=lambda p: p[0])
            groups: list[list] = []
            for cy, hgt, chars in parts:
                if groups and abs(cy - groups[-1][0]) < 0.5 * hgt:
                    groups[-1][1].append(chars)
                else:
                    groups.append([cy, [chars]])
            word_groups = []
            for _, pieces in groups:
                # giữ thứ tự ký tự trong từng phần, chỉ xếp các phần theo vị trí bắt đầu
                pieces.sort(key=lambda cs: cs[0]["bbox"][0])
                words = [w for cs in pieces for w in _split_words(cs)
                         if not _is_stray(w)]
                for a, b in zip(words, words[1:]):  # bbox các phần có thể lấn nhau
                    if a.x1 > b.x0:
                        a.x1 = b.x0 = min(max((a.x1 + b.x0) / 2, a.x0), b.x1)
                if words and any(any(ch.isalnum() for ch in w.text) for w in words):
                    word_groups.append(words)
            if not word_groups:
                continue
            x0, y0, x1, y1 = tiles[t]
            own = np.isin(labels[y0:y1, x0:x1], ids[t]) & (clean[y0:y1, x0:x1] > 0)
            bands = _line_bands(own, len(word_groups))
            for words, (b0, b1, base) in zip(word_groups, bands):
                em = max(base - b0, 1) / 0.85
                cols = own[b0:b1].any(axis=0)
                words = [piece for wd in words
                         for piece in self._split_by_gaps(wd, cols, x0, sx, em)]
                line = _Line((y0 + b0) * sy, (y0 + b1) * sy, words)
                line.baseline = (y0 + base) * sy
                lines.append(line)
        lines.sort(key=lambda ln: (ln.y0, ln.words[0].x0))
        return lines

    def _split_by_gaps(self, wd: _Word, cols: np.ndarray, x_off: int, sx: float,
                       em: float) -> list[_Word]:
        """Khôi phục dấu cách bị mất: tách từ tại khe trống trên ảnh rộng >= 0.22 em."""
        min_gap = em * 0.22
        if len(wd.text) < 2:
            return [wd]
        c0 = max(int(wd.x0 / sx) - x_off, 0)
        c1 = min(int(wd.x1 / sx) - x_off + 1, len(cols))
        seg = cols[c0:c1]
        ink_cols = np.nonzero(seg)[0]
        if len(ink_cols) < 2:
            return [wd]
        first, last = int(ink_cols[0]), int(ink_cols[-1])
        gaps, run = [], None  # (đầu, cuối) mỗi khe trống
        for i in range(first, last + 1):
            if not seg[i]:
                run = i if run is None else run
            elif run is not None:
                if i - run >= min_gap:
                    gaps.append((run, i))
                run = None
        n = len(wd.text)
        if not gaps:
            return [wd]
        # Các cụm mực giữa các khe. Chọn một dãy cụm liên tiếp (cụm ở mép có thể là của từ
        # bên cạnh do bbox OCR lấn sang) và điểm cắt sao cho độ rộng chữ theo font khớp nhất.
        edges = [first] + [v for g in gaps for v in g] + [last + 1]
        islands = [(edges[2 * j], edges[2 * j + 1]) for j in range(len(gaps) + 1)]
        cum = np.cumsum([0.0] + [self.font.text_length(ch, fontsize=em) for ch in wd.text])
        best = None
        for s0 in range(len(islands)):
            for s1 in range(s0, min(len(islands), s0 + n)):
                cost, cuts = _fit_islands(cum, islands[s0:s1 + 1])
                cost += sum(e - b for b, e in islands[:s0] + islands[s1 + 1:])  # mực bị bỏ
                if best is None or cost < best[0]:
                    best = (cost, cuts, islands[s0:s1 + 1])
        _, cuts, used = best
        x_base = c0 + x_off
        return [_Word(wd.text[p:q], (x_base + b) * sx, (x_base + e) * sx, wd.kind)
                for (p, q), (b, e) in zip(cuts, used)]

    # ---------------------------------------------------------------- kiểu chữ

    def _style_lines(self, lines: list[_Line], clean, rgb, ink, sx, sy, k):
        h, w = clean.shape
        for line in lines:
            # chiều cao từ đỉnh dấu thanh tới baseline ~ 0.85 em
            by_height = max(line.baseline - line.y0, 1.0) / 0.85
            sizes = []
            for wd in line.words:
                if sum(ch.isalnum() for ch in wd.text) >= 3:
                    length = self.font.text_length(wd.text, fontsize=10)
                    if length > 0:
                        sizes.append(10 * (wd.x1 - wd.x0) / length)
            size = statistics.median(sizes) if sizes else by_height
            line.weak = not sizes
            line.size = min(max(size, by_height * 0.6), by_height * 1.5)

            py0, py1 = int(line.y0 / sy), min(int(line.y1 / sy) + 1, h)
            for wd in line.words:
                px0, px1 = int(wd.x0 / sx), min(int(wd.x1 / sx) + 1, w)
                wd.stroke = _stroke_ratio(clean[py0:py1, px0:px1], line.size * k)
            line.color = _text_color(rgb[py0:py1], ink[py0:py1])
        _snap_sizes(lines)
        if lines:  # rác: dòng 1-2 ký tự nhưng to gấp đôi cỡ chữ phổ biến
            common = statistics.median(ln.size for ln in lines)
            lines[:] = [ln for ln in lines if not (
                ln.weak and len("".join(w.text for w in ln.words)) <= 2
                and ln.size > 2 * common)]
        _mark_bold(lines)

    def _attach_pseudo_words(self, lines: list[_Line], dots, boxes, sx, sy):
        """Gắn dòng chấm "....." và ô "□" (đã xoá trước khi OCR) vào dòng chữ tương ứng."""
        page_size = statistics.median([ln.size for ln in lines]) if lines else 11.0
        items = [(seg, "dots") for seg in dots] + [(b, "box") for b in boxes]
        for (x0, y0, x1, y1), kind in items:
            X0, Y0, X1, Y1 = x0 * sx, y0 * sy, x1 * sx, y1 * sy
            cy = (Y0 + Y1) / 2
            target, best = None, None
            for ln in lines:
                if kind == "box" and not 0.35 * ln.size <= Y1 - Y0 <= 1.1 * ln.size:
                    continue  # ô vuông lệch cỡ quá nhiều so với chữ của dòng
                if ln.y0 - 1 <= cy <= ln.y1 + 1:
                    dist = 0.0 if ln.words and ln.words[0].x0 <= X0 else 1.0
                    dist += min(abs(X0 - wd.x1) for wd in ln.words) if ln.words else 0
                    if best is None or dist < best:
                        target, best = ln, dist
            if target is None:
                size = page_size
                if kind == "box":
                    size = max(size, (Y1 - Y0) * 1.3)
                    y0l, y1l = Y0 - size * 0.25, Y1 + size * 0.1
                else:
                    y0l, y1l = Y1 - size, Y1 + size * 0.25
                target = _Line(y0l, y1l, [], size)
                target.baseline = Y1 if kind == "dots" else Y1 - (Y1 - Y0) * 0.05
                lines.append(target)
            text = "." if kind == "dots" else CHECKBOX
            target.words.append(_Word(text, X0, X1, kind))
        for ln in lines:
            ln.words.sort(key=lambda wd: wd.x0)

    def _write_text(self, page: pymupdf.Page, lines: list[_Line]):
        for line in lines:
            size = line.size
            baseline = line.baseline or line.y1 - size * 0.22
            for seg in _segments(line.words, size):
                tw = pymupdf.TextWriter(page.rect, color=line.color)
                pos = pymupdf.Point(seg[0].x0, baseline)
                for i, wd in enumerate(seg):
                    font = self.font_bold if wd.bold else self.font
                    text = wd.text
                    if wd.kind == "dots":
                        unit = font.text_length(".", fontsize=size) or 1
                        text = "." * max(3, round((wd.x1 - wd.x0) / unit))
                    if i < len(seg) - 1:
                        text += " "
                    _, pos = tw.append(pos, text, font=font, fontsize=size)
                tw.write_text(page)


# --------------------------------------------------------------------------- xử lý ảnh


def _estimate_skew(gray: np.ndarray) -> float:
    """Góc nghiêng (độ) theo phương pháp chiếu ngang, dò trong ±5°."""
    scale = 1000 / max(gray.shape)
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    bw = (small < 180).astype(np.float32)
    if bw.mean() < 0.002:
        return 0.0
    h, w = bw.shape
    center = (w / 2, h / 2)

    def score(a: float) -> float:
        m = cv2.getRotationMatrix2D(center, a, 1.0)
        rot = cv2.warpAffine(bw, m, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        return float(np.var(rot.sum(axis=1)))

    base = score(0.0)
    best, best_score = 0.0, base
    for a in np.arange(-5, 5.01, 0.25):
        s = score(float(a))
        if s > best_score:
            best, best_score = float(a), s
    if best and best_score < base * 1.05:  # cải thiện không đáng kể -> coi như thẳng
        return 0.0
    if best:
        for a in np.arange(best - 0.2, best + 0.21, 0.05):
            s = score(float(a))
            if s > best_score:
                best, best_score = float(a), s
    return best


def _rotate(img: np.ndarray, angle: float) -> np.ndarray:
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    border = (255, 255, 255) if img.ndim == 3 else 255
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=border)


def _ink_mask(gray: np.ndarray, k: float) -> np.ndarray:
    """Pixel mực (255) / nền (0). Ngưỡng thích nghi để chịu được ảnh chụp sáng không đều."""
    block = int(k * 12) | 1
    adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY_INV, block, 15)
    ink = adaptive & ((gray < 225).astype(np.uint8) * 255)
    # bỏ chấm nhiễu cực nhỏ
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    noise = st[:, cv2.CC_STAT_AREA] <= 2
    noise[0] = False
    ink[noise[lab]] = 0
    return ink


def _components(mask: np.ndarray):
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    return n, lab, st


def _find_lines(ink: np.ndarray, rgb: np.ndarray, k: float):
    """Đường kẻ ngang/dọc liền nét (khung bảng, gạch chân)."""
    min_len = max(int(25 * k), 10)
    max_thick = 3 * k
    h_open = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (min_len, 1)))
    v_open = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (1, min_len)))
    mask = np.zeros_like(ink)
    segs: dict[str, list[_Segment]] = {"h": [], "v": []}
    for key, opened in (("h", h_open), ("v", v_open)):
        # nối các đoạn bị đứt nhẹ (do nghiêng/nhoè)
        kernel = (int(3 * k), 1) if key == "h" else (1, int(3 * k))
        joined = cv2.morphologyEx(opened, cv2.MORPH_CLOSE,
                                  cv2.getStructuringElement(cv2.MORPH_RECT, kernel))
        n, lab, st = _components(joined)
        for i in range(1, n):
            x, y, w, h, area = st[i]
            length, span = (w, h) if key == "h" else (h, w)
            thick = area / max(length, 1)
            if length < min_len or thick > max_thick or span > max(thick * 3, 4 * k):
                continue  # khối đặc (ảnh, ô tô màu) chứ không phải đường kẻ
            sel = lab[y:y + h, x:x + w] == i
            mask[y:y + h, x:x + w][sel] = 255
            color = _mean_color(rgb[y:y + h, x:x + w][sel & (ink[y:y + h, x:x + w] > 0)])
            if key == "h":
                cy = y + h / 2
                segs["h"].append(_Segment(x, cy, x + w, cy, thick, color))
            else:
                cx = x + w / 2
                segs["v"].append(_Segment(cx, y, cx, y + h, thick, color))
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8)) & ink
    return segs["h"], segs["v"], mask


def _find_dot_leaders(ink: np.ndarray, k: float):
    """Dòng chấm "......" / "……" để điền form. Trả về bbox pixel từng dòng chấm."""
    n, lab, st = _components(ink)
    lim = 2.2 * k
    keep = (st[:, cv2.CC_STAT_WIDTH] <= lim) & (st[:, cv2.CC_STAT_HEIGHT] <= lim)
    keep[0] = False
    small = (keep[lab] * 255).astype(np.uint8)
    run = cv2.morphologyEx(small, cv2.MORPH_CLOSE,
                           cv2.getStructuringElement(cv2.MORPH_RECT, (int(5 * k), 1)))
    run = cv2.morphologyEx(run, cv2.MORPH_OPEN,
                           cv2.getStructuringElement(cv2.MORPH_RECT, (int(15 * k), 1)))
    run = cv2.dilate(run, np.ones((3, 3), np.uint8))
    mask = run & small
    rn, rlab, rst = _components(run)
    boxes = []
    for i in range(1, rn):
        x, y, w, h, _ = rst[i]
        sel = mask[y:y + h, x:x + w] > 0
        if not sel.any():
            continue
        ys, xs = np.nonzero(sel)
        # đếm số chấm để loại chuỗi dấu thanh dính nhau tình cờ
        cnt, _, _ = _components(mask[y:y + h, x:x + w])
        if cnt - 1 < 4:
            mask[y:y + h, x:x + w] = 0
            continue
        boxes.append((x + xs.min(), y + ys.min(), x + xs.max() + 1, y + ys.max() + 1))
    return boxes, mask


def _find_checkboxes(ink: np.ndarray, k: float):
    """Ô vuông rỗng cỡ chữ (□)."""
    n, lab, st = _components(ink)
    boxes, mask = [], np.zeros_like(ink)
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if not (3 * k <= w <= 16 * k and 3 * k <= h <= 16 * k and 0.75 <= w / h <= 1.33):
            continue
        sub = lab[y:y + h, x:x + w] == i
        t = max(int(min(w, h) * 0.2), 1)
        edges = [sub[:t].any(axis=0).mean(), sub[-t:].any(axis=0).mean(),
                 sub[:, :t].any(axis=1).mean(), sub[:, -t:].any(axis=1).mean()]
        inner = sub[t + 1:h - t - 1, t + 1:w - t - 1]
        if min(edges) >= 0.85 and (inner.size == 0 or inner.mean() < 0.05):
            boxes.append((x, y, x + w, y + h))
            mask[y:y + h, x:x + w][sub] = 255
    return boxes, mask


def _find_figures(ink: np.ndarray, k: float):
    """Khối mực lớn liền nhau (logo, con dấu, chữ ký, ảnh) -> giữ nguyên dạng ảnh."""
    big = 36 * k
    n, lab, st = _components(ink)
    rects = []
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if w >= big and h >= big:
            rects.append([x, y, x + w, y + h])
    # gộp các khối chồng lấn
    merged = True
    while merged and len(rects) > 1:
        merged = False
        for a in range(len(rects)):
            for b in range(a + 1, len(rects)):
                A, B = rects[a], rects[b]
                if A[0] <= B[2] and B[0] <= A[2] and A[1] <= B[3] and B[1] <= A[3]:
                    rects[a] = [min(A[0], B[0]), min(A[1], B[1]), max(A[2], B[2]), max(A[3], B[3])]
                    rects.pop(b)
                    merged = True
                    break
            if merged:
                break
    mask = np.zeros_like(ink)
    pad = int(2 * k)
    H, W = ink.shape
    out = []
    for x0, y0, x1, y1 in rects:
        x0, y0 = max(x0 - pad, 0), max(y0 - pad, 0)
        x1, y1 = min(x1 + pad, W), min(y1 + pad, H)
        mask[y0:y1, x0:x1] = 255
        out.append((x0, y0, x1, y1))
    return out, mask & ink


def _stroke_ratio(region: np.ndarray, size_px: float) -> float | None:
    """Độ dày nét chữ ≈ 2·diện tích / chu vi, chia cho cỡ chữ (pixel)."""
    if region.size == 0 or size_px <= 0:
        return None
    area = int(np.count_nonzero(region))
    if area < 20:
        return None
    eroded = cv2.erode(region, np.ones((3, 3), np.uint8))
    border = area - int(np.count_nonzero(eroded))
    return 2 * area / border / size_px if border > 0 else None


# Times thường ~0.06 em, đậm ~0.08 em. Ảnh chụp mờ làm nét dày lên đều -> so với trung vị trang.
BOLD_RATIO = 0.071


def _mark_bold(lines: list["_Line"]):
    strokes = [wd.stroke for ln in lines for wd in ln.words
               if wd.stroke is not None and len(wd.text) >= 3]
    if not strokes:
        return
    threshold = max(BOLD_RATIO, statistics.median(strokes) * 1.2)
    for ln in lines:
        for wd in ln.words:
            wd.bold = wd.stroke is not None and wd.stroke > threshold
        if len(ln.words) >= 3:  # làm mượt: dòng phần lớn đậm -> đậm cả dòng
            ratio = sum(wd.bold for wd in ln.words) / len(ln.words)
            if ratio >= 0.6 or ratio <= 0.25:
                for wd in ln.words:
                    wd.bold = ratio >= 0.6


def _mean_color(pixels: np.ndarray) -> tuple[float, float, float]:
    if pixels.size == 0:
        return (0.0, 0.0, 0.0)
    c = np.median(pixels.reshape(-1, 3), axis=0) / 255.0
    if c.max() - c.min() < 0.15:  # gần xám -> đen
        return (0.0, 0.0, 0.0)
    return tuple(float(v) for v in c)


def _text_color(rgb: np.ndarray, ink: np.ndarray) -> tuple[float, float, float]:
    sel = ink > 0
    if not sel.any():
        return (0.0, 0.0, 0.0)
    pixels = rgb[sel]
    gray = pixels.mean(axis=1)
    darkest = pixels[gray <= np.percentile(gray, 40)]  # bỏ viền khử răng cưa
    return _mean_color(darkest)


def _text_tiles(clean: np.ndarray, k: float):
    """Tách mảnh dòng chữ: nối các ký tự gần nhau theo chiều ngang (khoảng cách từ),
    khoảng trống lớn (cột/ô khác) thành mảnh riêng. Trả về (bbox, ảnh nhãn, danh sách nhãn của từng mảnh)."""
    n, lab, st = _components(clean)
    hs = st[1:, cv2.CC_STAT_HEIGHT]
    ws = st[1:, cv2.CC_STAT_WIDTH]
    sel = (hs >= 1.5 * k) & (hs <= 40 * k) & (ws <= 40 * k)
    ch = float(np.median(hs[sel])) if sel.any() else 8 * k
    kw = max(int(ch * 1.1), int(3 * k))
    kh = max(int(ch * 0.45), 1)
    joined = cv2.dilate(clean, cv2.getStructuringElement(cv2.MORPH_RECT, (kw, kh)))
    n, labels, st = _components(joined)
    raw = [[[int(v) for v in (x, y, x + w, y + h)], [i]]
           for i, (x, y, w, h, _) in enumerate(st[1:].tolist(), 1)]
    _merge_marks(raw)
    line_h = statistics.median(r[0][3] - r[0][1] for r in raw) if raw else 0
    tiles, ids = [], []
    for (x0, y0, x1, y1), group in raw:
        if y1 - y0 > 2.5 * line_h and x1 - x0 < 0.6 * (y1 - y0):
            continue  # cao và hẹp: phần sót của đường kẻ dọc, không phải chữ
        own = np.isin(labels[y0:y1, x0:x1], group) & (clean[y0:y1, x0:x1] > 0)
        if np.count_nonzero(own) < 4 * k * k:
            continue  # nhiễu
        # mảnh nhiều dòng -> tách từng dòng để Tesseract không gộp/bỏ dòng
        for r0, r1 in _row_runs(own):
            part = own[r0:r1]
            ys, xs = np.nonzero(part)
            if len(ys) < 4 * k * k:
                continue
            tiles.append((x0 + int(xs.min()), y0 + r0 + int(ys.min()),
                          x0 + int(xs.max()) + 1, y0 + r0 + int(ys.max()) + 1))
            ids.append(group)
    order = sorted(range(len(tiles)), key=lambda j: (tiles[j][1], tiles[j][0]))
    return [tiles[j] for j in order], labels, [ids[j] for j in order]


def _row_runs(own: np.ndarray) -> list[tuple[int, int]]:
    """Chia mảnh theo các dải hàng có mực; dải mỏng (dấu thanh, dấu chấm dưới) gắn vào
    dải kề gần nhất. Trả về [(hàng đầu, hàng cuối)] của từng dòng chữ."""
    counts = own.sum(axis=1)
    rows = counts > max(counts.max() * 0.03, 0)  # hàng gần như trống (chỉ lẻ tẻ dấu) = khe
    runs, start = [], None
    for r, v in enumerate(rows):
        if v and start is None:
            start = r
        elif not v and start is not None:
            runs.append([start, r])
            start = None
    if start is not None:
        runs.append([start, len(rows)])
    if len(runs) <= 1:
        return [(0, own.shape[0])]
    while len(runs) > 1:
        tallest = max(e - b for b, e in runs)
        i = min(range(len(runs)), key=lambda j: runs[j][1] - runs[j][0])
        if runs[i][1] - runs[i][0] >= 0.45 * tallest:
            break
        # gắn vào dải kề có khe nhỏ hơn
        up = runs[i][0] - runs[i - 1][1] if i > 0 else None
        down = runs[i + 1][0] - runs[i][1] if i + 1 < len(runs) else None
        j = i - 1 if down is None or (up is not None and up <= down) else i + 1
        a, b = sorted((i, j))
        runs[a] = [runs[a][0], runs[b][1]]
        runs.pop(b)
    # chỉ cắt ở khe giữa hai dải đều cao như dòng chữ; trả về biên (giữa khe)
    cuts = [0] + [(runs[i][1] + runs[i + 1][0]) // 2 for i in range(len(runs) - 1)]
    cuts.append(own.shape[0])
    return [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]


def _merge_marks(raw: list[list]):
    """Dấu thanh của chữ cỡ lớn cách thân chữ xa hơn khe nối dọc -> thành mảnh riêng.
    Gộp mảnh nhỏ cỡ dấu thanh nằm sát ngay trên/dưới một mảnh dòng chữ vào mảnh đó."""
    if len(raw) < 2:
        return
    line_h = statistics.median(r[0][3] - r[0][1] for r in raw)
    raw.sort(key=lambda r: (r[0][3] - r[0][1]))
    i = 0
    while i < len(raw):
        (ax0, ay0, ax1, ay1), _ = raw[i]
        ah, aw = ay1 - ay0, ax1 - ax0
        target = None
        for j in range(len(raw) - 1, i, -1):
            (bx0, by0, bx1, by1), _ = raw[j]
            bh = by1 - by0
            if bh > 4 * line_h:
                continue  # khối lớn (sót khung bảng, hình) không phải dòng chữ
            if ah >= 0.35 * bh:
                break  # các mảnh còn lại (sắp theo chiều cao) đều không đủ cao
            gap = max(by0 - ay1, ay0 - by1)
            overlap = min(ax1, bx1) - max(ax0, bx0)
            if aw <= bh and gap < 0.35 * bh and overlap > 0.5 * aw:
                target = j
                break
        if target is None:
            i += 1
            continue
        box, group = raw[target]
        box[:] = [min(box[0], ax0), min(box[1], ay0), max(box[2], ax1), max(box[3], ay1)]
        group.extend(raw[i][1])
        raw.pop(i)


def _fit_islands(cum: np.ndarray, islands: list[tuple[int, int]]):
    """Chia chuỗi ký tự (độ rộng luỹ kế `cum`, đơn vị pixel) vào các cụm mực theo thứ tự,
    mỗi cụm >= 1 ký tự, tối thiểu tổng sai lệch độ rộng. Trả về (chi phí, [(đầu, cuối)])."""
    n, m = len(cum) - 1, len(islands)
    inf = float("inf")
    if m > n:
        return inf, []
    cost = [[inf] * (n + 1) for _ in range(m + 1)]
    back = [[0] * (n + 1) for _ in range(m + 1)]
    cost[0][0] = 0.0
    for j in range(1, m + 1):
        iw = islands[j - 1][1] - islands[j - 1][0]
        for i in range(j, n - (m - j) + 1):
            for p in range(j - 1, i):
                c = cost[j - 1][p] + abs((cum[i] - cum[p]) - iw)
                if c < cost[j][i]:
                    cost[j][i], back[j][i] = c, p
    cuts, i = [], n
    for j in range(m, 0, -1):
        cuts.append((back[j][i], i))
        i = back[j][i]
    cuts.reverse()
    return cost[m][n], cuts


def _group_rows(tiles: list[tuple[int, int, int, int]]) -> list[list[int]]:
    """Gom các mảnh cùng hàng (chồng lấn dọc > 50% mảnh thấp hơn), sắp theo x."""
    rows: list[list[int]] = []
    spans: list[list[int]] = []
    for t in sorted(range(len(tiles)), key=lambda j: tiles[j][1]):
        x0, y0, x1, y1 = tiles[t]
        for row, sp in zip(rows, spans):
            ov = min(y1, sp[1]) - max(y0, sp[0])
            if ov > 0.5 * min(y1 - y0, sp[1] - sp[0]):
                row.append(t)
                sp[0], sp[1] = min(sp[0], y0), max(sp[1], y1)
                break
        else:
            rows.append([t])
            spans.append([y0, y1])
    for row in rows:
        row.sort(key=lambda j: tiles[j][0])
    return rows


def _tile_at(row: list[int], place, tiles, cx: float, gap: int) -> int | None:
    for t in row:
        left = place[t][0]
        w = tiles[t][2] - tiles[t][0]
        if left - gap / 2 <= cx <= left + w + gap / 2:
            return t
    return None


def _line_bands(own: np.ndarray, n: int) -> list[tuple[int, int, int]]:
    """Chia mảnh thành n dòng theo khe trống ngang; trả về (top, bottom, baseline) mỗi dòng."""
    rows = own.sum(axis=1)
    runs, start = [], None
    for r, v in enumerate(rows):
        if v and start is None:
            start = r
        elif not v and start is not None:
            runs.append([start, r])
            start = None
    if start is not None:
        runs.append([start, len(rows)])
    if not runs:
        return [(0, own.shape[0], own.shape[0])] * n
    # gộp khe nhỏ nhất (dấu thanh tách khỏi thân chữ) cho tới khi còn n dòng
    while len(runs) > n:
        gaps = [runs[i + 1][0] - runs[i][1] for i in range(len(runs) - 1)]
        i = int(np.argmin(gaps))
        runs[i] = [runs[i][0], runs[i + 1][1]]
        runs.pop(i + 1)
    if len(runs) < n:
        h = own.shape[0]
        runs = [[h * j // n, h * (j + 1) // n] for j in range(n)]
    bands = []
    for top, bottom in runs:
        seg = rows[top:bottom]
        m = seg.max() if seg.size else 0
        dense = np.nonzero(seg >= 0.35 * m)[0] if m else []
        base = top + int(dense[-1]) + 1 if len(dense) else bottom
        bands.append((top, bottom, base))
    return bands


def _snap_sizes(lines: list["_Line"]):
    """Đưa cỡ chữ gần nhau về cùng một cỡ phổ biến (văn bản thường chỉ dùng vài cỡ)."""
    rounded = [round(ln.size * 2) / 2 for ln in lines]
    freq: dict[float, int] = {}
    for r, ln in zip(rounded, lines):
        if not ln.weak:
            freq[r] = freq.get(r, 0) + 1
    common = sorted((s for s, c in freq.items() if c >= 3), key=lambda s: -freq[s])
    for ln, r in zip(lines, rounded):
        snap = r
        tol = 0.4 if ln.weak else 0.12
        near = [s for s in common if abs(s - ln.size) <= tol * s]
        if near:
            snap = near[0] if not ln.weak else min(near, key=lambda s: abs(s - ln.size))
        ln.size = snap or 10.0


# --------------------------------------------------------------------------- tách từ


def _split_words(chars: list[dict]) -> list[_Word]:
    """MuPDF làm mất dấu cách sau chữ có dấu tiếng Việt -> tự tách từ theo khoảng hở."""
    words: list[_Word] = []
    cur, x0, x1 = "", 0.0, 0.0
    for c in chars:
        ch = c["c"]
        bx0, bx1 = c["bbox"][0], c["bbox"][2]
        if unicodedata.combining(ch):  # dấu kết hợp rời (NFD) -> gắn vào ký tự trước
            if cur:
                cur += ch
            continue
        if ch.isspace():
            if cur:
                words.append(_Word(unicodedata.normalize("NFC", cur), x0, x1))
            cur = ""
            continue
        if cur and bx0 - x1 > 0.3:
            words.append(_Word(unicodedata.normalize("NFC", cur), x0, x1))
            cur = ""
        if not cur:
            x0 = bx0
        cur += ch
        x1 = bx1
    if cur:
        words.append(_Word(unicodedata.normalize("NFC", cur), x0, x1))
    return words


_STRAY = set("`´^~¨˜ˆ'\"‘’“”|")


def _is_stray(wd: _Word) -> bool:
    """Ký tự lẻ do Tesseract tách nhầm dấu thanh (ví dụ "`") hoặc từ rộng 0."""
    return all(ch in _STRAY for ch in wd.text) or wd.x1 - wd.x0 < 0.3


def _segments(words: list[_Word], size: float) -> list[list[_Word]]:
    """Nhóm các từ sát nhau thành cụm; khoảng hở lớn (cột khác, ô khác) tách cụm riêng."""
    groups: list[list[_Word]] = []
    for wd in words:
        if groups and wd.x0 - groups[-1][-1].x1 < size * 1.2:
            groups[-1].append(wd)
        else:
            groups.append([wd])
    return groups
