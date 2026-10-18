"""Compact CRNN text reader for printed schematic tokens (pin numbers, net labels, part numbers).

Old plotter-drawn schematics use a stroke font close to OpenCV's Hershey fonts, so the model is
trained on synthetic renders of schematic-style strings (with scan blur, noise, stroke weight and
skew) plus optional real crops. It runs on CPU at inference and fits a 4 GB GPU for training.

  python training/schematic_ocr.py train --out checkpoints/schematic-ocr [--real crops.jsonl] [--steps 6000] [--init old-folder]
  python training/schematic_ocr.py eval --model checkpoints/schematic-ocr --data crops.jsonl
  python training/schematic_ocr.py export --model checkpoints/schematic-ocr     # model.pt -> model.onnx for the backend
"""
from __future__ import annotations
import argparse, json, math, random, time
from pathlib import Path
import cv2
import numpy as np

CHARS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-+[]:/.<>=~*#_'
H = 32
MAX_W = 256
FONTS = [cv2.FONT_HERSHEY_SIMPLEX, cv2.FONT_HERSHEY_PLAIN, cv2.FONT_HERSHEY_DUPLEX, cv2.FONT_HERSHEY_COMPLEX_SMALL]


# ---------------------------------------------------------------- synthetic schematic strings

def random_text(rng):
    k = rng.random()
    L = lambda n: ''.join(rng.choice('ABCDEFGHIJKLMNOPRSTUVWXYZ') for _ in range(n))
    if k < 0.30:return str(rng.randint(1, 99 if rng.random() < 0.85 else 999))                 # pin numbers
    if k < 0.55:return L(rng.randint(1, 6)) + str(rng.randint(0, 31))                          # net labels DD16, AAA14
    if k < 0.65:return rng.choice(['74F', '74LS', '74HC', '74BCT', '74S', '74ALS']) + str(rng.choice([0, 2, 4, 8, 10, 32, 74, 85, 151, 157, 161, 163, 174, 181, 182, 194, 240, 244, 257, 298, 374, 2244]))
    if k < 0.72:return rng.choice('UURRCJPS') + str(rng.randint(1, 120))                       # references
    if k < 0.80:return f"{rng.choice('PJ')}{rng.randint(1, 3)}-{rng.choice('ABC')}{rng.randint(1, 32)}"  # connector pins
    if k < 0.86:return rng.choice(['1K00', '330R', '510R', '470R', '120R', '10K', '4K7', '+5V', 'GND', 'VCC'])
    if k < 0.93:return L(rng.randint(2, 4)) + '[' + str(rng.randint(0, 3)) + ':' + str(rng.randint(4, 23)) + ']'
    return rng.choice(['-', '~', '']) + L(rng.randint(2, 7)) + rng.choice(['', str(rng.randint(0, 9))])     # control signals -CCEN, SEQ1


def render(text, rng):
    font = rng.choice(FONTS)
    scale = rng.uniform(0.9, 1.6)
    thick = rng.choice([1, 1, 2, 2, 3])
    (w, h), base = cv2.getTextSize(text, font, scale, thick)
    pad = rng.randint(2, 8)
    img = np.full((h + base + 2 * pad, w + 2 * pad), 255, np.uint8)
    cv2.putText(img, text, (pad, pad + h), font, scale, 0, thick, cv2.LINE_AA if rng.random() < .5 else cv2.LINE_8)
    if rng.random() < 0.5:                                   # horizontal squeeze/stretch of plotter fonts
        img = cv2.resize(img, None, fx=rng.uniform(0.75, 1.25), fy=1.0)
    if rng.random() < 0.4:                                   # slight shear
        sh = rng.uniform(-0.15, 0.15)
        m = np.float32([[1, sh, 0], [0, 1, 0]])
        img = cv2.warpAffine(img, m, (img.shape[1] + int(abs(sh) * img.shape[0]), img.shape[0]), borderValue=255)
    return degrade(img, rng)


