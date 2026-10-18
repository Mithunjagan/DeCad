"""Make scanned/blurry PDF versions of a sample sheet for robustness tests.

Each variant simulates a real office scan: lower resolution, slight rotation, optical blur, sensor
noise, uneven lighting and JPEG compression, wrapped in a single-page A3 PDF. The ground truth of the
source sample applies unchanged, so run_eval.py can score the variants directly.

  python tools/eval/make_degraded.py 4 --out tools/eval/degraded
"""
import argparse
from pathlib import Path
import cv2
import fitz
import numpy as np

from run_eval import SAMPLES

# name: (dpi of the simulated scan, rotation degrees, blur sigma at scan dpi, noise sigma, jpeg quality)
VARIANTS = {
    'scan300': (300, 0.8, 0.8, 6, 60),
    'blur300': (300, -1.2, 2.0, 8, 45),
    'scan200': (200, 0.5, 1.0, 6, 50),
}


def degrade(gray, src_dpi, dpi, angle, blur, noise, quality, seed=0):
    rng = np.random.default_rng(seed)
    f = dpi / src_dpi
    img = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    h, w = img.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    img = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=255)
    img = cv2.GaussianBlur(img, (0, 0), blur).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    shade = 1.0 - 0.12 * ((xx / w - 0.3) ** 2 + (yy / h - 0.6) ** 2)      # scanner lamp falloff
    img = img * shade + rng.normal(0, noise, img.shape)
    img = np.clip(img, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('samples', nargs='*', type=int, default=[4])
    ap.add_argument('--out', default=str(Path(__file__).parent / 'degraded'))
    ap.add_argument('--src-dpi', type=float, default=600.0)    # 9917 px across an A3 sheet
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for i in a.samples:
        gray = cv2.imread(str(SAMPLES / f'Sample {i}.jpg.jpeg'), cv2.IMREAD_GRAYSCALE)
        for name, (dpi, angle, blur, noise, q) in VARIANTS.items():
            jpg = degrade(gray, a.src_dpi, dpi, angle, blur, noise, q, seed=i)
            doc = fitz.open()
            page = doc.new_page(width=1190.55, height=841.89)           # A3 landscape, points
            page.insert_image(page.rect, stream=jpg)
            path = out / f'Sample {i}-{name}.pdf'
            doc.save(path)
            print(path, f'{len(jpg) / 1e6:.1f} MB')


if __name__ == '__main__':
    main()
