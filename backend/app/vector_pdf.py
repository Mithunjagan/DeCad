"""Native PDF geometry in raster coordinates, including crop/rotation transforms.

    Drawing paths include symbol outlines as well as wires. The downstream
    body classifier must remove those outlines before electrical tracing.
"""
from dataclasses import dataclass, field
import math

import numpy as np


@dataclass
class VectorPage:
    lines: list = field(default_factory=list)  # (x0,y0,x1,y1,width)
    curves: list = field(default_factory=list)
    dots: list = field(default_factory=list)
    text: list = field(default_factory=list)
    primitive_count: int = 0

    def transformed(self, affine):
        matrix = np.asarray(affine, dtype=float).reshape(2, 3)
        point = lambda x, y: tuple((matrix @ [x, y, 1]).tolist())
        scale = math.hypot(matrix[0, 0], matrix[1, 0])
        lines = [(*point(x0, y0), *point(x1, y1), width * scale)
                 for x0, y0, x1, y1, width in self.lines]
        texts = []
        for item in self.text:
            x0, y0, x1, y1 = item['bbox']
            corners = [point(x, y) for x, y in ((x0,y0),(x0,y1),(x1,y0),(x1,y1))]
            direction = matrix[:, :2] @ item['direction']
            texts.append({**item, 'bbox': (min(p[0] for p in corners), min(p[1] for p in corners),
                                          max(p[0] for p in corners), max(p[1] for p in corners)),
                          'direction': tuple(direction / max(1e-9, np.linalg.norm(direction)))})
        return VectorPage(lines, [[point(*p) for p in curve] for curve in self.curves],
                          [(*point(x,y), radius*scale) for x,y,radius in self.dots],
                          texts, self.primitive_count)


def extract_page(page, dpi=400, minimum=30):
    """Return None for raster PDFs. Filled compact circles are dot candidates.

    PyMuPDF extraction uses unrotated page coordinates; get_pixmap uses rotated
    coordinates. Apply page.rotation_matrix before the DPI scale.
    """
    import fitz
    drawings = page.get_drawings()
    result = VectorPage()
    for path in drawings:
        width = float(path.get('width') or 0.5)
        path_curves = []
        for item in path['items']:
            kind = item[0]
            if kind == 'l':
                result.lines.append((*item[1], *item[2], width))
                result.primitive_count += 1
            elif kind in ('re', 'qu'):
                shape = item[1]
                points = [shape.tl, shape.tr, shape.br, shape.bl] if kind == 're' else [shape.ul, shape.ur, shape.lr, shape.ll]
                for a, b in zip(points, points[1:] + points[:1]):
                    result.lines.append((*a, *b, width))
                    result.primitive_count += 1
            elif kind == 'c':
                curve = [tuple(p) for p in item[1:5]]
                result.curves.append(curve)
                path_curves.append(curve)
                result.primitive_count += 1
        rect = path['rect']
        # A standard circle is four cubic Beziers. Unfilled pin bubbles and
        # semicircle bridges are deliberately excluded from solder dots.
        if (path.get('fill') is not None and len(path_curves) == 4
                and 0.8 <= rect.width / max(1e-9, rect.height) <= 1.25
                and 0.5 <= rect.width <= 10 and max(path['fill']) < 0.5):
            result.dots.append(((rect.x0+rect.x1)/2, (rect.y0+rect.y1)/2, rect.width/2))
    if result.primitive_count <= minimum:
        return None
    dictionary = page.get_text('dict', flags=fitz.TEXT_PRESERVE_WHITESPACE)
    directions = {(bi, li): tuple(line['dir']) for bi, block in enumerate(dictionary['blocks'])
                  for li, line in enumerate(block.get('lines', []))}
    # words provides individual exact boxes rather than estimated subdivisions
    # of a proportional-font span. Both extraction calls share block/line IDs.
    for x0, y0, x1, y1, word, bi, li, _ in page.get_text('words'):
        if word.strip():
            result.text.append({'text': word, 'bbox': (x0,y0,x1,y1),
                                'direction': directions.get((bi, li), (1.,0.))})
    m = page.rotation_matrix * fitz.Matrix(dpi/72, dpi/72)
    return result.transformed([[m.a,m.c,m.e], [m.b,m.d,m.f]])


def segments(vector):
    """Exact orthogonal line primitives, coalesced only at identical axes."""
    from .digital_vision import Seg
    rows = {}
    for x0,y0,x1,y1,width in vector.lines:
        # KiCad and other plotters draw glyph strokes as paths as well as
        # searchable text. Those strokes are not wire primitives.
        if any(t['bbox'][0]-.5<=min(x0,x1) and max(x0,x1)<=t['bbox'][2]+.5
               and t['bbox'][1]-.5<=min(y0,y1) and max(y0,y1)<=t['bbox'][3]+.5 for t in vector.text):
            continue
        horizontal, vertical = abs(y1-y0) < .05, abs(x1-x0) < .05
        if not (horizontal or vertical):
            continue  # Diagonal paths are kept in VectorPage for graph tracing.
        if horizontal:
            key, span = (True, round((y0+y1)/2, 4)), (min(x0,x1),max(x0,x1),width)
        else:
            key, span = (False, round((x0+x1)/2, 4)), (min(y0,y1),max(y0,y1),width)
        rows.setdefault(key, []).append(span)
    merged = []
    for (horizontal, across), spans in rows.items():
        current = None
        for start,end,width in sorted(spans):
            if current and start <= current[1] + .05:
                current[1] = max(current[1], end)
                current[2] = max(current[2], width)
            else:
                if current:merged.append((horizontal,across,*current))
                current = [start,end,width]
        if current:merged.append((horizontal,across,*current))
    result = []
    median = float(np.median([s[4] for s in merged])) if merged else 1.
    for horizontal,across,start,end,width in merged:
        coords = (start,across,end,across) if horizontal else (across,start,across,end)
        result.append(Seg(*(round(c) for c in coords), width, horizontal, width > 1.7*median and end-start > 200))
    return result


def tokens(vector):
    from .digital_vision import Token
    return [Token(row['text'], 1., *(round(c) for c in row['bbox']), abs(row['direction'][1]) > .7) for row in vector.text]
