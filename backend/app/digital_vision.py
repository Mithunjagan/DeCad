"""Recognition of printed digital schematics (ICs, gates, buses, connector pins) from scans.

Pipeline: clean/deskew/binarize -> split wires from text -> word-level OCR (both orientations)
-> wire segments + junction dots -> symbols (IC boxes, gate clusters) -> pins (wire ends with a
pin number) -> nets (wire connectivity, net labels, connector pins) -> pinout check against the
installed OrCAD part libraries. Every uncertain decision is reported as a warning for review.
"""
from __future__ import annotations
import math, re
from collections import Counter
from dataclasses import dataclass, field
import cv2
import numpy as np

_OCR = None


_GPU = None


def use_gpu():
    """True when onnxruntime-gpu and the CUDA 12 / cuDNN 9 libraries are present (S2SDN_OCR_DEVICE=cpu
    turns it off). PyTorch's CUDA build ships those libraries; its folder is added when installed."""
    global _GPU
    if _GPU is None:
        import importlib.util, os
        _GPU = False
        try:
            import onnxruntime as ort
            if os.getenv('S2SDN_OCR_DEVICE', 'auto').lower() != 'cpu' and 'CUDAExecutionProvider' in ort.get_available_providers():
                spec = importlib.util.find_spec('torch')
                libs = [os.getenv('S2SDN_CUDA_DLLS', '')]          # e.g. another Python's torch\lib
                if spec and spec.submodule_search_locations:
                    libs.append(os.path.join(list(spec.submodule_search_locations)[0], 'lib'))
                for lib in libs:
                    if lib and os.path.isdir(lib) and hasattr(os, 'add_dll_directory'):
                        os.add_dll_directory(lib)
                if hasattr(ort, 'preload_dlls'):
                    ort.preload_dlls()
                _GPU = True
        except Exception:
            _GPU = False
    return _GPU


CUDA_OPTIONS = {'device_id': 0, 'arena_extend_strategy': 'kSameAsRequested', 'cudnn_conv_algo_search': 'HEURISTIC',
                'gpu_mem_limit': 1536 * 2**20, 'do_copy_in_default_stream': True}


def ocr_engine():
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        gpu = use_gpu()
        _OCR = RapidOCR(det_use_cuda=gpu, cls_use_cuda=gpu, rec_use_cuda=gpu)
        if gpu:
            # RapidOCR asks CUDA for an exhaustive convolution search, repeated for every new tile shape,
            # with power-of-two arena growth: gigabytes of scratch on a 4 GB laptop GPU. Lean sessions instead.
            import onnxruntime as ort
            for holder in (getattr(_OCR.text_det, 'infer', None), getattr(_OCR.text_cls, 'infer', None),
                           getattr(_OCR.text_rec, 'session', None)):
                old = getattr(holder, 'session', None)
                if old is not None:
                    holder.session = ort.InferenceSession(old._model_path, sess_options=old.get_session_options(),
                                                          providers=[('CUDAExecutionProvider', CUDA_OPTIONS), 'CPUExecutionProvider'])
    return _OCR


@dataclass
class Token:
    text: str
    conf: float
    x0: int; y0: int; x1: int; y1: int
    vertical: bool = False

    @property
    def cx(self): return (self.x0 + self.x1) / 2

    @property
    def cy(self): return (self.y0 + self.y1) / 2

    @property
    def h(self): return (self.x1 - self.x0) if self.vertical else (self.y1 - self.y0)


@dataclass
class Page:
    gray: np.ndarray
    binary: np.ndarray          # ink = 255
    hlines: np.ndarray
    vlines: np.ndarray
    text: np.ndarray            # ink = 255, wires removed
    scale: float = 1.0          # page pixels per source pixel
    notes: list = field(default_factory=list)
    soft: np.ndarray = None     # low-resolution input only: smoothed grayscale text (dark on white, wires removed) for OCR
    affine: np.ndarray = None   # source raster -> working pixels, including deskew
    vector: object = None      # native PDF primitives, in working pixels
    measurements: dict = field(default_factory=dict)


# ---------------------------------------------------------------- preprocessing

def load(path, notes):
    """Grayscale page at a working resolution where printed characters are ~40 px tall."""
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError('Unreadable image file.')
    return gray


def _banded_stats(mask, band=2048, overlap=256):
    """Stats (x, y, w, h, area, cx, cy) of components no taller than `overlap` (any width), computed in overlapping row
    bands so a large sheet never needs one whole-page label image. Each component is counted once, in the
    band where its top edge lies, so the result equals a whole-page pass for components of that size."""
    H = mask.shape[0]
    out = []
    for y0 in range(0, H, band - overlap):
        y1 = min(H, y0 + band)
        _, _, stats, cent = cv2.connectedComponentsWithStats(mask[y0:y1], 8)
        for (x, y, w, h, area), (cx, cy) in zip(stats[1:], cent[1:]):
            top_ok = y <= band - overlap or y1 == H
            if (y > 0 or y0 == 0) and (y + h < y1 - y0 or y1 == H) and top_ok:
                out.append((int(x), int(y) + y0, int(w), int(h), int(area), float(cx), float(cy) + y0))
        if y1 == H:
            break
    return out


def char_height(binary, robust=True):
    """Median height of character-sized connected components."""
    stats = _banded_stats(binary)
    hs = np.array([s[3] for s in stats if 6 <= s[3] <= 200 and 2 <= s[2] <= 150 and s[4] > 12 and s[3] >= s[2] * 0.8])
    if len(hs) <= 30:
        return 0.0
    # Dense buses leave many small specks after wire removal; characters are the tall cluster.
    if robust:
        hs = hs[hs >= 0.5 * np.percentile(hs, 90)]
    return float(np.median(hs)) if len(hs) > 30 else 0.0


def binarize(gray):
    g = cv2.medianBlur(gray, 3)
    _, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # Scans with uneven lighting: fall back to local thresholding when Otsu floods the page.
    if b.mean() > 255 * 0.25:
        b = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 15)
    return b


def binarize_lowres(gray, level=0.8):
    """Binarize an upscaled low-resolution or blurred sheet. Its glyph strokes are gray ramps, so Otsu
    and median filtering erase them; keep everything clearly darker than the paper instead. Tiny
    sheets have faint thin strokes (level 0.8); blurred scans have broad halos that would merge
    glyphs, so they cut nearer the middle (level 0.68)."""
    paper = float(np.percentile(gray, 90))
    return np.where(gray < min(255.0 * level - 4, level * paper), 255, 0).astype(np.uint8)


def deskew_angle(binary):
    f = min(1.0, 2500 / binary.shape[1])
    small = cv2.resize(binary, None, fx=f, fy=f, interpolation=cv2.INTER_AREA) if f < 1 else binary
    lines = cv2.HoughLinesP(small, 1, np.pi / 1800, threshold=150, minLineLength=small.shape[1] // 15, maxLineGap=3)
    if lines is None:
        return 0.0
    angles = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        a = math.degrees(math.atan2(y2 - y1, x2 - x1))
        a = (a + 45) % 90 - 45          # fold vertical lines onto horizontal
        if abs(a) < 5:
            angles.append(a)
    return float(np.median(angles)) if angles else 0.0


def soft_edge_ratio(gray):
    """Share of inked pixels that are mid-gray. Plotter scans saved as 1-bit images are ~0; blurred,
    low-dpi or JPEG-compressed scans and photos are 0.5+ (their strokes are gray ramps)."""
    ink = int((gray < 230).sum())
    return float(((gray > 60) & (gray < 200)).sum()) / ink if ink else 0.0


def prepare(path):
    notes = []
    gray = load(path, notes)
    b = binarize(gray)
    ch = char_height(b)
    initial_affine=np.array([[1.,0.,0.],[0.,1.,0.]])
    measurements={}
    from .pipeline_profile import enabled
    if enabled():
        from .normalization import normalize
        gray,initial_affine,normal_notes,measurements=normalize(gray,b,ch)
        notes+=normal_notes
        # Mixed horizontal/vertical captions are common. Preserve page geometry;
        # additional OCR orientations are selected on text crops instead.
        if normal_notes:
            b=binarize(gray);ch=char_height(b)
    scale, lowres = 1.0, False
    soft_edges = soft_edge_ratio(gray)
    # Blurry or low-resolution scans: upscale so characters are ~40 px before OCR and tracing.
    long_side = max(gray.shape)
    if long_side < 6000 and char_height(b, robust=False) < 20:
        lowres = True
        # A whole drawing sheet saved as a small JPEG: its characters are a few pixels tall, below
        # what can be measured. Scale toward a normal ~10k px sheet scan (at most 8x).
        scale = min(8.0, 10000.0 / long_side, math.sqrt(120e6 / (gray.shape[0] * gray.shape[1])))
    elif 0 < ch < 26:
        scale = min(2.0, 40.0 / ch)
    # Blurred/greyscale scans take the same stroke-preserving route as tiny sheets: Otsu plus median
    # filtering breaks their soft glyph strokes apart.
    soft_mode = lowres or soft_edges > 0.3
    binarizer = (lambda g: binarize_lowres(g, 0.8 if lowres else 0.68)) if soft_mode else binarize
    if scale > 1.0:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        if soft_mode:                     # smooth JPEG blocks / sensor noise into solid strokes
            gray = cv2.GaussianBlur(gray, (0, 0), max(0.6, 0.2 * scale))
        else:
            gray = cv2.addWeighted(gray, 1.6, cv2.GaussianBlur(gray, (0, 0), 2.0), -0.6, 0)   # unsharp mask
    elif soft_mode:
        gray = cv2.GaussianBlur(gray, (0, 0), 0.6)
    if scale > 1.0 or soft_mode:
        b = binarizer(gray)
    if lowres:
        notes.append(f'Input assessment: low-resolution/blurry sheet ({long_side} px, text a few px tall); enhanced automatically '
                     f'({scale:.1f}x super-sampling, stroke-preserving binarization, grayscale OCR).')
    elif soft_mode:
        notes.append(f'Input assessment: blurred or greyscale scan ({soft_edges:.0%} soft stroke edges, text ~{ch:.0f} px); enhanced '
                     f'automatically ({scale:.1f}x resampling, stroke-preserving binarization, grayscale OCR).')
    elif scale > 1.0:
        notes.append(f'Input assessment: scan with small text (~{ch:.0f} px); upscaled {scale:.1f}x automatically.')
    affine = np.array([[scale, 0., 0.], [0., scale, 0.]])
    affine=(np.vstack((affine,[0,0,1])) @ np.vstack((initial_affine,[0,0,1])))[:2]
    angle = deskew_angle(b)
    if abs(angle) > 0.15:
        h, w = gray.shape
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        affine = (np.vstack((m, [0.,0.,1.])) @ np.vstack((affine, [0.,0.,1.])))[:2]
        gray = cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)
        b = binarizer(gray)
        notes.append(f'Scan deskewed by {angle:.2f} degrees.')
    ch = char_height(b) or 40.0
    run = max(int(ch * 1.6), 30)          # a wire is a straight run longer than any glyph stroke
    hl = cv2.morphologyEx(b, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (run, 1)))
    vl = cv2.morphologyEx(b, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, run)))
    lines = cv2.dilate(cv2.bitwise_or(hl, vl), np.ones((3, 3), np.uint8))
    text = cv2.bitwise_and(b, cv2.bitwise_not(lines))
    text = cv2.morphologyEx(text, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))   # drop specks left by wire edges
    soft = np.where(lines > 0, 255, gray).astype(np.uint8) if soft_mode else None
    if lowres or soft_mode:
        notes.append('Review required: detail lost to blur or a scan below 300 dpi cannot be recovered by any reader. '
                     'Check every part, pin number and net label against the source, or rescan at 300 dpi or better.')
    if not notes:
        notes.append(f'Input assessment: clear scan ({long_side} px, text ~{ch:.0f} px); no enhancement needed.')
    return Page(gray=gray, binary=b, hlines=hl, vlines=vl, text=text, scale=scale, notes=notes, soft=soft, affine=affine, measurements=measurements)


# ---------------------------------------------------------------- word-level OCR

def _runs(mask, axis, gap):
    """Ink runs along one axis (axis=0: along x, 1: along y) separated by gaps wider than `gap`."""
    profile = (mask > 0).sum(axis=0) if axis == 0 else (mask > 0).sum(axis=1)
    ink = np.where(profile > 0)[0]
    if ink.size == 0:
        return []
    runs, start, last = [], ink[0], ink[0]
    for i in ink[1:]:
        if i - last > gap:
            runs.append((start, last + 1)); start = i
        last = i
    runs.append((start, last + 1))
    return runs


def _words(mask, ch):
    """Rows of horizontal words in a detected text box, as (x0, y0, x1, y1) relative to the mask."""
    word_gap, line_gap = max(5, int(ch * 0.72)), max(2, int(ch * 0.25))
    return [(x0, y0, x1, y1)
            for y0, y1 in _runs(mask, 1, line_gap)
            for x0, x1 in _runs(mask[y0:y1], 0, word_gap)]


def _pass(layer, ch, tile, overlap, soft=None):
    """Detect text lines on one orientation of the wire-free layer and read each word."""
    engine = ocr_engine()
    img = 255 - layer
    H, W = img.shape
    det_scale = min(1.0, 22.0 / ch)       # detector works best with ~20 px glyphs
    small = cv2.resize(img, None, fx=det_scale, fy=det_scale, interpolation=cv2.INTER_AREA) if det_scale < 1 else img
    boxes = []
    st, so = int(tile * det_scale) or tile, int(overlap * det_scale)
    for y in range(0, small.shape[0], st - so):
        for x in range(0, small.shape[1], st - so):
            t = small[y:y + st, x:x + st]
            if (t < 128).sum() < 30:
                continue
            res, _ = engine(cv2.cvtColor(t, cv2.COLOR_GRAY2BGR), use_cls=False, use_rec=False)
            for box in res or []:
                b = (np.array(box) + [x, y]) / det_scale
                boxes.append((int(b[:, 0].min()), int(b[:, 1].min()), int(b[:, 0].max()), int(b[:, 1].max())))
    out = []
    for x0, y0, x1, y1 in _dedupe(boxes):
        x0, y0, x1, y1 = max(0, x0 - 2), max(0, y0 - 2), min(W, x1 + 2), min(H, y1 + 2)
        mask = layer[y0:y1, x0:x1]
        if mask.size == 0 or mask.max() == 0 or (y1 - y0) > 2.6 * ch and (x1 - x0) < 2.6 * ch:
            continue                      # tall narrow box: text of the other orientation
        for a, b, c, d in _words(mask, ch):
            w = _read(engine, layer, x0 + a, y0 + b, x0 + c, y0 + d, soft)
            if w:
                out.append(w)
    return out