def degrade(img, rng):
    """Scan artefacts: downsample/upsample blur, noise, threshold dropouts."""
    if rng.random() < 0.6:
        f = rng.uniform(0.25, 0.7)
        small = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        img = cv2.resize(small, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_CUBIC)
    if rng.random() < 0.5:
        img = cv2.GaussianBlur(img, (0, 0), rng.uniform(0.3, 1.4))
    if rng.random() < 0.5:
        img = np.clip(img.astype(np.float32) + np.random.normal(0, rng.uniform(3, 25), img.shape), 0, 255).astype(np.uint8)
    if rng.random() < 0.35:
        _, img = cv2.threshold(img, rng.randint(90, 200), 255, cv2.THRESH_BINARY)
    return img


def normalize(img):
    """Grayscale crop (ink dark) -> float32 [1, H, W<=MAX_W], ink bright."""
    if img.ndim == 3:img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = img.shape
    nw = max(8, min(MAX_W, int(round(w * H / max(h, 1)))))
    x = cv2.resize(img, (nw, H), interpolation=cv2.INTER_AREA if h > H else cv2.INTER_CUBIC)
    return (255 - x).astype(np.float32)[None] / 255.0


def clean_label(t):
    t = t.upper().replace(' ', '')
    return ''.join(c for c in t if c in CHARS)


# ---------------------------------------------------------------- model

def build_model():
    import torch.nn as nn

    class CRNN(nn.Module):
        def __init__(self, n):
            super().__init__()
            c = lambda i, o: [nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(inplace=True)]
            self.cnn = nn.Sequential(*c(1, 32), nn.MaxPool2d(2), *c(32, 64), nn.MaxPool2d(2),
                                     *c(64, 128), *c(128, 128), nn.MaxPool2d((2, 1)),
                                     *c(128, 192), nn.MaxPool2d((2, 1)), *c(192, 192), nn.MaxPool2d((2, 1)))
            self.rnn = nn.LSTM(192, 128, num_layers=2, bidirectional=True, batch_first=True, dropout=0.1)
            self.fc = nn.Linear(256, n + 1)

        def forward(self, x):                                # x: [B,1,32,W]
            f = self.cnn(x).squeeze(2).permute(0, 2, 1)       # [B, W/4, 192]
            return self.fc(self.rnn(f)[0])                    # [B, T, n+1]

    return CRNN(len(CHARS))


def decode(logits):
    out = []
    for seq in logits.argmax(-1).tolist():
        s, prev = [], 0
        for k in seq:
            if k != prev and k != 0:s.append(CHARS[k - 1])
            prev = k
        out.append(''.join(s))
    return out


def batchify(imgs):
    import torch
    W = max(i.shape[2] for i in imgs); W = int(math.ceil(W / 4) * 4)
    x = np.zeros((len(imgs), 1, H, W), np.float32)
    for k, i in enumerate(imgs):x[k, :, :, :i.shape[2]] = i
    return torch.from_numpy(x)


# ---------------------------------------------------------------- train / eval

def load_real(path):
    """jsonl of {"image": crop path, "text": label} (labels from verified readings only)."""
    rows = []
    if path:
        base = Path(path).parent
        for line in Path(path).read_text(encoding='utf-8').splitlines():
            r = json.loads(line)
            img = cv2.imread(str(base / r['image']), cv2.IMREAD_GRAYSCALE)
            if img is not None and clean_label(r['text']):rows.append((img, clean_label(r['text'])))
    return rows


