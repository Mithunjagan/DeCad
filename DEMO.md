# DeCad demo: schematic image / scanned PDF → native OrCAD Capture .DSN

> Historical workflow notes. Use the [current setup guide](docs/SETUP.md) and
> [recorded results](docs/RESULTS.md) for the pinned production profile and current published statistics.
> Older timings and experimental model settings below retain their original scope.

## Before the panel (5 minutes)

1. Close Docker Desktop (not needed; it holds port 3100 and RAM).
2. Double-click the **DeCad** icon on the Desktop / Start Menu (created once with
   `powershell -ExecutionPolicy Bypass -File install-desktop-app.ps1`). It starts the backend and frontend
   if they are not running and opens DeCad in its own app window (no tabs or address bar).
   Same as `powershell -ExecutionPolicy Bypass -File start-native.ps1`.
   Check the header badge reads **Automatic recognition** with the CUDA runtime (see [GPU OCR](README.md#gpu-accelerated-ocr)).
3. Create a project (e.g. `Demo`).
4. Recognition takes about 1 minute per sheet with GPU OCR (about 2 minutes on CPU). Run each demo input
   once beforehand so the project already holds a finished design, then repeat one live.

Demo inputs:

| Input | File | What it shows |
|---|---|---|
| Clear scan | `samples/orcad/Sample 4.jpg.jpeg` | standard path |
| Blurry 1600 px sheet | `samples/orcad/Sample 2.jpg.jpeg` | automatic low-resolution enhancement |
| Scanned PDF | `tools/eval/degraded/Sample 4-scan300.pdf` | 300 dpi office scan, rotated, noisy, JPEG |
| Blurred / low-dpi PDF | `tools/eval/degraded/Sample 4-blur300.pdf`, `Sample 4-scan200.pdf` | stress cases |

## Fastest live flow: Libraries & footprints tab (one drop, about 2 minutes)

1. Open a project, click the **Libraries & footprints** tab.
2. Drop the blueprint (image or PDF) on **Blueprint → OrCAD Capture**. A progress bar and timer run while
   DeCad reads the drawing, matches parts, writes the .DSN and reopens it to verify every pin.
3. The **OrCAD Capture design** dialog opens by itself: verified badge, parts, pins, nets, **PCB footprints
   N/M**, and the drawing read back from the saved .DSN.
4. Scroll down in the dialog: **Physical netlist** (read back from the saved .DSN) lists every net with
   its `part.pin` connections and every part with its PCB footprint; filter it (`U12`, `U12.5`, a net
   name) and download **PCB Editor netlist (.net)** or **Netlist (.csv)**.
5. **Open in OrCAD Capture**: Capture opens the *project* only. To see the schematic, in the project
   tree expand `<design>.dsn` → `SCHEMATIC1` → double-click **`PAGE1`**, then *View → Zoom → All*.
   Recognized source coordinates and page orientation are preserved; overlap avoidance can move
   symbols, and merged body detections still need review. Capture's own netlist: select the `.dsn` in the tree →
   *Tools → Create Netlist → PCB* (every part has a PCB Footprint). OrCAD PCB Editor: *File → Import →
   Logic/Netlist → Other* with the downloaded `.net`.

### Show "add any design and footprints" (1 minute, already loaded in the `local` workspace)

For the new automatic component flow, enter **Timer:NE555P** in the unified browser,
choose an unused reference and press **Find component and add to project**. It
searches KiCad/OrCAD sources, acquires permitted missing assets, validates pin/pad
mapping, and stores a project-local footprint library. Real local, public-network,
API and UI acceptance runs passed. Additional providers require authorization;
unsupported Allegro geometry stays explicit. See [component library details](COMPONENT_LIBRARIES.md).

- Drop an existing Capture design on **Add to the library**, e.g. Cadence's own sample
  `D:	ools\capture\samples\PCB-Layout\Bench\BENCH.DSN`. All 65 packages are extracted into
  `BENCH_parts.olb` with their footprints, a preview of the design appears, and **Open in OrCAD Capture**
  opens it.
- Drop footprints: single `.psm/.dra/.pad` files or a `.zip` of a footprint folder (e.g. the BENCH
  `allegrolib` folder zipped: 76 files). Search the catalog (3,290 footprints) in the tab.
- Add a mapping row, e.g. `74F174 → soic16`, then convert again: that part now gets `soic16`
  (source "part map"), and the design zip carries the used footprint files and libraries.
- Any recognized part number found in a workspace library is placed from it (the result dialog lists
  "Workspace libraries used").

If OrCAD Capture says **"projects that were not properly closed"** on start, a previous Capture session
was killed. Click **Cancel** (nothing is deleted), and close Capture with its window's X button.

## Live flow from the assistant (no settings changed between inputs)

1. Attach the file in the assistant panel (**+**), type `convert to OrCAD`, send.
2. The **Review circuit** dialog opens. The yellow notes start with the **Input assessment**, which
   says what the system measured and what it did automatically. For example:
   - *clear scan … no enhancement needed*
   - *low-resolution/blurry sheet … enhanced automatically (6.2x super-sampling, stroke-preserving binarization, grayscale OCR)*
   - *blurred or greyscale scan (66% soft stroke edges) … enhanced automatically*
3. Tick the review box, then **Generate verified OrCAD .DSN**.
4. The **OrCAD Capture design** dialog shows:
   - **Verified**: the saved .DSN was reopened through Capture's own database and every pin's net was compared with the recognized circuit.
   - The number of parts, checked pin connections and nets.
   - Automatic corrections, such as misread pins removed because the part has no such pin.
   - A drawing rendered from the saved .DSN.
5. **Open in OrCAD Capture** launches the design in the installed OrCAD X Capture.
   **Download design (.zip)** gives the `.DSN`, the generated `.OLB`, the `.opj` and the verification record.

## Answers to the panel's criteria

- **Accuracy (validated):** measured against hand-transcribed ground truth, scored from the saved .DSN
  itself (not from intermediate output). Reproduce with
  `backend\.venv\Scripts\python.exe tools\eval\run_eval.py 1 2 3 4 5`. The accepted table is in
  `tools/eval/results/claude-ocr3-gate/report.md` and below.
- **Automation:** one **Automatic** mode for every input. The system measures resolution, character
  height, stroke blur and skew, then picks the enhancement and recognizer itself. There is no manual
  switch between blurry and clear inputs.
- **Your own libraries and footprints:** any `.OLB`, any existing `.DSN` (its parts are extracted),
  footprint files and a part map are added in one drop and used by every generated design; each part
  gets a PCB footprint that is verified in the reopened .DSN.
- **Scanned / blurry PDFs:** PDFs are rendered at 400 dpi, assessed and enhanced the same way.
  `tools/eval/make_degraded.py` builds realistic scans (rotation, blur, sensor noise, lamp falloff,
  JPEG) from a sample so the effect can be measured against the same ground truth.

## Measured results (2026-10-18)

| Input | Parts found (precision) | Values | Labelled pin→net exact | .DSN | Time (GPU) |
|---|---|---|---|---|---|
| Sample 1 (clear) | 24/28 = 86% (100%) | 100% | **51/56 = 91%** | verified, 24 parts, 277 pins | 53 s |
| Sample 3 (clear) | 30/34 = 88% (97%) | 93% | **59/69 = 86%** | verified, 43 parts, 499 pins | 73 s |
| Sample 4 (clear) | 25/30 = 83% (100%) | 100% | **64/72 = 89%** | verified, 25 parts, 276 pins | 49 s |
| Sample 5 (clear) | 22/25 = 88% (100%) | 95% | **39/48 = 81%** | verified, 27 parts, 264 pins | 56 s |
| **Sample 2 (1600 px, ~5 px text)** | TC514100 7/16, 74F374 4/8, 74F244 2/4 | – | not transcribed | verified, 21 parts, 107 pins | 53 s |
| **Sample 4 scanned PDF, 300 dpi** | 25/30 = 83% (86%) | 100% | 38/72 = 53% | verified, 29 parts, 260 pins | 58 s |
| **Sample 4 scanned PDF, 200 dpi** | 18/30 = 60% (90%) | 100% | 0/72 | verified, 20 parts, 62 pins | 54 s |
| **Sample 4 blurred PDF (σ=2 px @300 dpi)** | 12/30 = 40% (80%) | 100% | 0/72 | verified, 15 parts, 45 pins | 55 s |

Clear sheets: **213/245 labelled pins exact (87%)**, up from 158/245 in the previous accepted gate.
Accepted gate: `tools/eval/results/claude-ocr3-gate/` (fresh GPU OCR on all eight inputs). All eight
designs verify on reopen and all eight Capture PCB netlists contain zero error entries.

Ground truth: every part on sheets 1 and 4 and the listed parts on 3 and 5, plus 245 explicitly labelled
pin→net checkpoints, transcribed by hand from the full-resolution scans (`tools/eval/ground_truth`).
Scores are read back from the saved .DSN. Samples 1 and 3 also supplied text crops to the fine-tuned
reader; 2, 4 and 5 were held out in this gate. New training on these sheets must
be reported separately. Measured time was 49–73 seconds per sheet with GPU OCR.

Honest limits: recognition is not complete. Labelled pin→net checkpoints are 81–91% exact on
the annotated clear sheets and 0–53% on degraded scans. Scan at 300 dpi or better;
blurred and 200 dpi inputs still require substantial review. Every design should be reviewed before use. The review
dialog and the verification record list what is uncertain.