def tokens(page, tile=2400, overlap=200):
    """Word tokens in page coordinates from two passes: as printed, and rotated 90 degrees for
    vertical text. Where readings overlap, the more confident one wins."""
    if page.vector is not None and page.vector.text:
        from .vector_pdf import tokens as vector_tokens
        return vector_tokens(page.vector)
    from .pipeline_profile import enabled, profile
    from concurrent.futures import ThreadPoolExecutor
    ch = char_height(page.text) or 40.0
    H, W = page.text.shape
    rotated = cv2.rotate(page.text, cv2.ROTATE_90_CLOCKWISE)        # bottom-to-top text becomes upright
    softs = [page.soft, cv2.rotate(page.soft, cv2.ROTATE_90_CLOCKWISE)] if page.soft is not None else [None, None]
    with ThreadPoolExecutor(1 if use_gpu() else 2) as pool:      # one GPU: the passes take turns
        flat, turned = pool.map(lambda la: _pass(la[0], ch, tile, overlap, la[1]), [(page.text, softs[0]), (rotated, softs[1])])
    for t in turned:                      # rotated (x', y') -> page (y', H-1-x')
        t.x0, t.y0, t.x1, t.y1 = t.y0, H - t.x1, t.y1, H - t.x0
        t.vertical = True
    if enabled() and not any(t.conf>=.92 and REF_RE.fullmatch(t.text.upper()) for t in flat+turned):
        # Recognition of upside-down sources must not rotate a mixed-orientation
        # sheet and perturb wire geometry. Read the remaining two text views.
        extra=[]
        tile=profile()['tile_size'];overlap=round(tile*profile()['tile_overlap'])
        for turn in (0,2,1,3):
            layer=np.ascontiguousarray(np.rot90(page.text,turn))
            soft=np.ascontiguousarray(np.rot90(page.soft,turn)) if page.soft is not None else None
            reads=_pass(layer,ch,tile,overlap,soft)
            for t in reads:
                if turn==2:t.x0,t.y0,t.x1,t.y1=W-t.x1,H-t.y1,W-t.x0,H-t.y0
                elif turn==1:
                    t.x0,t.y0,t.x1,t.y1=W-t.y1,t.x0,W-t.y0,t.x1
                    t.vertical=True
                elif turn==3:
                    t.x0,t.y0,t.x1,t.y1=t.y0,H-t.x1,t.y1,H-t.x0
                    t.vertical=True
            extra+=reads
        if sum(t.conf>=.92 and REF_RE.fullmatch(t.text.upper()) is not None for t in extra)>=3:
            flat+=extra
            page.notes.append('Inverted text views recovered multiple confident references; wire coordinates were preserved.')
    merged = []
    for t in sorted(flat + turned, key=lambda t: t.conf * len(t.text), reverse=True):
        area = (t.x1 - t.x0) * (t.y1 - t.y0)
        if any(_overlap((t.x0, t.y0, t.x1, t.y1), (k.x0, k.y0, k.x1, k.y1)) > 0.4 * area for k in merged):
            continue
        merged.append(t)
    if page.soft is not None:
        for t in merged:
            t.text = lowres_text(t.text)
        snap_part_numbers(merged)
    return merged


LOWRES_DIGITS = str.maketrans({'O': '0', 'D': '0', 'Q': '0', 'C': '0', 'I': '1', 'L': '1', 'T': '7', 'P': '7', 'Z': '2',
                               'S': '5', 'B': '8', 'G': '6', 'A': '4', 'Y': '7', 'R': '7', 'E': '6'})


def lowres_text(text):
    """Character confusions typical of 4-6 px plotter text, repaired only where the token shape is
    unambiguous: a U reference ("UPO" -> U70), a 74-series number ("7AF244" -> 74F244) or a TC memory."""
    u = text.upper()
    m = re.fullmatch(r'U([0-9A-Z]{1,3})', u) or re.fullmatch(r'V(\d{2,3})', u)    # V43: a U with a faint bottom stroke
    if m and not REF_RE.match(u):
        d = m.group(1).translate(LOWRES_DIGITS)
        if d.isdigit():
            return 'U' + d
    # 74-series: the family letter between "74" and the 3-digit type blurs into 7/5/1; the type
    # digits are kept exactly as read (a wrong 74F240/74F244 swap is worse than an unknown part).
    m = re.fullmatch(r'[7RP][A41]([F751EP])(\d{3})', u)
    if m and u[2] != 'F' or m and u[:2] != '74':
        return '74F' + m.group(2)
    m = re.fullmatch(r'[7RP][A4]([A-Z]{0,3}?)([0-9A-Z]{2,4})', u)
    if m and not PART_RE.match(u) and sum(c.isdigit() for c in m.group(2)) >= 2:
        return '74' + m.group(1) + m.group(2).translate(LOWRES_DIGITS)
    m = re.fullmatch(r'T[CG0O]([0-9A-Z]{5,7})', u)
    if m and sum(c.isdigit() for c in m.group(1)) >= 3:
        return 'TC' + m.group(1).translate(LOWRES_DIGITS)
    return text


def snap_part_numbers(toks):
    """Low-resolution sheets: a part number read cleanly somewhere on the sheet ("TC514100", 0.87)
    corrects its blurred copies elsewhere ("1C514100", "T3314100", "rG514100"): same length, most
    characters in place, and the digits that differ are recorded as a correction, not invented."""
    vocab = {t.text.upper() for t in toks if t.conf >= 0.7 and PART_RE.match(t.text.upper())
             and re.search(r'[A-Z]{2}', t.text.upper()) and len(t.text) >= 7 and not t.text.upper().startswith('74')}
    if not vocab:
        return
    for t in toks:
        u = t.text.upper()
        if u in vocab or len(u) < 7 or u.startswith('74'):
            continue
        best = min(vocab, key=lambda v: (len(v) != len(u), sum(a != b for a, b in zip(u, v))))
        if len(best) == len(u):
            diff = sum(a != b for a, b in zip(u, best))
            tail = sum(a == b for a, b in zip(u[-4:], best[-4:]))
            if diff <= max(2, len(u) // 3 + (1 if tail >= 3 else 0)) and diff < len(u) // 2:
                t.text = best


def _read(engine, layer, x0, y0, x1, y1, soft=None):
    sub = layer[y0:y1, x0:x1]
    ys, xs = np.nonzero(sub)
    if ys.size < 8:
        return None
    x0, x1, y0, y1 = x0 + xs.min(), x0 + xs.max() + 1, y0 + ys.min(), y0 + ys.max() + 1
    crop = cv2.copyMakeBorder(_reading_crop(layer, soft, x0, y0, x1, y1), 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)
    r, _ = engine(cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR), use_det=False, use_cls=False)
    if not r:
        return None
    text = clean_text(str(r[0][0]))
    return Token(text, float(r[0][1]), int(x0), int(y0), int(x1), int(y1)) if text else None


def _reading_crop(layer, soft, x0, y0, x1, y1):
    """Crop handed to the OCR reader: the binary text layer, or for low-resolution input the
    smoothed grayscale (padded by a pixel band so anti-aliased glyph edges survive)."""
    if soft is None:
        return 255 - layer[y0:y1, x0:x1]
    p = 3
    return soft[max(0, y0 - p):y1 + p, max(0, x0 - p):x1 + p]


def _cells(mask, axis, ch):
    """Glyph cells along the reading axis: ink runs, with scan dropouts inside one glyph re-joined."""
    runs = _runs(mask, axis, 1)
    merged = []
    for r in runs:
        gap = r[0] - merged[-1][1] if merged else 0
        # a narrow run is a glyph fragment only when it is close; further out it is something else
        # (a sliver of the body outline beside a pin number: "6" + edge -> "61")
        if merged and (gap <= max(2, ch * 0.08) or r[1] - r[0] < ch * 0.12 and gap <= 0.3 * ch):
            merged[-1] = (merged[-1][0], r[1])
        else:
            merged.append(r)
    return merged


def _ocr_box(page, x0, y0, x1, y1, rotate):
    engine = ocr_engine()
    crop = page.text[y0:y1, x0:x1]
    ys, xs = np.nonzero(crop)
    if ys.size < 8:
        return None
    x0, x1, y0, y1 = x0 + xs.min(), x0 + xs.max() + 1, y0 + ys.min(), y0 + ys.max() + 1
    img = cv2.copyMakeBorder(_reading_crop(page.text, page.soft, x0, y0, x1, y1), 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)
    if rotate:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    r, _ = engine(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), use_det=False, use_cls=False)
    text = clean_text(str(r[0][0])) if r else ''
    return Token(text, float(r[0][1]), int(x0), int(y0), int(x1), int(y1), rotate) if text else None


def refine_tokens(page, toks, ch):
    """Repair two systematic OCR groupings on printed schematics:
    - a column of horizontal pin numbers stacked beside an IC, read by the rotated pass as one
      vertical "word" ("675914"): split it into rows and read each row upright;
    - a net label and its pin number printed one space apart ("12 CC12" -> "12CC12"): the plotter
      font is monospaced, so a space is a double step between glyph centres; split there."""
    out = []
    for t in toks:
        sub = page.text[t.y0:t.y1, t.x0:t.x1]
        if sub.size == 0:
            out.append(t); continue
        if t.vertical and (t.x1 - t.x0) <= 2.2 * ch:
            rows = _runs(sub, 1, max(2, int(ch * 0.15)))
            full = [r for r in rows if 0.8 * ch <= r[1] - r[0] <= 1.45 * ch]
            if len(rows) >= 3 and len(full) >= 0.8 * len(rows):
                pieces = [_ocr_box(page, t.x0, t.y0 + a, t.x1, t.y0 + b, False) for a, b in rows]
                pieces = [p for p in pieces if p and as_number(p.text)]
                if len(pieces) >= max(2, 0.6 * len(rows)):
                    out.extend(pieces); continue
        text = t.text.upper()
        lead = re.match(r'^(\d{1,3})[.\-_,:]?([A-Z][A-Z0-9]{1,8})$', text)        # "13CC11": pin 13, label CC11
        tail = re.match(r'^([A-Z][A-Z0-9]{1,8}?)[.\-_,:]?(\d{1,2})$', text)       # "DD167": label DD16, pin 7
        fused = re.fullmatch(r'\d{4,7}', text) and not REF_RE.match(text)          # "88463": BB4 63, letters read as digits
        if fused:
            axis = 1 if t.vertical else 0
            cells = [c for c in _cells(sub, axis, ch) if c[1] - c[0] >= 0.2 * ch]
            if t.vertical:
                cells = cells[::-1]
            if len(cells) >= 4:
                centres = [(a + b) / 2 for a, b in cells]
                steps = [abs(c2 - c1) for c1, c2 in zip(centres, centres[1:])]
                pitch = float(np.median(steps))
                k = int(np.argmax(steps))
                if steps[k] >= 1.5 * pitch and sorted(steps)[-2] < 1.25 * pitch and pitch >= 0.4 * ch:
                    span = lambda cs: (min(c[0] for c in cs), max(c[1] for c in cs))
                    (a0, a1), (b0, b1) = span(cells[:k + 1]), span(cells[k + 1:])
                    if t.vertical:
                        first = _ocr_box(page, t.x0, t.y0 + a0, t.x1, t.y0 + a1, True)
                        second = _ocr_box(page, t.x0, t.y0 + b0, t.x1, t.y0 + b1, True)
                    else:
                        first = _ocr_box(page, t.x0 + a0, t.y0, t.x0 + a1, t.y1, False)
                        second = _ocr_box(page, t.x0 + b0, t.y0, t.x0 + b1, t.y1, False)
                    if first and second and bool(as_number(first.text)) != bool(as_number(second.text)):
                        out.extend([first, second]); continue
        if lead or tail:
            axis = 1 if t.vertical else 0
            cells = [c for c in _cells(sub, axis, ch) if c[1] - c[0] >= 0.2 * ch]
            if t.vertical:
                cells = cells[::-1]                                  # rotated text reads upward
            if len(cells) >= 3:
                centres = [(a + b) / 2 for a, b in cells]
                steps = [abs(c2 - c1) for c1, c2 in zip(centres, centres[1:])]
                pitch = float(np.median(steps))
                if lead:
                    k = min(len(lead.group(1)), len(cells) - 1) - 1            # boundary after the leading digits
                    ok = steps[k] >= 1.25 * pitch
                else:
                    k = len(cells) - 1 - min(len(tail.group(2)), len(cells) - 1) # boundary before the trailing pin
                    ok = steps[k] >= 1.35 * pitch and steps[k] == max(steps)
                if ok and pitch >= 0.4 * ch:
                    span = lambda cs: (min(c[0] for c in cs), max(c[1] for c in cs))
                    (a0, a1), (b0, b1) = span(cells[:k + 1]), span(cells[k + 1:])
                    if t.vertical:
                        first = _ocr_box(page, t.x0, t.y0 + a0, t.x1, t.y0 + a1, True)
                        second = _ocr_box(page, t.x0, t.y0 + b0, t.x1, t.y0 + b1, True)
                    else:
                        first = _ocr_box(page, t.x0 + a0, t.y0, t.x0 + a1, t.y1, False)
                        second = _ocr_box(page, t.x0 + b0, t.y0, t.x0 + b1, t.y1, False)
                    if first and second and bool(as_number(first.text)) != bool(as_number(second.text)):
                        out.extend([first, second]); continue
        out.append(t)
    return out


CONFUSABLE_TEXT = str.maketrans({'O': '0', 'I': '1', 'L': '1', 'S': '5', 'B': '8', 'Z': '2', 'G': '6', 'Q': '0', 'D': '0'})