def train(args):
    import torch
    import torch.nn.functional as F
    rng = random.Random(args.seed); torch.manual_seed(args.seed)
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = build_model()
    if args.init:                                            # fine-tune: keep what synthetic training learned
        model.load_state_dict(torch.load(Path(args.init) / 'model.pt', map_location='cpu'))
    model = model.to(dev)
    real = load_real(args.real)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=5e-4 if args.init else 2e-3, total_steps=args.steps, pct_start=0.1)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    t0, log = time.time(), []
    for step in range(1, args.steps + 1):
        texts, imgs = [], []
        for _ in range(args.batch):
            if real and rng.random() < args.real_ratio:
                img, text = rng.choice(real); img = degrade(img, rng) if rng.random() < .5 else img
            else:
                text = random_text(rng); img = render(text, rng); text = clean_label(text)
            texts.append(text); imgs.append(normalize(img))
        x = batchify(imgs).to(dev)
        logits = model(x)
        lp = F.log_softmax(logits, -1).permute(1, 0, 2)
        targets = torch.tensor([CHARS.index(c) + 1 for t in texts for c in t], dtype=torch.long)
        loss = F.ctc_loss(lp, targets, torch.full((len(texts),), lp.shape[0], dtype=torch.long),
                          torch.tensor([len(t) for t in texts], dtype=torch.long), zero_infinity=True)
        opt.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0); opt.step(); sched.step()
        if step % 200 == 0 or step == args.steps:
            model.eval()
            with torch.no_grad():
                vr = random.Random(999); vt = [random_text(vr) for _ in range(256)]
                pred = decode(model(batchify([normalize(render(t, vr)) for t in vt]).to(dev)).cpu())
                acc = sum(p == clean_label(t) for p, t in zip(pred, vt)) / len(vt)
            model.train()
            mem = torch.cuda.max_memory_allocated() / 2**20 if dev == 'cuda' else 0
            log.append({'step': step, 'loss': float(loss), 'synthetic_val_acc': acc, 'elapsed_s': round(time.time() - t0), 'peak_mib': round(mem)})
            print(json.dumps(log[-1]), flush=True)
    torch.save(model.state_dict(), out / 'model.pt')
    (out / 'config.json').write_text(json.dumps({'chars': CHARS, 'height': H, 'max_width': MAX_W, 'arch': 'crnn-v1',
                                                 'steps': args.steps, 'real_samples': len(real), 'init': args.init,
                                                 'real_data': args.real, 'log': log}, indent=2))


def export(args):
    """model.pt -> model.onnx (input "image" [1,1,32,W], W a multiple of 4), as the backend reads it."""
    import torch
    model = build_model()
    model.load_state_dict(torch.load(Path(args.model) / 'model.pt', map_location='cpu'))
    model.eval()
    torch.onnx.export(model, torch.zeros(1, 1, H, 128), str(Path(args.model) / 'model.onnx'), input_names=['image'],
                      output_names=['logits'], dynamic_axes={'image': {3: 'width'}, 'logits': {1: 'steps'}}, opset_version=17)


class Reader:
    """CPU inference wrapper used by the recognizer."""
    def __init__(self, folder):
        import torch
        self.torch = torch
        self.model = build_model()
        self.model.load_state_dict(torch.load(Path(folder) / 'model.pt', map_location='cpu'))
        self.model.eval()

    def read(self, crops):
        if not crops:return []
        with self.torch.no_grad():
            logits = self.model(batchify([normalize(c) for c in crops]))
            probs = logits.softmax(-1)
            conf = probs.max(-1).values.min(-1).values.tolist()
        return list(zip(decode(logits), conf))


def evaluate(args):
    rows = load_real(args.data)
    r = Reader(args.model)
    pred = r.read([img for img, _ in rows])
    ok = sum(p == t for (p, _), (_, t) in zip(pred, rows))
    print(json.dumps({'samples': len(rows), 'exact': ok, 'accuracy': ok / max(1, len(rows))}))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('train'); t.add_argument('--out', required=True); t.add_argument('--real'); t.add_argument('--real-ratio', type=float, default=0.3)
    t.add_argument('--steps', type=int, default=6000); t.add_argument('--batch', type=int, default=64); t.add_argument('--seed', type=int, default=1)
    t.add_argument('--init', help='folder with a model.pt to fine-tune from')
    e = sub.add_parser('eval'); e.add_argument('--model', required=True); e.add_argument('--data', required=True)
    x = sub.add_parser('export'); x.add_argument('--model', required=True)
    a = ap.parse_args()
    {'train': train, 'eval': evaluate, 'export': export}[a.cmd](a)