def _dedupe(boxes):
    boxes = sorted(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
    kept = []
    for b in boxes:
        area = (b[2] - b[0]) * (b[3] - b[1])
        if any(_overlap(b, k) > 0.6 * area for k in kept):
            continue
        kept.append(b)
    return kept


def _overlap(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0]); h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0


CONFUSABLE = str.maketrans({'!': '1', '|': '1', 'O': '0', 'o': '0', 'I': '1', 'l': '1', 'i': '1', 't': '1', 'T': '7', 'S': '5', 's': '5', 'B': '8', 'Z': '2', 'z': '2', 'G': '6', 'g': '9', 'q': '9', 'D': '0'})


def clean_text(t):
    t = re.sub(r'[^A-Za-z0-9_\-+\[\]:./()<>=*#~!]', '', t or '')
    return t.strip('.:-')


def as_number(text):
    """Pin numbers are 1-3 digits; repair common OCR letter/digit confusions."""
    # Translate look-alike letters only in short readings with at most one letter ("1O" -> 10,
    # "I3" -> 13); "BB4" or "DD9" are net labels, not pins 884 / 009.
    t = text.translate(CONFUSABLE) if len(text) <= 3 and sum(c.isalpha() for c in text) <= 1 else text
    return t if re.fullmatch(r'\d{1,3}', t) and int(t) > 0 else None


# ---------------------------------------------------------------- wires, dots, boxes

REF_RE = re.compile(r'^(U|IC|R|C|L|D|Q|J|P|S|SW|Y|X|RN|TP)\d{1,3}[A-H]?$')
PART_RE = re.compile(r'^(74[A-Z]{0,4}\d{2,4}[A-Z]?|IDT\w+|AM\d{3,5}\w*|TC\d{4,}\w*|HM\d{4,}\w*|MC\d{3,}\w*|\d+[KMR]\d+|\d+(?:\.\d+)?[KMR]?)$')
PASSIVE = {'R': 'Device:R', 'C': 'Device:C', 'L': 'Device:L', 'D': 'Device:D'}
# Net labels on printed schematics: letters, an optional index, an optional suffix letter or bus range.
LABEL_RE = re.compile(r'^[-~/+]?[A-Z][A-Z_]{0,9}\d{0,3}[A-Z]?(\[\d+[:.]\d+\])?$|^[A-Z0-9]{1,4}[-_/][A-Z0-9]{1,8}$|^\+\d+V$')
PIN_DEBUG = []                              # (ref, x, y, pin, label) per IC pin read; diagnostics only
IC_VALUE_RE = re.compile(r'^(74|54|IDT|AM|TC|HM|MC|\d{5})')
CONN_RE = re.compile(r'(?<![A-Z0-9])([PJ]\d{1,2})[-_.=]?([A-D]\d{1,2}|\d{1,3})(?![0-9])')


@dataclass
class Seg:
    x0: int; y0: int; x1: int; y1: int
    thick: float
    horizontal: bool
    bus: bool = False

    def ends(self):
        return ((self.x0, self.y0), (self.x1, self.y1))

    def dist(self, x, y):
        """Distance from a point to the segment."""
        if self.horizontal:
            dx = max(self.x0 - x, 0, x - self.x1); return math.hypot(dx, y - self.y0)
        dy = max(self.y0 - y, 0, y - self.y1); return math.hypot(x - self.x0, dy)


def segments(page):
    if page.vector is not None:
        from .vector_pdf import segments as vector_segments
        return vector_segments(page.vector)
    segs = []
    # Banded (rows for horizontal lines, columns for vertical ones): no whole-page label image on 14k px sheets.
    hstats = _banded_stats(page.hlines)
    vstats = [(y, x, h, w, area, cy, cx) for x, y, w, h, area, cx, cy in _banded_stats(np.ascontiguousarray(page.vlines.T))]
    for stats, horizontal in ((hstats, True), (vstats, False)):
        for x, y, w, h, area, _, _ in stats:
            if horizontal:
                segs.append(Seg(int(x), int(y + h // 2), int(x + w - 1), int(y + h // 2), area / max(w, 1), True))
            else:
                segs.append(Seg(int(x + w // 2), int(y), int(x + w // 2), int(y + h - 1), area / max(h, 1), False))
    segs = _bridge(segs, page)
    if segs:
        median = float(np.median([s.thick for s in segs]))
        for s in segs:
            s.bus = s.thick > 1.7 * median and max(s.x1 - s.x0, s.y1 - s.y0) > 200
    return segs


def _bridge(segs, page):
    """Join collinear pieces of one wire split by scan dropouts (gap < ~1 character)."""
    ch = char_height(page.text) or 40.0
    drift = max(3, int(0.18 * ch))         # parallel wires are >= half a character apart
    out = []
    for horizontal in (True, False):
        # (position across the wire, start, end) so both orientations share one merge loop
        key = (lambda s: (s.y0, s.x0, s.x1)) if horizontal else (lambda s: (s.x0, s.y0, s.y1))
        rows = {}                          # across-position bucket -> open merged pieces
        for s in sorted((s for s in segs if s.horizontal == horizontal), key=lambda s: key(s)[1]):
            across, start, end = key(s)
            target = None
            for b in range(across // 4 - 2, across // 4 + 3):
                for m in rows.get(b, []):
                    m_across, _, m_end = key(m)
                    # a long edge drifts a few pixels across a scan (U43 in sample 1: x 4470 -> 4466 -> 4461)
                    if abs(m_across - across) <= drift and -3 <= start - m_end <= ch * 0.9:
                        target = m; break
                if target:
                    break
            if target:
                if horizontal:target.x1 = max(target.x1, end)
                else:target.y1 = max(target.y1, end)
                target.thick = max(target.thick, s.thick)
            else:
                rows.setdefault(across // 4, []).append(Seg(s.x0, s.y0, s.x1, s.y1, s.thick, s.horizontal))
        out.extend(m for ms in rows.values() for m in ms)
    return out


def dots(page, ch):
    """Junction dots: small, round, solid blobs (wires are thin, so their distance transform stays low)."""
    if page.vector is not None:
        return [(x,y) for x,y,_ in page.vector.dots]
    H, band, overlap = page.binary.shape[0], 2048, 256      # row bands: no whole-page float image
    out = []
    for y0 in range(0, H, band - overlap):
        y1 = min(H, y0 + band)
        dist = cv2.distanceTransform(page.binary[y0:y1], cv2.DIST_L2, 5)
        core = (dist >= max(3.0, ch * 0.16)).astype(np.uint8) * 255
        _, _, stats, cent = cv2.connectedComponentsWithStats(core, 8)
        lo, hi = (0 if y0 == 0 else overlap // 2), (y1 - y0 if y1 == H else band - overlap // 2)
        for (x, y, w, h, area), (cx, cy) in zip(stats[1:], cent[1:]):
            if lo <= cy < hi and w <= ch * 0.8 and h <= ch * 0.8 and 0.5 < w / max(h, 1) < 2.0:
                out.append((float(cx), float(cy) + y0))
        if y1 == H:
            break
    return out


def boxes(page, ch):
    """Closed rectangles drawn with wire-weight lines: IC bodies."""
    lines = cv2.bitwise_or(page.hlines, page.vlines)
    lines = cv2.dilate(lines, np.ones((5, 5), np.uint8))
    contours, hier = cv2.findContours(lines, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    if hier is None:
        return out
    H, W = lines.shape
    for c, hrow in zip(contours, hier[0]):
        if hrow[3] < 0:
            continue                      # only holes: the inside of a closed outline
        x, y, w, h = cv2.boundingRect(c)
        if w < 2.5 * ch or h < 2.5 * ch or w > W * 0.5 or h > H * 0.5:
            continue
        if cv2.contourArea(c) < 0.85 * w * h:
            continue
        out.append((x - 3, y - 3, x + w + 3, y + h + 3))
    return out


def seg_boxes(segs, ch, tol):
    """IC bodies drawn as two vertical edges of equal span joined by top and bottom lines.
    Works when the outline is not one closed shape (pin bubbles and scan dropouts break it)."""
    vs = [s for s in segs if not s.horizontal and s.y1 - s.y0 >= 2.5 * ch]
    # A long body edge can arrive in pieces: scan drift and pin junctions break it (U43 in sample 1:
    # x 4470 then 4463; 4910, a 46 px gap, then 4906). Chained edges join the candidates; the pieces stay.
    chains = []
    for s in sorted(vs, key=lambda s: s.y0):
        c = next((c for c in chains if abs(c[0] - s.x0) <= 0.3 * ch and -3 <= s.y0 - c[2] <= 2 * ch), None)
        if c:
            c[2], c[3] = max(c[2], s.y1), c[3] + 1
        else:
            chains.append([s.x0, s.y0, s.y1, 1])
    vs = sorted(vs + [Seg(x, y0, x, y1, 0, False) for x, y0, y1, n in chains if n > 1], key=lambda s: s.x0)
    hs = [s for s in segs if s.horizontal]
    out = []
    def covered(y, xa, xb):
        """Half the width covered; (reaches the left corner, reaches the right corner)."""
        near = [h for h in hs if abs(h.y0 - y) <= tol * 2]
        span = sum(max(0, min(h.x1, xb) - max(h.x0, xa)) for h in near)
        return span >= 0.5 * (xb - xa), any(h.x0 <= xa + ch and h.x1 >= xa for h in near), \
            any(h.x0 <= xb and h.x1 >= xb - ch for h in near)

    def closed(y0, y1, xa, xb):
        # top and bottom lines present, and each corner reached by one of them: a wire bus beside a
        # body is not its edge (both lines then stop a long way short of it)
        (t, tl, tr), (u, bl, br) = covered(y0, xa, xb), covered(y1, xa, xb)
        return t and u and (tl or bl) and (tr or br)
    for i, a in enumerate(vs):
        for b in vs[i + 1:]:
            gap = b.x0 - a.x0
            if gap > 25 * ch:
                break
            if gap < 2.5 * ch:
                continue
            overlap = min(a.y1, b.y1) - max(a.y0, b.y0)
            if overlap < 0.8 * min(a.y1 - a.y0, b.y1 - b.y0):
                continue
            # pins joining at a corner can break one edge short: test the outer and inner extents
            for y0, y1 in ((min(a.y0, b.y0), max(a.y1, b.y1)), (max(a.y0, b.y0), min(a.y1, b.y1))):
                if closed(y0, y1, a.x0, b.x0):
                    out.append((a.x0 - 3, y0 - 3, b.x0 + 3, y1 + 3))
                    break
            else:
                continue
            break
    return out


def _merge_boxes(bxs):
    """One box per rectangle. A much smaller rectangle inside a larger one is kept: bodies drawn inside
    a rectangle of wires and buses (U15 in sample 1); recognize() takes the box its pins end on."""
    out = []
    for b in sorted(bxs, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True):
        area = (b[2] - b[0]) * (b[3] - b[1])
        if not any(_overlap(b, k) > 0.7 * area and area > 0.6 * (k[2] - k[0]) * (k[3] - k[1]) for k in out):
            out.append(b)
    return out


def _split_stacked(bxs, segs, toks, ch, candidates=()):
    """An outline holding two IC references is two bodies read as one: seg_boxes pairs a long bus
    wire with a body edge, or bodies drawn edge to edge share side lines that _bridge joins, and
    _merge_boxes keeps the large outline over the real ones. Use the real body rectangles inside it,
    else cut it at the full-width lines between the references; only when every piece then holds at
    most one reference and none is lost."""
    ics = [(r, t.cx, t.cy) for t in toks for r in [normalize_ref(t.text)] if r and re.fullmatch(r'(U|IC)\d{1,3}[A-H]?', r)]
    area = lambda b: (b[2] - b[0]) * (b[3] - b[1])
    out = []
    for b in bxs:
        inside = {r for r, x, y in ics if _inside(b, x, y)}
        pieces = None
        holds = lambda c: {r for r, x, y in ics if _inside(c, x, y)}
        if len(inside) >= 2 and all(any(c is not b and area(c) < area(b) and _inside(c, x, y) and len(holds(c)) == 1
                                        for c in bxs) for r, x, y in ics if r in inside):
            continue                      # each reference already has its own body: drop the false outline
        if len(inside) >= 2:
            kids = _merge_boxes([c for c in candidates if area(c) < 0.8 * area(b) and _overlap(c, b) > 0.9 * area(c)])
            held = [{r for r, x, y in ics if _inside(c, x, y)} for c in kids]
            if kids and all(len(h) <= 1 for h in held) and set().union(*held) == inside:
                pieces = kids
        for horizontal in (True, False) if len(inside) >= 2 and pieces is None else ():
            lo, hi = (b[1], b[3]) if horizontal else (b[0], b[2])
            a0, a1 = (b[0], b[2]) if horizontal else (b[1], b[3])
            cuts = sorted({s.y0 if horizontal else s.x0 for s in segs if s.horizontal == horizontal and
                           lo + 2.5 * ch < (s.y0 if horizontal else s.x0) < hi - 2.5 * ch and
                           min(a1, s.x1 if horizontal else s.y1) - max(a0, s.x0 if horizontal else s.y0) >= 0.8 * (a1 - a0)})
            edges = [lo] + cuts + [hi]
            spans = [(p - 3 if p != lo else p, q + 3 if q != hi else q) for p, q in zip(edges, edges[1:]) if q - p >= 2.5 * ch]
            cand = [(b[0], p, b[2], q) if horizontal else (p, b[1], q, b[3]) for p, q in spans]
            held = [{r for r, x, y in ics if _inside(c, x, y)} for c in cand]
            if cuts and all(len(h) <= 1 for h in held) and set().union(*held) == inside:
                pieces = cand
                break
        out.extend(pieces or [b])
    return out


class DSU:
    def __init__(self, n): self.p = list(range(n))
    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]; a = self.p[a]
        return a
    def union(self, a, b): self.p[self.find(a)] = self.find(b)


def connect(segs, dot_points, tol):
    """Union segments at junction dots and at shared end points. Buses never join plain wires."""
    dsu = DSU(len(segs))
    grid = {}
    cell = max(int(tol * 4), 16)
    for i, s in enumerate(segs):
        for gx in range(min(s.x0, s.x1) // cell - 1, max(s.x0, s.x1) // cell + 2):
            for gy in range(min(s.y0, s.y1) // cell - 1, max(s.y0, s.y1) // cell + 2):
                grid.setdefault((gx, gy), []).append(i)
    near = lambda x, y: {i for i in grid.get((int(x) // cell, int(y) // cell), [])}
    for x, y in dot_points:
        hit = [i for i in near(x, y) if segs[i].dist(x, y) <= tol * 1.5]
        for kind in (False, True):
            group = [i for i in hit if segs[i].bus == kind]
            for a, b in zip(group, group[1:]):
                dsu.union(a, b)
    for i, s in enumerate(segs):
        for ex, ey in s.ends():
            for j in near(ex, ey):
                if j != i and segs[j].bus == s.bus and any(math.hypot(ex - fx, ey - fy) <= tol for fx, fy in segs[j].ends()):
                    dsu.union(i, j)
    return dsu


# ---------------------------------------------------------------- assembly

def _box_dist(t, x, y):
    return math.hypot(max(t.x0 - x, 0, x - t.x1), max(t.y0 - y, 0, y - t.y1))


def _inside(b, x, y, pad=0):
    return b[0] - pad <= x <= b[2] + pad and b[1] - pad <= y <= b[3] + pad


def _on_edge(b, x, y, tol):
    """Point lies on the outline of box b."""
    if not _inside(b, x, y, tol):
        return False
    return min(abs(x - b[0]), abs(x - b[2]), abs(y - b[1]), abs(y - b[3])) <= tol + 3


def _is_outline(s, bxs, tol):
    for b in bxs:
        if s.horizontal and min(abs(s.y0 - b[1] - 3), abs(s.y0 - b[3] + 3)) <= tol and s.x0 >= b[0] - tol and s.x1 <= b[2] + tol:
            return True
        if not s.horizontal and min(abs(s.x0 - b[0] - 3), abs(s.x0 - b[2] + 3)) <= tol and s.y0 >= b[1] - tol and s.y1 <= b[3] + tol:
            return True
    return False


def normalize_ref(text):
    t = text.upper().replace('O', '0') if text[:1].upper() in 'UR' else text.upper()
    t = re.sub(r'^(U|R|C|J|P)[\-_.]?', r'\1', t)
    return t if REF_RE.match(t) else None


def _reread_numbers(page, free, numbers, toks, ch):
    """OCR's line detector skips lone digits. At every free wire end without a pin number,
    read the closest small glyph cluster directly (rotated too for vertical wires)."""
    engine = ocr_engine()
    H, W = page.text.shape
    covered = [(t.x0, t.y0, t.x1, t.y1) for t in toks]
    found = []
    for _, x, y, (ux, uy) in free:
        if any(_box_dist(t, x, y) <= 1.6 * ch for t, _ in numbers + found):
            continue
        r = int(1.9 * ch)
        x0, y0, x1, y1 = max(0, int(x) - r), max(0, int(y) - r), min(W, int(x) + r), min(H, int(y) + r)
        win = page.text[y0:y1, x0:x1]
        n, _, stats, cent = cv2.connectedComponentsWithStats(win, 8)
        glyphs = [(gx + x0, gy + y0, gx + x0 + gw, gy + y0 + gh) for gx, gy, gw, gh, a in stats[1:]
                  if 0.45 * ch <= max(gw, gh) <= 1.4 * ch and a >= 15]
        glyphs = [g for g in glyphs if not any(_overlap(g, c) > 0 for c in covered)]
        if not glyphs:
            continue
        # cluster glyphs that touch within half a character, starting from the closest one
        glyphs.sort(key=lambda g: math.hypot((g[0] + g[2]) / 2 - x, (g[1] + g[3]) / 2 - y))
        cx0, cy0, cx1, cy1 = glyphs[0]
        for g in glyphs[1:]:
            if g[0] <= cx1 + ch * 0.5 and g[2] >= cx0 - ch * 0.5 and g[1] <= cy1 + ch * 0.5 and g[3] >= cy0 - ch * 0.5:
                cx0, cy0, cx1, cy1 = min(cx0, g[0]), min(cy0, g[1]), max(cx1, g[2]), max(cy1, g[3])
        if math.hypot((cx0 + cx1) / 2 - x, (cy0 + cy1) / 2 - y) > 1.8 * ch:
            continue
        crop = cv2.copyMakeBorder(255 - page.text[cy0:cy1, cx0:cx1], 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
        options = [crop]
        if abs(uy) > abs(ux):              # vertical wire: its pin number is usually printed rotated
            options += [cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE), cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)]
        best = None
        for c in options:
            res, _ = engine(cv2.cvtColor(c, cv2.COLOR_GRAY2BGR), use_det=False, use_cls=False)
            if res:
                num = as_number(clean_text(str(res[0][0])))
                if num and (best is None or res[0][1] > best[1]):
                    best = (num, float(res[0][1]))
        if best and best[1] >= 0.5:
            t = Token(best[0], best[1], cx0, cy0, cx1, cy1)
            found.append((t, best[0])); covered.append((cx0, cy0, cx1, cy1))
    return found


def _strip_words(strip, axis, ch, reverse):
    """Glyph groups along a text strip, ordered from the pin end outward; a word break is a
    centre-to-centre step wider than a monospaced character pitch plus a space."""
    cells = [c for c in _cells(strip, axis, ch) if c[1] - c[0] >= 0.15 * ch]
    if reverse:
        cells = cells[::-1]
    # A sliver of the body outline left at the pin end after line removal reads as a "1" ("5" -> "51"):
    # narrow, touching the edge, and apart from the glyphs that follow it.
    if len(cells) >= 2:
        length = strip.shape[1 - axis]
        (a0, a1), (b0, b1) = cells[0], cells[1]
        edge_gap, next_gap = (length - a1, a0 - b1) if reverse else (a0, b0 - a1)
        if a1 - a0 <= 0.26 * ch and edge_gap <= 0.1 * ch and next_gap >= 0.35 * ch:
            cells = cells[1:]
    words = []
    for c in cells:
        if words and abs((c[0] + c[1]) / 2 - (words[-1][-1][0] + words[-1][-1][1]) / 2) <= 1.33 * ch:
            words[-1].append(c)
        else:
            words.append([c])
    # "SPWE4 14": a narrow "1" closes the space between a pin number and its label, so they come out
    # as one long word. Split the pin-end word at its widest glyph step when that step stands out.
    if words and len(words[0]) >= 3 and abs(words[0][-1][1] - words[0][0][0]) > 3.2 * ch:
        w = words[0]
        steps = [abs((b[0] + b[1]) / 2 - (a[0] + a[1]) / 2) for a, b in zip(w, w[1:])]
        k = max(range(min(4, len(steps))), key=lambda j: steps[j])
        if steps[k] >= 1.2 * float(np.median(steps)):
            words[0:1] = [w[:k + 1], w[k + 1:]]
    return [(min(w[0][0], w[-1][0]), max(w[0][1], w[-1][1])) for w in words]


_TEXT_MODEL = None
_TEXT_FALLBACK = None
TEXT_CHARS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-+[]:/.<>=~*#_'


def text_model():
    """Fine-tuned schematic text reader (training/schematic_ocr.py, exported to ONNX), or None."""
    global _TEXT_MODEL
    if _TEXT_MODEL is None:
        import os
        from pathlib import Path
        path = Path(os.getenv('S2SDN_TEXT_MODEL') or Path(__file__).resolve().parents[2] / 'checkpoints/schematic-ocr/model.onnx')
        _TEXT_MODEL = False
        if path.is_file():
            try:
                import onnxruntime as ort
                _TEXT_MODEL = ort.InferenceSession(str(path), providers=(['CUDAExecutionProvider'] if use_gpu() else []) + ['CPUExecutionProvider'])
            except Exception:
                _TEXT_MODEL = False
    return _TEXT_MODEL or None


def fallback_text_model():
    global _TEXT_FALLBACK
    import os
    from pathlib import Path
    from .text_fallback import load
    baseline = Path(os.getenv('S2SDN_TEXT_MODEL') or Path(__file__).resolve().parents[2] / 'checkpoints/schematic-ocr/model.onnx')
    _TEXT_FALLBACK = load(baseline, TEXT_CHARS, use_gpu())
    return _TEXT_FALLBACK


def read_text_model(page, x0, y0, x1, y1, rotate, *, fallback_scope=None):
    """Second reading of one crop by the fine-tuned model: (text, min character confidence)."""
    sess = text_model()
    if sess is None or x1 <= x0 or y1 <= y0:
        return None
    img = 255 - page.text[max(0, y0 - 2):y1 + 2, max(0, x0 - 2):x1 + 2]
    if rotate:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    h, w = img.shape
    nw = max(8, min(256, int(round(w * 32 / max(h, 1)))))
    x = cv2.resize(img, (nw, 32), interpolation=cv2.INTER_AREA if h > 32 else cv2.INTER_CUBIC)
    x = (255 - x).astype(np.float32)[None, None] / 255.0
    pad = (-x.shape[3]) % 4
    if pad:
        x = np.pad(x, ((0, 0), (0, 0), (0, 0), (0, pad)))
    logits = sess.run(None, {'image': x})[0][0]
    e = np.exp(logits - logits.max(-1, keepdims=True)); probs = e / e.sum(-1, keepdims=True)
    best = probs.argmax(-1)
    out, prev, confs = [], 0, []
    for k, pk in zip(best, probs.max(-1)):
        if k != prev and k != 0:
            out.append(TEXT_CHARS[k - 1]); confs.append(float(pk))
        prev = k
    reading = (''.join(out), min(confs)) if out else None
    fallback = fallback_text_model() if fallback_scope is not None else None
    return fallback.read(x, reading, scope=fallback_scope) if fallback else reading


def _read_strip(page, x, y, ux, uy, ch, side, *, audit=None):
    """One candidate text strip beside a pin wire. side=-1: above / left of the wire, +1: below / right."""
    H, W = page.text.shape
    L = int(10 * ch)
    near, far = (-1.35 * ch, -0.08 * ch) if side < 0 else (0.08 * ch, 1.35 * ch)
    if abs(ux) >= abs(uy):                         # horizontal pin wire
        out = -1 if ux > 0 else 1                  # direction away from the body
        y0, y1 = max(0, int(y + near)), min(H, max(1, int(y + far)))
        x0, x1 = (max(0, int(x - L)), int(x)) if out < 0 else (int(x), min(W, int(x + L)))
        words = _strip_words(page.text[y0:y1, x0:x1], 0, ch, reverse=out < 0)
        start = (x1 - x0) if out < 0 else 0
        box = lambda a, b: (x0 + a, y0, x0 + b, y1)
        rotate = False
    else:                                          # vertical pin wire, rotated text
        out = -1 if uy > 0 else 1
        x0, x1 = max(0, int(x + near)), min(W, max(1, int(x + far)))
        y0, y1 = (max(0, int(y - L)), int(y)) if out < 0 else (int(y), min(H, int(y + L)))
        words = _strip_words(page.text[y0:y1, x0:x1], 1, ch, reverse=out < 0)
        start = (y1 - y0) if out < 0 else 0
        box = lambda a, b: (x0, y0 + a, x1, y0 + b)
        rotate = True
    if not words:
        return None, None
    if min(abs(words[0][0] - start), abs(words[0][1] - start)) > 0.9 * ch or words[0][1] - words[0][0] > 3.2 * ch:
        return None, None
    num = _ocr_box(page, *box(*words[0]), rotate)
    if audit is not None:
        audit['primary'] = (num.text, float(num.conf)) if num else None
        audit['secondary'] = read_text_model(page, *box(*words[0]), rotate)
    num = as_number(num.text) if num else None
    if not num:                                    # second opinion from the fine-tuned reader
        alt = audit.get('secondary') if audit is not None else read_text_model(page, *box(*words[0]), rotate)
        num = alt[0] if alt and alt[1] >= 0.6 and re.fullmatch(r'\d{1,3}', alt[0]) and int(alt[0]) > 0 else None
    if not num:
        return None, None
    label = None
    if len(words) > 1 and abs((words[1][0] + words[1][1]) / 2 - (words[0][0] + words[0][1]) / 2) <= 6 * ch:
        # the label runs from the next glyph group until a clear gap (glyph groups inside one label
        # can be split by merged or broken glyphs)
        lo, hi = words[1]
        for w in words[2:]:
            gap = (w[0] - hi) if w[0] >= hi else (lo - w[1])
            if gap > 0.9 * ch:
                break
            lo, hi = min(lo, w[0]), max(hi, w[1])
        t = _ocr_box(page, *box(lo, hi), rotate)
        text = t.text.upper().strip('<>[]()=_.') if t else ''
        cands = [text] if t and t.conf >= 0.3 and len(text) >= 2 and not text.isdigit() else []
        alt = read_text_model(page, *box(lo, hi), rotate)
        if alt and alt[1] >= 0.5 and len(alt[0]) >= 2 and not alt[0].isdigit():
            cands.append(alt[0])
        label = cands or None                      # validated against the sheet vocabulary by the caller
    return num, label


def read_pin_strip(page, x, y, ux, uy, ch):
    """IC pins on printed schematics carry their pin number right outside the body edge and an
    optional net label further out, both resting on the pin wire (on either side, depending on the
    drafting style). Read them directly from the text layer: returns (pin number, label)."""
    best = (None, None)
    for side in (-1, 1):
        num, label = _read_strip(page, x, y, ux, uy, ch, side)
        if num and (best[0] is None or (label and not best[1])):
            best = (num, label)
        if best[0] and best[1]:
            break
    return best


def pin_sequences(rows, reads, ch):
    """Pin numbers along one body edge run in a sequence (57 58 59 60, or 2 4 6 8) at the drawing's pin
    pitch. Where >= 3 readable pins and 60% of the row fit one (start, step +-1/+-2), pins left unread,
    read twice (a neighbour's column: "57" "57") or misread long ("581") take the number their place
    gives, unless another pin of the part already has it. A unique, plausible reading is never overridden;
    a label read twice goes with the stolen number.
    rows: {row: [(key, ref, position along the edge)]}; reads: {key: (number, label)}, updated in place."""
    owned, count = {}, Counter()
    for row in rows.values():
        for k, ref, _ in row:
            if reads[k][0]:
                owned.setdefault(ref, set()).add(reads[k][0]); count[ref, reads[k][0]] += 1
    fixed = []
    for row in rows.values():
        row = sorted(row, key=lambda r: r[2])
        gaps = [b[2] - a[2] for a, b in zip(row, row[1:]) if b[2] - a[2] > 0.5 * ch]
        if len(row) < 3 or not gaps:
            continue
        pitch = float(np.median(gaps))
        slot = [round((r[2] - row[0][2]) / pitch) for r in row]
        nums = [int(reads[k][0]) if (reads[k][0] or '').isdigit() else None for k, _, _ in row]
        best = None
        for j, n in enumerate(nums):
            for step in ((1, -1, 2, -2) if n is not None else ()):
                start = n - step * slot[j]
                fit = sum(1 for s, m in zip(slot, nums) if m is not None and m == start + step * s)
                if best is None or fit > best[0]:
                    best = (fit, start, step)
        if not best or best[0] < 3 or best[0] < 0.6 * sum(m is not None for m in nums):
            continue
        _, start, step = best
        for (k, ref, _), s, m in zip(row, slot, nums):
            want = str(start + step * s)
            if int(want) <= 0 or m is not None and str(m) == want or want in owned.get(ref, set()):
                continue
            if m is not None and count[ref, str(m)] < 2 and len(str(m)) <= len(want):
                continue                  # a unique, plausible reading stands (AM2910: 34 36 38 40 2 4)
            old = reads[k]
            twice = old[1] and any(reads[o][1] == old[1] for o, _, _ in row if o != k)
            reads[k] = (want, None if twice else old[1])
            owned.setdefault(ref, set()).add(want)
            fixed.append((ref, old[0], want))
    return fixed


def symbol_consensus(ends, reads, values, ch):
    """Repeated parts are drawn with one symbol: the pin at a given place on a 74F194 body has the same
    number on every copy. Pin numbers read cleanly on some copies fill in or correct faint ones.
    ends: [(key, body box, x, y)]; reads: {key: (number, label)}, updated in place; values: box -> part
    number. A copy is corrected only where >= 2 of its own readable pins already agree, so a different
    section of a multi-section part (74F244 halves share an outline) is never renumbered."""
    groups = {}
    for k, box, x, y in ends:
        v = values.get(box)
        if v and v != 'UNKNOWN':
            size = (round((box[2] - box[0]) / ch), round((box[3] - box[1]) / ch))
            groups.setdefault((v, size), {}).setdefault(box, []).append((k, x - box[0], y - box[1]))
    fixed = []
    for (v, _), copies in groups.items():
        if len(copies) < 2:
            continue
        slots = []                                  # [(dx, dy, [(box, key)])], same place within 0.6 ch
        for box, pins in copies.items():
            for k, dx, dy in pins:
                s = next((s for s in slots if abs(s[0] - dx) <= 0.6 * ch and abs(s[1] - dy) <= 0.6 * ch), None)
                if s is None:
                    slots.append((dx, dy, [(box, k)]))
                else:
                    s[2].append((box, k))
        agreed = {}
        for dx, dy, members in slots:
            votes = Counter(reads[k][0] for _, k in members if reads[k][0])
            if not votes:
                continue
            (top, n), *rest = votes.most_common()
            if n >= 2 and n >= 0.75 * sum(votes.values()) and not any(c >= 2 for _, c in rest):
                for box, k in members:
                    agreed[k] = top
        for box, pins in copies.items():
            ok = sum(1 for k, _, _ in pins if k in agreed and reads[k][0] == agreed[k])
            if ok < 2:
                continue
            own = {reads[k][0] for k, _, _ in pins if reads[k][0]}
            for k, _, _ in pins:
                if k in agreed and reads[k][0] != agreed[k] and agreed[k] not in own:
                    fixed.append((reads[k][0], agreed[k]))
                    reads[k] = (agreed[k], reads[k][1]); own.add(agreed[k])
    return fixed


def recover_split_pin_digits(rows, reads):
    """Recover a digit split off a duplicated pin number into its net label.

    Both OCR readers must independently return the same leading digit and
    indexed signal. At least three other signals on this edge must establish
    that family. The destination number must be unused, and another observation
    of the old number must remain. Unique pin readings are never changed.
    """
    owners = Counter((ref, reads[k][0]) for row in rows.values() for k, ref, _ in row if reads[k][0])
    proposals = []
    for row in rows.values():
        for k, ref, _ in row:
            number, labels = reads[k]
            if not number or len(number) != 1 or owners[ref, number] < 2 or not labels or len(labels) < 2:
                continue
            # Leading 1 and 8 can belong to I/B signal prefixes; the existing
            # label normalizer deliberately preserves them, so leave them alone.
            matches = [re.fullmatch(r'([2-79])([A-Z]{2,8})(\d{1,2})', text) for text in labels]
            if not all(matches) or len({m.groups() for m in matches}) != 1:
                continue
            digit, prefix, index = matches[0].groups()
            want = number + digit
            if owners[ref, want]:
                continue
            anchors = {m[1] for other, _, _ in row if other != k
                       for text in reads[other][1] or []
                       if (m := re.fullmatch(re.escape(prefix) + r'(\d{1,2})', text))}
            if len(anchors) < 3:
                continue
            proposals.append((k, ref, number, want, prefix + index))
    destinations = Counter((ref, want) for _, ref, _, want, _ in proposals)
    removals = Counter((ref, old) for _, ref, old, _, _ in proposals)
    fixed = []
    for k, ref, old, want, label in proposals:
        if destinations[ref, want] != 1 or removals[ref, old] >= owners[ref, old]:
            continue
        reads[k] = (want, [label])
        fixed.append((ref, old, want))
    return fixed


# Characters OCR confuses on plotter fonts; substituting within a pair is a cheap edit.
_PAIRS = {frozenset(p) for p in ['C0', 'DU', 'U0', 'D0', 'O0', 'DO', 'Q0', 'B8', 'S5', 'I1', 'L1', 'Z2', 'G6', 'CG', 'UV', 'EF', 'MN', 'CO', 'HN', 'B3']}
BUS_RE = re.compile(r'^([A-Z][A-Z_]{0,9})[\[E(C{](\d{1,2})[:;](\d{1,2})[\]J)}1]?$')


def _cost(a, b):
    """Edit distance where confusable characters cost 0.3."""
    d = [[0.0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):d[i][0] = float(i)
    for j in range(len(b) + 1):d[0][j] = float(j)
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            sub = 0.0 if a[i - 1] == b[j - 1] else 0.3 if frozenset((a[i - 1], b[j - 1])) in _PAIRS else 1.0
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + sub)
    return d[-1][-1]


def label_vocabulary(toks, strip_readings=()):
    """Net names this sheet uses. Signal families (PREFIX + index) are inferred from every reading:
    prefixes differing only by OCR-confusable characters are merged into the most frequent spelling,
    and a family seen with four or more indices contributes its whole index range. Bus declarations
    ("DD[1:19]") and confident plain labels are added as read."""
    from collections import Counter
    toks = list(toks) + [Token(normalize_pin_label(s), .9, 0, 0, 0, 0) for s in strip_readings]
    fam = {}
    vocab = set()
    for t in toks:
        text = t.text.upper().replace(' ', '')
        m = BUS_RE.match(text)
        if m and int(m.group(3)) <= 64 and int(m.group(2)) <= int(m.group(3)):
            vocab.update(f'{m.group(1)}{k}' for k in range(int(m.group(2)), int(m.group(3)) + 1)); continue
        m = re.match(r'^([A-Z0-9]{0,8}[A-Z])(\d{1,2})$', canonical_label(text))
        if m and len(m.group(1)) >= 2:
            fam.setdefault(m.group(1), set()).add(int(m.group(2)))
        elif t.conf >= 0.93 and LABEL_RE.match(text) and re.search(r'[A-Z]{2}', text):
            vocab.add(canonical_label(text))
    counts = Counter({p: len(v) for p, v in fam.items()})
    merged = {}
    for p, _ in counts.most_common():
        home = next((q for q in merged if len(q) == len(p) and _cost(p, q) <= 0.6), None)
        merged.setdefault(home or p, set()).update(fam[p])
    # A clipped bus header (CC[1:16] read as CC1:16]) can parse as a C family.
    # Repeated pin readings supply the missing prefix; transfer the declared range.
    prefixes = set(merged) | {m[1] for v in vocab if (m := re.fullmatch(r'([A-Z]+)(\d{1,2})', v))}
    promoted = {}
    for p in sorted(prefixes):
        # a thin leading glyph (I, 1, L) is the one OCR loses most: INBU read as NBU on a third of pins
        choices = [q for q, idx in merged.items() if len(q) == len(p) + 1 and (q.startswith(p) or q.endswith(p)) and
                   len(idx) >= max(4, (1 if q.endswith(p) and q[0] in 'IL' else 2) * len(merged.get(p, ())))]
        if len(choices) == 1:promoted[p] = choices[0]
    for p in promoted:
        while promoted[p] in promoted:promoted[p] = promoted[promoted[p]]
    for p, q in promoted.items():
        merged.setdefault(q, set()).update(merged.pop(p, set()))
    vocab = {promoted.get(m[1], m[1]) + m[2] if (m := re.fullmatch(r'([A-Z]+)(\d{1,2})', v)) else v for v in vocab}
    for p, idx in merged.items():
        if len(idx) >= 4 and re.search(r'[A-Z]{2}|^[A-Z]$', p) and not re.search(r'\d', p):
            # One bad BB97 reading must not manufacture BB17..96 on a BB1..16 sheet.
            clusters = [[]]
            for n in sorted(idx):
                if clusters[-1] and n - clusters[-1][-1] > 4:clusters.append([])
                clusters[-1].append(n)
            core = max(clusters, key=lambda c: (len(c), -min(c)))
            if len(core) >= 4:vocab.update(f'{p}{k}' for k in range(min(core), max(core) + 1))
    return vocab


def canonical_label(text):
    """One spelling per signal: ADDA00 and ADDA0 are the same net; OCR reads O for 0 in indices."""
    m = re.match(r'^(.*?[A-Z])([0-9OQ]{1,3})$', text)
    if m and re.search(r'\d', m.group(2)):
        return m.group(1) + str(int(m.group(2).replace('O', '0').replace('Q', '0')))
    return text


def normalize_pin_label(text):
    text = text.upper().strip('<>[]()=_. ')
    # Preserve a leading glyph that belongs to the signal prefix, rather than dropping it.
    if re.match(r'^1[A-Z]{2}', text):text = 'I' + text[1:]
    elif re.match(r'^8[A-Z]', text):text = 'B' + text[1:]
    else:text = re.sub(r'^[^A-Z~+\-]+', '', text) or text
    return canonical_label(text)


def _indexed_names(vocab):
    families = {}
    for name in vocab:
        m = re.fullmatch(r'([A-Z]{2,12})(\d{1,2})', name)
        if m:families.setdefault(m[1], {})[int(m[2])] = name
    return families


def _prefix_cost(reading, prefix):
    compact = lambda s: re.sub(r'(.)\1+', r'\1', s)
    return min(_cost(reading, prefix), _cost(compact(reading), compact(prefix)) + .2)


def _family_index_options(text, vocab):
    """Decode plotter-font index glyphs only into members of an established sheet family."""
    glyphs = {'O': ('0',), 'Q': ('0',), 'I': ('1',), 'L': ('1',), 'T': ('1', '7'),
              'S': ('5',), 'Z': ('2',), 'B': ('8',), 'G': ('6',), 'A': ('4',), 'M': ('11',)}
    found = []
    for prefix, members in _indexed_names(vocab).items():
        t = text
        if prefix[0] in 'IL' and not t.startswith(prefix[0]) and _cost(t[:len(prefix) - 1], prefix[1:]) <= .61:
            t = prefix[0] + t                          # the thin leading glyph was lost: "NBUI4" -> INBU14
        tail = t[len(prefix):]
        if len(members) < 4 or not 1 <= len(tail) <= 3 or _cost(t[:len(prefix)], prefix) > .61:
            continue
        options = ['']
        for char in tail:
            values = (char,) if char.isdigit() else glyphs.get(char, ())
            options = [a + b for a in options for b in values]
        found += [members[int(n)] for n in options if n and int(n) in members]
    return sorted(set(found), key=lambda n: (-len(re.sub(r'\d+$', '', n)), n))


def snap_label(text, vocab):
    """Nearest declared name when exactly one is close; otherwise the reading itself."""
    text = normalize_pin_label(text)
    if not vocab or text in vocab:
        return text
    decoded = _family_index_options(text, vocab)
    if len(decoded) == 1:return decoded[0]
    m = re.fullmatch(r'(.*?)(\d{1,2})', text)
    if m:
        scored = sorted((_prefix_cost(m[1], prefix), name) for prefix, members in _indexed_names(vocab).items()
                        if int(m[2]) in members for name in [members[int(m[2])]])
        if scored and scored[0][0] <= 1.3 and (len(scored) == 1 or scored[1][0] - scored[0][0] >= .29):
            return scored[0][1]
        return text
    idx = re.search(r'\d+$', text)
    same = lambda v: bool(idx) and v.endswith(idx.group(0)) and not v[:-len(idx.group(0))][-1:].isdigit()
    # OCR drops or doubles letters far more often than it invents index digits: on equal cost,
    # prefer the name that keeps the index that was read.
    scored = sorted((_cost(text, v), not same(v), v) for v in vocab if abs(len(v) - len(text)) <= 1)
    limit = 1.3 if len(text) >= 5 else 1.0
    if scored and scored[0][0] <= limit and (len(scored) == 1 or scored[1][0] - scored[0][0] >= 0.3
                                           or scored[1][1] != scored[0][1]):
        return scored[0][2]
    return text


def strip_label_options(readings, vocab):
    raw = [normalize_pin_label(s) for s in readings]
    indexed = lambda s: bool(re.fullmatch(r'[A-Z]{2,12}\d{1,2}', s))
    literal = list(dict.fromkeys(s for s in raw if s in vocab and indexed(s)))
    # When both readers supply the same index, keep the complete prefix they actually read.
    literal = [s for s in literal if not any(s != t and
               (a := re.fullmatch(r'([A-Z]+)(\d+)', s)) and
               (b := re.fullmatch(r'([A-Z]+)(\d+)', t)) and a[2] == b[2] and
               len(b[1]) > len(a[1]) and (b[1].startswith(a[1]) or b[1].endswith(a[1])) for t in literal)]
    decoded = [n for s in raw for n in _family_index_options(s, vocab)]
    snapped = [snap_label(s, vocab) for s in raw]
    options = list(dict.fromkeys(literal + decoded + [n for n in snapped if n in vocab and indexed(n)]))
    # Keep plausible clipped-prefix alternatives for the row geometry to disambiguate.
    for s in raw:
        m = re.fullmatch(r'([A-Z]+)(\d{1,2})', s)
        if not m:continue
        for prefix, members in sorted(_indexed_names(vocab).items(), key=lambda item: (-len(item[1]), item[0])):
            if int(m[2]) in members and 0 < len(prefix) - len(m[1]) <= 2 and \
                    (prefix.startswith(m[1]) or prefix.endswith(m[1])):
                if members[int(m[2])] not in options:options.append(members[int(m[2])])
    return options or list(dict.fromkeys([n for n in snapped if n in vocab] +
                                        [n for n in snapped if LABEL_RE.match(n)]))


def resolve_strip_rows(observations, vocab, ch):
    """Resolve a clipped index using two nearby numbered labels on the same body edge.

    A prediction must be a sheet-supported candidate, or the missing index of an explicitly
    read family head. Ambiguous numeric readings may choose only among supported alternatives.
    """
    anchors = []
    for o in observations:
        for option in o['options']:
            if m := re.fullmatch(r'([A-Z]{2,12})(\d{1,2})', option):
                anchors.append((o, m[1], int(m[2]), len(o['options']) == 1))
    for o in observations:
        allowed = set(o['options'])
        heads = {normalize_pin_label(s) for s in o['labels']}
        if len(allowed) == 1 and allowed.isdisjoint(heads):
            # A unique correction already has stronger direct evidence than interpolation.
            continue
        nearby = [(a, p, n, strong) for a, p, n, strong in anchors if a is not o and a['ref'] == o['ref'] and
                  a['side'] == o['side'] and abs(a['edge'] - o['edge']) <= ch and abs(a['axis'] - o['axis']) <= 6 * ch]
        predictions, weak, support, strong_support = [], set(), {}, {}
        for j, (a, prefix, ia, a_strong) in enumerate(nearby):
            for b, other, ib, b_strong in nearby[j + 1:]:
                if prefix != other or not 1 <= abs(ib - ia) <= 4:continue
                step = (b['axis'] - a['axis']) / (ib - ia)
                if not .6 * ch <= abs(step) <= 3 * ch:continue
                if min(a['axis'], b['axis']) - 2 * abs(step) > o['axis'] or \
                        o['axis'] > max(a['axis'], b['axis']) + 2 * abs(step):continue
                index = ia + (o['axis'] - a['axis']) / step
                if abs(index - round(index)) > .18:continue
                name = f'{prefix}{round(index)}'
                if name not in vocab:continue
                if name not in allowed and prefix not in heads:
                    # A clipped prefix and a 7 read as 1 need independent row
                    # evidence; two neighbours alone cannot override the index.
                    clipped = False
                    for reading in heads:
                        m = re.fullmatch(r'([A-Z]+)(\d{1,2})', reading)
                        target = str(round(index))
                        if m and 0 < len(prefix)-len(m[1]) <= 2 and (prefix.startswith(m[1]) or prefix.endswith(m[1])) and \
                                len(m[2]) == len(target) and m[2] != target and \
                                all(x == y or {x,y} == {'1','7'} for x,y in zip(m[2],target)):
                            clipped = True
                    if not clipped:continue
                    weak.add(name)
                    support.setdefault(name,set()).update((a['axis'],b['axis']))
                    if a_strong:strong_support.setdefault(name,set()).add(a['axis'])
                    if b_strong:strong_support.setdefault(name,set()).add(b['axis'])
                elif not (a_strong and b_strong and abs(ib-ia)<=2):
                    continue
                distance = (abs(o['axis'] - a['axis']) + abs(o['axis'] - b['axis'])) / abs(step)
                predictions.append((distance, name))
        predictions = sorted(p for p in predictions if p[1] not in weak or
                             len(support[p[1]]) >= 3 and strong_support.get(p[1]))
        if predictions:
            rivals = [score for score, name in predictions if name != predictions[0][1]]
            if not rivals or min(rivals) - predictions[0][0] >= 1:
                o['fixed'] = predictions[0][1]


def passive_value(text):
    """Resistor/capacitor values read with letter-for-digit slips: IKOO -> 1K00, 33OR -> 330R."""
    t = text.upper()
    if re.fullmatch(r'[0-9IOL]{1,4}[KMRUNP][0-9IOL]{0,3}', t) and re.search(r'\d', t.replace('O', '0').replace('I', '1')):
        head = re.match(r'[0-9IOL]+', t).group(0)
        return head.replace('O', '0').replace('I', '1').replace('L', '1') + t[len(head)] +             t[len(head) + 1:].replace('O', '0').replace('I', '1').replace('L', '1')
    return t


def _ic_value(text):
    """IC part numbers, including all-digit memory/PROM codes (2148, 75919)."""
    t = text.upper()
    return bool(IC_VALUE_RE.match(t) or re.fullmatch(r'\d{4,5}[A-Z]?', t))


# A U reference whose U or a digit was misread: "!84", "L61", "|59", "C17", "089", "US8" (U58).
LOST_U_RE = re.compile(r'([U!|ILC]|0(?=[1-9]\d$))?[-_.]?([0-9SOBIL!|]{1,3})')


def lost_u(text, bare=False):
    """The U reference a misread token stands for, else None. A bare number ("89") only with bare=True
    (inside a known body, where pin numbers are not printed); letters in the number only beside a digit."""
    m = LOST_U_RE.fullmatch(text.upper())
    if not m or not (m.group(1) or bare and m.group(2).isdigit()) or not re.search(r'\d', m.group(2)):
        return None
    n = m.group(2).translate(CONFUSABLE)
    return f'U{int(n)}' if n.isdigit() and int(n) > 0 else None


def lost_u_options(text, bare=False):
    """lost_u, plus the other reading of a blurred S (5 or 8: "US5" is U55 or U85)."""
    first = lost_u(text, bare)
    if not first:
        return []
    other = lost_u(text.upper().replace('S', '8'), bare)
    return [first] + ([other] if other and other != first else [])


def same_family(text, values):
    """74-series number with a slip, repaired from the sheet itself: "74F!61" -> 74F161, "74F24U" -> 74F240,
    "745174" -> 74F174 when 74F174 is printed elsewhere on the sheet (the family letter read as a digit)."""
    t = text.upper()
    m = re.fullmatch(r'(74[A-Z]{0,4})([0-9!|IOU]{2,4})([A-Z]?)', t)
    if m and not m.group(2).isdigit() and re.search(r'\d', m.group(2)):
        t = m.group(1) + m.group(2).translate(str.maketrans('!|IOU', '11100')) + m.group(3)
    m = re.fullmatch(r'74[51](\d{3})', t)                       # 74S174 is a real family: only digits
    if m:
        same = {v for v in values if re.fullmatch(r'74[A-Z]{1,4}' + m.group(1), v)}
        if len(same) == 1:
            t = same.pop()
    return t


def _reread_ref(page, p, box, ch):
    """Read the area around an IC part number again, enlarged, for the reference printed beside it.
    A U (or a typical misreading of it) must lead, and two enlargements must agree: a thin glyph
    the reader cannot resolve ("U7" -> "U?", "07", "U9") gives no reference rather than a guess."""
    H, W = page.text.shape
    pad = int(5 * ch)
    x0, y0, x1, y1 = max(0, p.x0 - pad), max(0, p.y0 - pad), min(W, p.x1 + pad), min(H, p.y1 + pad)
    if box is not None:
        x0, y0, x1, y1 = max(x0, int(box[0]) + 4), max(y0, int(box[1]) + 4), min(x1, int(box[2]) - 4), min(y1, int(box[3]) - 4)
    if x1 - x0 < ch or y1 - y0 < ch:
        return None
    crop = 255 - page.text[y0:y1, x0:x1]
    if p.vertical:
        crop = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
    readings = []
    for glyph in (40.0, 56.0):                    # two enlargements, ~40 and ~56 px characters
        scale = min(3.0, max(1.0, glyph / ch))
        img = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC) if scale > 1 else crop
        img = cv2.copyMakeBorder(img, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
        res, _ = ocr_engine()(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), use_cls=False)
        best = None
        for _, text, conf in res or []:
            r = lost_u(clean_text(str(text)))
            if r and (best is None or float(conf) > best[1]):
                best = (r, float(conf))
        readings.append(best)
    a, b = readings
    return (a[0], min(a[1], b[1])) if a and b and a[0] == b[0] else None


def read_ref_beside(page, toks, p, ch):
    """A reference cut short by OCR ("U" or "U?" for U7: a thin 7) beside an IC part number, read by the
    fine-tuned text reader on three crops running on along the text. All three must agree, confidently."""
    for t in toks:
        if t.vertical != p.vertical or not re.fullmatch(r'[U][^0-9]?', t.text.upper()) or \
                min(_box_dist(t, p.cx, p.cy), math.hypot(t.cx - p.cx, t.cy - p.cy)) > 2.5 * ch:
            continue
        reads = []
        for pad, run in ((0.1, 1.4), (0.15, 1.7), (0.2, 2.0)):
            q, r = int(pad * ch), int(run * ch)
            box = (t.x0 - q, t.y0 - r, t.x1 + q, t.y1 + q) if t.vertical else (t.x0 - q, t.y0 - q, t.x1 + r, t.y1 + q)
            got = read_text_model(page, *box, t.vertical)
            reads.append(normalize_ref(got[0]) if got and got[1] >= 0.95 else None)
        if reads[0] and re.fullmatch(r'U\d{1,3}', reads[0]) and reads.count(reads[0]) == 3:
            return reads[0], t
    return None


def reread_token(page, t, ch):
    """A low-confidence reference read again from its own pixels, enlarged: "U10" (0.68) -> U18."""
    H, W = page.text.shape
    pad = int(0.4 * ch)
    x0, y0, x1, y1 = max(0, t.x0 - pad), max(0, t.y0 - pad), min(W, t.x1 + pad), min(H, t.y1 + pad)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    img = 255 - page.text[y0:y1, x0:x1]
    if t.vertical:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    scale = min(3.0, max(1.5, 48.0 / ch))
    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    img = cv2.copyMakeBorder(img, 24, 24, 24, 24, cv2.BORDER_CONSTANT, value=255)
    res, _ = ocr_engine()(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), use_cls=False)
    best = max(((clean_text(str(text)), float(conf)) for _, text, conf in res or []), key=lambda r: r[1], default=None)
    return best if best and best[0] else None


def part_prefix(text):
    """Manufacturer prefix read with letter slips on clear sheets too: Idf7210L -> IDT7210L.
    Only the three prefix letters change, and only ahead of a part-number shaped tail."""
    m = re.fullmatch(r'[I1L|][DO0][TF7](\d{3,5}[A-Z]{0,2}\d{0,3})', text.upper())
    return 'IDT' + m.group(1) if m else text


def choose_wire_label(readings, wire):
    """Most-supported label, with reproducible geometry-based tie breaking.

    Horizontal labels rest above their wire; upward text rests to its left. OCR boxes
    for neighbouring rows can both touch a wire, but their baselines distinguish them.
    Preserve majority votes, then prefer matching orientation/baseline and confidence.
    """
    from collections import Counter
    counts = Counter(name for name, _ in readings)

    def alignment(token):
        distance = abs(wire.y0 - token.y1) if wire.horizontal else abs(wire.x0 - token.x1)
        return (wire.horizontal == token.vertical, distance, -token.conf, token.y0, token.x0)

    return min(counts, key=lambda name: (-counts[name],
               min(alignment(token) for label, token in readings if label == name), name))


def reread_part_tokens(page, toks, boxes, ch):
    """Second-reader recovery of damaged logic headers, preserving readable values.

    Two confident crops must agree with a value already printed on this sheet,
    and two other bodies must agree on dimensions and the header's position.
    """
    if page.soft is None:
        return []
    area = lambda b: (b[2] - b[0]) * (b[3] - b[1])
    body = lambda p: min((b for b in boxes if _inside(b, p.cx, p.cy)), key=area, default=None)
    shape = lambda p, b: (b[2] - b[0], b[3] - b[1], p.cx - b[0], p.cy - b[1])
    known = {}
    for p in toks:
        if p.conf >= .7 and PART_RE.fullmatch(p.text.upper()) and _ic_value(p.text) and (b := body(p)) is not None:
            known.setdefault((p.text.upper(), p.vertical), []).append((b, shape(p, b)))
    fixed = []
    for t in toks:
        if PART_RE.fullmatch(t.text.upper()) or not re.fullmatch(r'[7RP][A41][A-Z0-9]{3,7}', t.text.upper()):
            continue
        b = body(t)
        if b is None:
            continue
        reads = []
        for fraction in (.12, .2):
            pad = max(1, round(fraction * ch))
            reads.append(read_text_model(page, t.x0 - pad, t.y0 - pad, t.x1 + pad, t.y1 + pad, t.vertical,
                                         fallback_scope='part'))
        if not all(r and r[1] >= .9 for r in reads) or reads[0][0] != reads[1][0]:
            continue
        value = reads[0][0].upper()
        own_shape = shape(t, b)
        supporting = {box for box, other in known.get((value, t.vertical), []) if box != b and
                      all(abs(x - y) <= 1.25 * ch for x, y in zip(own_shape, other))}
        if len(supporting) < 2:
            continue
        fixed.append((t.text, value))
        t.text, t.conf = value, min(r[1] for r in reads)
    return fixed


def repeated_part_boxes(page, toks, boxes, ch):
    """Recover broken outlines where repeated labels and four pixel edges agree.

    At least three distinct bodies must agree on size, orientation and label
    offset. Each recovered edge needs at least half its span in the line layer,
    matching seg_boxes' closure rule. A repeated value alone is insufficient.
    """
    if page.soft is None:
        return []
    parts = [t for t in toks if t.conf >= .7 and PART_RE.fullmatch(t.text.upper()) and _ic_value(t.text)]
    area = lambda b: (b[2] - b[0]) * (b[3] - b[1])
    groups = {}
    for p in parts:
        body = min((b for b in boxes if _inside(b, p.cx, p.cy)), key=area, default=None)
        if body is None:
            continue
        shape = (body[2] - body[0], body[3] - body[1], p.cx - body[0], p.cy - body[1])
        clusters = groups.setdefault((p.text.upper(), p.vertical), [])
        cluster = next((c for c in clusters if all(abs(a - b) <= .6 * ch for a, b in zip(c[0][1], shape))), None)
        if cluster is None:
            clusters.append([(body, shape)])
        elif body not in [b for b, _ in cluster]:
            cluster.append((body, shape))
    out = []
    H, W = page.binary.shape

    def edge(mask, across, lo, hi, horizontal):
        pad = max(3, round(.7 * ch))
        limit = H if horizontal else W
        a, b = max(0, round(across) - pad), min(limit, round(across) + pad + 1)
        lo, hi = max(0, round(lo)), min(W if horizontal else H, round(hi))
        if b <= a or hi <= lo:
            return None
        crop = mask[a:b, lo:hi] if horizontal else mask[lo:hi, a:b].T
        coverage = np.count_nonzero(crop, axis=1) / (hi - lo)
        k = int(np.argmax(coverage))
        return a + k if coverage[k] >= .5 else None

    for p in parts:
        if any(_inside(b, p.cx, p.cy) for b in boxes + out):
            continue
        clusters = [c for c in groups.get((p.text.upper(), p.vertical), []) if len(c) >= 3]
        # Different sections/packages sharing a value cannot supply a unique template.
        if len(clusters) != 1:
            continue
        width, height, dx, dy = np.median([s for _, s in clusters[0]], axis=0)
        x, y = p.cx - dx, p.cy - dy
        x0 = edge(page.vlines, x, y + ch, y + height - ch, False)
        x1 = edge(page.vlines, x + width, y + ch, y + height - ch, False)
        y0 = edge(page.hlines, y, x + ch, x + width - ch, True)
        y1 = edge(page.hlines, y + height, x + ch, x + width - ch, True)
        if any(v is None for v in (x0, y0, x1, y1)):
            continue
        if abs(x1 - x0 - width) > ch or abs(y1 - y0 - height) > ch:
            continue
        candidate = (x0 - 3, y0 - 3, x1 + 3, y1 + 3)
        if not _inside(candidate, p.cx, p.cy) or any(
                _overlap(candidate, b) > .2 * min(area(candidate), area(b)) for b in boxes + out):
            continue
        out.append(candidate)
    return out


def unclaimed_body(part, box, boxes, anchors, pin_ends, ch):
    """An enclosing wire rectangle must not consume a separately outlined IC.

    Require a smaller closed body with multiple pin ends, no existing anchor,
    and a part label far from every anchor assigned to the enclosing rectangle.
    This only changes the assignment of an otherwise discarded part label.
    """
    owners = [a for a in anchors if a[3] == box] if box is not None else []
    if not owners or any(math.hypot(a[1] - part.cx, a[2] - part.cy) <= 6 * ch for a in owners):
        return box
    area = lambda b: (b[2] - b[0]) * (b[3] - b[1])
    candidates = [b for b in boxes if _inside(b, part.cx, part.cy) and area(b) < 0.5 * area(box)
                  and pin_ends[b] >= 2 and not any(a[3] == b or _inside(b, a[1], a[2]) for a in anchors)]
    return min(candidates, key=area, default=box)


def recognize(page, toks):
    ch = char_height(page.text) or 40.0
    tol = max(4.0, ch * 0.25)
    warnings = list(page.notes)
    PIN_DEBUG.clear()
    toks = toks if page.vector is not None else refine_tokens(page, toks, ch)
    segs = segments(page)
    candidates = boxes(page, ch) + seg_boxes(segs, ch, tol)
    bxs = _split_stacked(_merge_boxes(candidates), segs, toks, ch, candidates)
    caption_boxes = list(bxs)
    reread = reread_part_tokens(page, toks, bxs, ch)
    if reread:
        warnings.append('Part labels confirmed by two second-reader crops and matching symbols: ' +
                        ', '.join(f'{old}->{new}' for old, new in reread) + '. Check them.')
    # Rectangles closed by crossing wires are not IC bodies: a body holds its reference or part number.
    named = [t for t in toks if normalize_ref(t.text) or PART_RE.match(t.text.upper()) and re.search(r'[A-Z]', t.text.upper())]
    bxs = [b for b in bxs if any(_inside(b, t.cx, t.cy) for t in named)]
    restored = repeated_part_boxes(page, toks, bxs, ch)
    bxs += restored
    if restored:
        warnings.append(f'{len(restored)} IC outlines recovered using repeated part labels and four visible edges. Check them.')
    wires = [s for s in segs if not _is_outline(s, bxs, tol * 2)]
    dot_points = [d for d in dots(page, ch) if sum(s.dist(*d) <= tol * 1.5 for s in wires) >= 2]
    dsu = connect(wires, dot_points, tol)

    # Free wire ends: not shared with another wire and not on a junction dot.
    def joined(i, x, y):
        if any(math.hypot(x - dx, y - dy) <= tol * 1.5 for dx, dy in dot_points):
            return True
        return any(j != i and wires[j].bus == wires[i].bus and any(math.hypot(x - fx, y - fy) <= tol for fx, fy in wires[j].ends()) for j in range(len(wires)))
    free = []                              # (wire index, x, y, outward unit vector)
    for i, s in enumerate(wires):
        if s.bus:
            continue
        (ax, ay), (bx, by) = s.ends()
        length = max(1.0, math.hypot(bx - ax, by - ay))
        for (x, y), (ox, oy) in (((ax, ay), (bx, by)), ((bx, by), (ax, ay))):
            if not joined(i, x, y):
                free.append((i, x, y, ((x - ox) / length, (y - oy) / length)))

    # Token roles.
    # Keep the literal OCR casing for captions; the digital bus/part family
    # normalizers below intentionally use uppercase spellings.
    caption_tokens = [Token(t.text, t.conf, t.x0, t.y0, t.x1, t.y1, t.vertical) for t in toks]
    refs, parts, numbers, conns, labels = [], [], [], [], []
    printed = {t.text.upper() for t in toks if PART_RE.match(t.text.upper()) and t.text.upper().startswith('74')}
    for t in toks:
        t.text = same_family(part_prefix(t.text), printed)
        r = normalize_ref(t.text)
        if r and re.fullmatch(r'U\d{1,3}', r) and t.conf < 0.75 and page.soft is None and any(_inside(b, t.cx, t.cy) for b in bxs):
            again = reread_token(page, t, ch)   # a doubtful IC reference: read its own pixels again, enlarged
            r2 = normalize_ref(again[0]) if again and again[1] >= max(0.85, t.conf + 0.1) else None
            if r2 and re.fullmatch(r'U\d{1,3}', r2) and r2 != r:
                warnings.append(f'Reference {t.text} (confidence {t.conf:.2f}) read again as {r2}. Check it.')
                t.text, t.conf, r = r2, again[1], r2
        c = CONN_RE.search(t.text.upper())
        if c and not r:
            conns.append((t, c.group(1), c.group(2)))
            rest = CONN_RE.sub('', t.text.upper()).strip('=<>-_. ')
            if len(rest) >= 3 and re.search(r'[A-Z]', rest):
                labels.append((t, rest))
        elif r:
            refs.append((t, r))
        elif PART_RE.match(passive_value(t.text)) and re.search(r'[A-Z]', passive_value(t.text)):
            t.text = passive_value(t.text)
            parts.append(t)
        elif re.fullmatch(r'[1-9]\d{4}[A-Z]?', t.text.upper()):
            parts.append(t)                     # PROM/ROM device codes (75919); only U references take them
        elif re.fullmatch(r'[1-9]\d{3}[A-Z]?', t.text.upper()) and any(_inside(b, t.cx, t.cy) for b in bxs):
            parts.append(t)                     # memory part numbers (2148) inside a body; pin numbers sit outside
        elif as_number(t.text):
            numbers.append((t, as_number(t.text)))
        elif LABEL_RE.match(t.text.upper().strip('<>[]()=_.')) and not any(_inside(b, t.cx, t.cy) for b in bxs):
            labels.append((t, t.text.upper().strip('<>[]()=_.')))

    # Components: every reference occurrence is an anchor; its value is the nearest part number.
    # Outlines can overlap where a long wire pairs with a body edge; the body is where pin wires end.
    pin_ends = {b: sum(_on_edge(b, x, y, tol * 2) for _, x, y, _ in free) for b in bxs}

    def body_at(x, y):
        return max((b for b in bxs if _inside(b, x, y)), key=lambda b: pin_ends[b], default=None)

    components, anchors, taken = {}, [], set()
    for t, r in refs:
        box = body_at(t.cx, t.cy)
        ic_ref = re.fullmatch(r'(U|IC)\d{1,3}[A-H]?', r) is not None
        # IC part numbers belong to U/IC references only; Y0, S1, D7... inside a body are pin names
        fits = [p for p in parts if ic_ref or not _ic_value(p.text)]
        # A part number is printed in its reference's direction; rotated pin text inside a body
        # ("31822" beside U22 / 2148) is only a fallback.
        near = sorted(fits, key=lambda p: min(_box_dist(p, t.cx, t.cy), math.hypot(p.cx - t.cx, p.cy - t.cy) - 1.5 * ch)
                      + (2 * ch if p.vertical != t.vertical and not re.search(r'[A-Z]', p.text.upper()) else 0))
        value = ''
        if near and (_box_dist(near[0], t.cx, t.cy) < 2.5 * ch or math.hypot(near[0].cx - t.cx, near[0].cy - t.cy) < 4 * ch):
            value = near[0].text.upper()
            taken.add(id(near[0]))
        if not value and box is not None and re.fullmatch(r'U\d{1,3}', r) and                 not any(_inside(box, a[1], a[2]) for a in anchors):
            value = 'UNKNOWN'             # an IC body with its reference but no printed part number (PROMs)
        if not value:
            continue                      # pin names (D1, Y0, P16...) look like references but carry no part number
        if r not in components or value != 'UNKNOWN' and components[r] in ('', 'UNKNOWN'):
            components[r] = value         # a gate drawn twice: the copy with its part number printed wins
        anchors.append((r, t.cx, t.cy, box))
    # An IC part number no reference took: the reference was misread ("!84", "L61", "89") or not read.
    # Take a misread one beside it, else read the area again enlarged. A body with pins whose
    # reference stays unreadable is still a part: U_1, U_2 ... to annotate in Capture.
    unref, recovered = [], []
    for p in parts:
        if id(p) in taken or not _ic_value(p.text):
            continue
        box = body_at(p.cx, p.cy)
        if page.soft is not None:
            box = unclaimed_body(p, box, bxs, anchors, pin_ends, ch)
        if box is not None and all(a[3] != box or math.hypot(a[1] - p.cx, a[2] - p.cy) > 6 * ch for a in anchors) \
                and any(a[3] == box for a in anchors) and all(components.get(a[0]) != p.text.upper() for a in anchors if a[3] == box):
            box = None                    # a rectangle of wires around several gates (U4 ... 74F10): not one body
        if box is None and not re.search(r'[A-Z]', p.text.upper()):
            continue                      # an all-digit number outside any body is pin/label text ("88463": BB4 63)
        if any(a[3] == box for a in anchors) if box is not None else \
                any(math.hypot(a[1] - p.cx, a[2] - p.cy) < 4 * ch for a in anchors):
            continue
        found, lettered = None, bool(re.search(r'[A-Z]', p.text.upper()))
        for t in toks:
            opts = lost_u_options(t.text, bare=box is not None and _inside(box, t.cx, t.cy) and lettered)
            if page.soft is not None and not t.text.upper().startswith('U'):
                opts = []                 # blurred sheet: no guessing a U from "!", "L" or "0"
            u = next((o for o in opts if components.get(o) == p.text.upper()), opts[0] if opts else None)
            if not u or t is p or t.vertical != p.vertical or components.get(u, p.text.upper()) != p.text.upper() \
                    or normalize_ref(t.text) in components:
                continue                  # a known U only as another drawing of the same part; never a real C17
            near = _box_dist(t, p.cx, p.cy) < 2.5 * ch or math.hypot(t.cx - p.cx, t.cy - p.cy) < 4 * ch
            if near and (box is None or _inside(box, t.cx, t.cy)):
                if found is None or math.hypot(t.cx - p.cx, t.cy - p.cy) < math.hypot(found[1].cx - p.cx, found[1].cy - p.cy):
                    found = (u, t)
        if found and found[0] in components:
            anchors.append((found[0], found[1].cx, found[1].cy, box))
            numbers = [(t, n) for t, n in numbers if t is not found[1]]
            continue
        if found:
            r, (ax, ay) = found[0], (found[1].cx, found[1].cy)
            numbers = [(t, n) for t, n in numbers if t is not found[1]]
        else:
            # Blurred or low-resolution sheets lost those pixels: an enlarged re-read only invents digits
            # ("U87" -> U187). They keep the U_n placeholder for review instead.
            again = _reread_ref(page, p, box, ch) if page.soft is None else None
            r, (ax, ay) = (again[0] if again and again[0] not in components else None), (p.cx, p.cy)
            beside = read_ref_beside(page, toks, p, ch) if not r and page.soft is None else None
            if beside and beside[0] not in components:
                r, (ax, ay) = beside[0], (beside[1].cx, beside[1].cy)
        if r:
            recovered.append(r)
        elif box is not None and lettered and (page.soft is not None or any(_on_edge(box, x, y, tol * 2) for _, x, y, _ in free)):
            # (an all-digit number with no reference anywhere near is fused pin/label text, "88463" = BB4 63)
            r = f'U_{len(unref) + 1}'
            unref.append(r)
        else:
            continue
        components[r] = p.text.upper()
        anchors.append((r, ax, ay, box))
    if recovered:
        warnings.append('References read again beside their part numbers: ' + ', '.join(recovered) + '. Check them.')
    if unref:
        warnings.append(f'{len(unref)} IC bodies have a legible part number but an unreadable reference; '
                        f'placed as U_1..U_{len(unref)}. Annotate them in Capture.')

    # Modern device names need not belong to a finite manufacturer-prefix
    # regex. Read uniquely aligned captions beside visible bodies. This late
    # pass supplies newly recognized bodies to the following pin extraction.
    from .ic_caption import recover as recover_captions, external_connectors
    from .recognition_catalog import correct_literal
    recovered_captions = []
    for ref, value, box in recover_captions(caption_tokens, caption_boxes, segs, ch, components, anchors):
        literal = value
        value = correct_literal(literal)
        if value != literal:
            warnings.append(f'{ref}: caption {literal} matched the unique library spelling {value}. Check the marking.')
        components[ref] = value
        anchors.append((ref, (box[0]+box[2])/2, (box[1]+box[3])/2, box))
        recovered_captions.append((ref, value, box))
    conns = external_connectors(conns, [box for _, _, box in recovered_captions], ch)

    meaningful = [t for t, _ in refs + numbers + labels] + parts + [t for t, _, _ in conns]
    numbers += _reread_numbers(page, free, numbers, meaningful, ch)
    nodes = {}                             # (ref, pin) -> wire index
    used_ends = set()
    strip_labels = {}                      # wire index -> label read on that pin's own strip
    strip_observations = []
    # IC pins: wire ends on the edge of a named body, read directly along the pin wire.
    edge_pins, end_box = [], {}
    for k, (i, x, y, (ux, uy)) in enumerate(free):
        body = [a for a in anchors if a[3] and _on_edge(a[3], x, y, tol * 2)]
        if body:
            a = min(body, key=lambda a: math.hypot(a[1] - x, a[2] - y))
            ref, end_box[k] = a[0], a[3]
            edge_pins.append((k, i, x, y, ux, uy, ref))
    strip_reads = {k: read_pin_strip(page, x, y, ux, uy, ch) for k, i, x, y, ux, uy, ref in edge_pins}
    rows = {}                              # one body edge: same body and side, edge position within a character
    for k, i, x, y, ux, uy, ref in sorted(edge_pins, key=lambda e: (e[6], round(e[4]), round(e[5]), e[2] if abs(e[4]) >= abs(e[5]) else e[3])):
        across, along = (x, y) if abs(ux) >= abs(uy) else (y, x)
        key = next((r for r in reversed(list(rows)) if r[:3] == (ref, round(ux), round(uy)) and abs(r[3] - across) <= ch), None)
        rows.setdefault(key or (ref, round(ux), round(uy), across), []).append((k, ref, along))
    sequenced = pin_sequences(rows, strip_reads, ch)
    if sequenced:
        warnings.append(f'{len(sequenced)} pin numbers completed from the numbering along their body edge '
                        f'(e.g. {", ".join(f"{r}:" + (a or "?") + "->" + b for r, a, b in sequenced[:5])}). Check them.')
    box_values = {end_box[k]: components.get(ref) for k, i, x, y, ux, uy, ref in edge_pins}
    fixed = symbol_consensus([(k, end_box[k], x, y) for k, i, x, y, ux, uy, ref in edge_pins], strip_reads, box_values, ch)
    if fixed:
        warnings.append(f'{len(fixed)} faint pin numbers taken from other copies of the same part drawn identically '
                        f'(e.g. {", ".join((a or "?") + "->" + b for a, b in fixed[:5])}). Check them.')
    split_digits = recover_split_pin_digits(rows, strip_reads)
    if split_digits:
        warnings.append('Pin digits split into their adjacent net labels recovered by both OCR readers: '
                        + ', '.join(f'{ref}:{old}->{new}' for ref, old, new in split_digits) + '. Check them.')
    from .pin_crop_recovery import recover as recover_pin_crops
    crop_fixes = recover_pin_crops(page, edge_pins, strip_reads, components, ch, _read_strip)
    if crop_fixes:
        warnings.append('Clipped pin digits reread by both OCR readers at two crop widths and checked against library pin numbers: '
                        + ', '.join(f'{ref}:{old}->{new}' for ref, old, new in crop_fixes) + '. Check them.')
    for k, i, x, y, ux, uy, ref in edge_pins:
        num, label = strip_reads[k]
        PIN_DEBUG.append((ref, int(x), int(y), num, label))
        observation = None
        if label:
            horizontal = abs(ux) >= abs(uy)
            observation = {'wire': i, 'ref': ref, 'labels': label, 'active': False,
                           'side': (round(ux), round(uy)), 'axis': y if horizontal else x,
                           'edge': x if horizontal else y}
            strip_observations.append(observation)
        if not num:
            continue
        if (ref, num) in nodes and dsu.find(nodes[(ref, num)]) != dsu.find(i):
            warnings.append(f'{ref} pin {num} was read on two different wires; kept the first. Check it.')
            continue
        nodes[(ref, num)] = i
        used_ends.add(k)
        if observation is not None:observation['active'] = True
    vocab = label_vocabulary(toks, [s for o in strip_observations for s in o['labels']])
    for o in strip_observations:
        o['options'] = strip_label_options(o['labels'], vocab)
        o['fixed'] = o['options'][0] if o['options'] else None
    resolve_strip_rows(strip_observations, vocab, ch)
    for o in strip_observations:
        if o['active'] and o['fixed']:strip_labels[o['wire']] = o['fixed']
    for k, (i, x, y, (ux, uy)) in enumerate(free):
        if k in used_ends:
            continue
        # The pin number is printed beside the wire, outside the body; pin names sit inside it.
        cand = [(t, n) for t, n in numbers if _box_dist(t, x, y) <= 1.6 * ch and
                (t.cx - x) * ux + (t.cy - y) * uy <= 0.35 * ch]
        if not cand:
            continue
        t, num = min(cand, key=lambda tn: _box_dist(tn[0], x, y))
        owners = [a for a in anchors if math.hypot(a[1] - x, a[2] - y) < 9 * ch and (a[1] - x) * ux + (a[2] - y) * uy > -ch]
        edge = [b for b in bxs if _on_edge(b, x, y, tol * 2)]
        inbox = [a for a in owners if any(_inside(b, a[1], a[2]) for b in edge)]
        owners = inbox or owners
        if not owners:
            continue
        ref = min(owners, key=lambda a: math.hypot(a[1] - x, a[2] - y))[0]
        if (ref, num) in nodes and dsu.find(nodes[(ref, num)]) != dsu.find(i):
            warnings.append(f'{ref} pin {num} was read on two different wires; kept the first. Check it.')
            continue
        nodes[(ref, num)] = i
        used_ends.add(k)

    # Connector pins ("P2-B12"): the closest unused free wire end.
    for t, conn, pin in conns:
        best = None
        for k, (i, x, y, _) in enumerate(free):
            if k in used_ends:
                continue
            d = _box_dist(t, x, y)
            if d <= 3 * ch and (best is None or d < best[0]):
                best = (d, k, i)
        if best:
            components.setdefault(conn, 'CONNECTOR')
            nodes[(conn, pin)] = best[2]
            used_ends.add(best[1])
        else:
            warnings.append(f'Connector pin {conn}-{pin} has no wire next to it.')

    # Net labels: text lying on/along a wire names that wire's net.
    names, seg_names, seg_readings = {}, {}, {}
    for t, name in labels:
        if not re.fullmatch(r'[A-Z0-9_+\-./:\[\]]{2,40}', name):
            continue
        name = snap_label(name, vocab)
        best = None
        # Printed labels rest on their wire: the baseline (bottom of horizontal text, right side of
        # text rotated to read upward) touches the line, and the wire runs along the label.
        for i, s in enumerate(wires):
            if s.bus or s.horizontal == t.vertical:
                continue
            if s.horizontal:
                along = min(s.x1, t.x1) - max(s.x0, t.x0); d = min(abs(s.y0 - t.y1), abs(s.y0 - t.y0) + 0.15 * ch)
                mid = abs(s.y0 - t.cy); span = t.x1 - t.x0
            else:
                along = min(s.y1, t.y1) - max(s.y0, t.y0); d = min(abs(s.x0 - t.x1), abs(s.x0 - t.x0))
                mid = abs(s.x0 - t.cx); span = t.y1 - t.y0
            if along < 0.5 * span:
                continue
            d = min(d, mid + ch * 0.1)            # a label drawn centred on its wire also counts
            if d <= ch * 0.5 and (best is None or d < best[0]):
                best = (d, i)
        if best is None:                          # fall back to proximity (labels beside short stubs)
            for i, s in enumerate(wires):
                if s.bus:
                    continue
                d = s.dist(t.cx, t.cy) - (t.y1 - t.y0) / 2 if s.horizontal else s.dist(t.cx, t.cy) - (t.x1 - t.x0) / 2
                if d <= ch * 0.8 and (best is None or d < best[0]):
                    best = (d, i)
        if best:
            names.setdefault(dsu.find(best[1]), []).append(name)
            seg_names.setdefault(best[1], []).append(name)
            seg_readings.setdefault(best[1], []).append((name, t))

    # Nets. Printed buses are often drawn with plain-weight lines: one wire group then carries many
    # different labels, one per stub. A pin takes the label on its own stub; otherwise its group's
    # label when the group has exactly one; groups sharing a label are one net.
    nets = {}
    for (ref, pin), i in nodes.items():
        root = dsu.find(i)
        own = [strip_labels[i]] if i in strip_labels else seg_names.get(i)
        group = set(names.get(root, []))
        if own:name = strip_labels[i] if i in strip_labels else choose_wire_label(seg_readings[i], wires[i])
        elif len(group) == 1:name = next(iter(group))
        elif group:name = f'N{root:05d}_{i}'           # unlabeled stub on a multi-signal bus: its own net
        else:name = f'N{root:05d}'
        nets.setdefault(name, []).append((ref, pin))
    nets = {n: sorted(set(m)) for n, m in nets.items()}
    for ref, value, _ in recovered_captions:
        if not any(r == ref for members in nets.values() for r, _ in members):
            warnings.append(f'{ref}: marking {value} read beside its symbol; pin connections remain unrecognized.')
        else:
            warnings.append(f'{ref}: marking {value} read beside its symbol. Check the physical pin connections.')
    floating = [n for n, m in nets.items() if len(m) < 2 and n.startswith('N')]
    if floating:
        warnings.append(f'{len(floating)} pins connect to nothing else that was recognized; review them.')
    missing = [r for r, v in components.items() if not v]
    if missing:
        warnings.append('No part number read for: ' + ', '.join(sorted(missing)))
    # Where each part sits on the sheet (its body centre, else its reference), as fractions of the
    # sheet width, so the generated design can keep the drawing's arrangement.
    width = float(page.gray.shape[1])
    where = {}
    for r, x, y, box in anchors:
        if box is not None and (r not in where or not where[r][2]):
            where[r] = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2, True)
        elif r not in where:
            where[r] = (x, y, False)
    return {
        'components': [{'ref': r, 'value': v or 'UNKNOWN', 'library': PASSIVE.get(re.sub(r'\d.*', '', r)),
                        **({'x': round(where[r][0] / width, 4), 'y': round(where[r][1] / width, 4)} if r in where else {})}
                       for r, v in sorted(components.items())],
        'nets': [{'name': n, 'nodes': [{'ref': r, 'pin': p} for r, p in m]} for n, m in sorted(nets.items())],
        'warnings': warnings,
        'debug': {'segments': len(segs), 'wires': len(wires), 'boxes': len(bxs), 'dots': len(dot_points), 'free_ends': len(free),
                  'tokens': len(toks), 'refs': len(refs), 'numbers': len(numbers), 'labels': len(labels), 'pins': len(nodes)},
    }


# ---------------------------------------------------------------- entry point

def extract(path, cache_dir=None):
    """Image or scanned PDF -> reviewed-ready Circuit with warnings for everything uncertain."""
    import os, tempfile
    from pathlib import Path
    from .ingestion import Circuit
    path = Path(path)
    vector = None
    with tempfile.TemporaryDirectory() as td:
        if path.suffix.lower() == '.pdf':
            import fitz
            with fitz.open(path) as doc:
                if len(doc) < 1:
                    raise ValueError('The PDF has no pages.')
                from .pipeline_profile import enabled, profile
                if enabled():
                    from .vector_pdf import extract_page
                    vector = extract_page(doc[0], dpi=400, minimum=profile()['vector_min_primitives'])
                image = Path(td) / 'page.png'
                doc[0].get_pixmap(dpi=400, colorspace=fitz.csGRAY).save(image)
                extra = [f'PDF has {len(doc)} pages; page 1 was recognized.'] if len(doc) > 1 else []
            page = prepare(image)
        else:
            extra = []
            page = prepare(path)
    page.notes += extra
    if vector is not None:
        page.vector = vector.transformed(page.affine)
        page.notes.append(f'Native PDF fast path: {vector.primitive_count} vector primitives; exact text and geometry transformed into working pixels.')
    result = recognize(page, tokens(page))
    graph = {'components': result['components'], 'nets': result['nets'],
             'sheet_aspect': round(page.gray.shape[1] / page.gray.shape[0], 6)}
    warnings = result['warnings']
    cache = Path(cache_dir or os.getenv('STATE_ROOT') or Path(__file__).resolve().parents[1] / '.state')
    try:
        from . import orcad_capture
        if orcad_capture.available():
            graph, notes = orcad_capture.check(graph, cache)
            warnings = notes + warnings
    except Exception as e:                 # library check is an aid; recognition stands without it
        warnings.append(f'OrCAD library check skipped: {e}')
    nets = [n for n in graph['nets'] if n['nodes']]
    if not graph['components']:
        raise ValueError('no part references with part numbers were readable. ' + ' '.join(page.notes))
    warnings.insert(0, f"Recognized {len(graph['components'])} parts and {sum(len(n['nodes']) for n in nets)} pin connections "
                       f"in {len(nets)} nets. Check them against the source before generating the design.")
    return Circuit.model_validate({**graph, 'nets': nets, 'warnings': warnings})
