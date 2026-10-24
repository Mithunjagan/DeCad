# Native OrCAD Capture .DSN generation

> Historical workflow notes. Use the [current setup guide](docs/SETUP.md) and
> [recorded results](docs/RESULTS.md) for the pinned production profile and current published statistics.
> Older timings and experimental model settings below retain their original scope.

DeCad writes **native OrCAD Capture designs (.DSN)** through Capture's own database API, then
reopens every saved design and checks it pin by pin before returning it. This needs a local OrCAD
installation (tested with OrCAD X 26.1 at `D:\tools`; set `ORCAD_ROOT` if yours is elsewhere) and
the native backend (`start-native.ps1`). The Docker backend cannot reach a Windows OrCAD install.

## Pipeline (one click: image or PDF → verified .DSN)

0. **Input assessment** (automatic, no mode switch): resolution, character height, share of soft
   (blurred) stroke edges and skew are measured. Tiny/blurry sheets (e.g. a 1600 px JPEG) and blurred or
   greyscale scans/PDFs get super-sampling, stroke-preserving binarization, OCR on smoothed grayscale,
   low-resolution character repair (`UPO`→U70, `7AF244`→74F244) and part numbers snapped to clean
   readings elsewhere on the sheet. IC bodies with a legible part number but unreadable reference are
   kept as `U_1, U_2…` for annotation in Capture. The assessment is the first review note.
1. **Recognition** (`backend/app/digital_vision.py`): deskew/upscale, wire and junction tracing,
   word OCR in both orientations, IC bodies, then each IC pin is read directly along its wire
   (pin number next to the body edge, net label further out). Net names are corrected against the
   sheet's own signal families (`DD1..DD19`, `ADDA0..15`, inferred from all readings).
2. **Library check** (`orcad_capture.check`): part numbers are matched against the workspace
   libraries (see below) and every installed Capture library with OCR-aware correction (`AM291C → AM2910`, `74F24U → 74F240`); pins the part
   does not have are dropped with a warning.
3. **Design generation** (`orcad_writer.tcl`): each part is placed from its Capture library; parts
   with no library match get a **generated symbol** in `DECAD_GENERATED.OLB` (shipped with the
   design). Every connected pin gets a wire stub with its net alias, and every part a PCB footprint.
4. **Reopen verification** (`orcad_dump.tcl`): the saved DSN is reopened and every pin's net is
   compared with the source graph. Recognition noise that verification rejects (a misread pin on a
   fixed power pin, a pin listed on two nets, a pin the part lacks) is removed, the design rebuilt,
   and each removal reported in `corrections`.
5. **Layout**: recognized source coordinates and sheet orientation are preserved; the writer
   moves overlapping symbols to nearby free space. Missing coordinates go in a bottom strip.
   Source positions can still be wrong or shared when recognition merges bodies. On S1,
   placement RMS relative to recognized centres improved from 17.27% to 1.49% of sheet width.
6. **Physical netlist** (`physical_netlist`): read back from the reopened .DSN (parts with PCB
   footprints, nets with `part.pin`, implicit power pins included) and written as `netlist.json`,
   `netlist.csv` and `<design>.net` (OrCAD PCB Editor / Allegro third-party "Telesis" format).
   Routes: `GET /projects/{pid}/orcad/netlist`, `GET /projects/{pid}/orcad/file?name=`.
7. **Preview** (`orcad_render.tcl` + `orcad_capture.svg`): the saved design is read back from the
   DSN (real symbol graphics, pins, wires, aliases) and rendered as SVG for the browser.

## Workspace libraries and PCB footprints

The unified component browser also supports **Find component and add to project**:
local KiCad/OrCAD search, authorized asset acquisition, pin/pad validation, verified
cache and project-local symbol/footprint placement. Real local and public-network
NE555P acceptance runs both pass 8-pin/8-pad and native footprint checks. Native
OLB package extraction/export is verified on original fixtures with Capture 26.1;
Allegro geometry conversion is explicitly unavailable. See [the support matrix](COMPONENT_LIBRARIES.md).

The **Libraries & footprints** tab (`frontend/app/LibraryPanel.js`, backend `orcad_library.py`) adds a
team's own material to every generated design. It is stored per workspace in
`backend/workspaces/<user>/.libraries/` and shared by all projects of that workspace.

| You add | What happens |
|---|---|
| Capture symbol library `.OLB` | indexed; its packages are preferred over the installed libraries when a part number matches |
| Existing Capture design `.DSN` (any, e.g. Cadence's `BENCH.DSN`) | every placed package is copied into `<name>_parts.OLB` (`orcad_extract.tcl`), with the footprint the design used; a preview is rendered and the design can be opened in Capture |
| Footprints `.psm .dra .pad .bsm .fsm .ssm .osm .mdd`, KiCad `.kicad_mod` | added to the footprint catalog; files a design uses ship in its zip under `footprints/` |
| Part map `.csv` (key, footprint, optional symbol) or rows typed in the tab | key = reference (`U12`), part number (`74F174`) or package; symbol override `Library.olb:Package` |
| `.zip` of any of the above | unpacked and processed file by file |

Every placed part gets a **PCB Footprint** (`SetPCBFootprint`, read back on reopen), chosen in this order:
part map → the symbol library package's own footprint (26,463 installed packages carry one) → a standard
footprint from the installed OrCAD PCB library (`<root>/share/pcb/pcb_lib/symbols`, 3,255 footprints) by
package type and pin count (`dipN_3`/`dipN_6`, `res400`, `cap196`, `din96abcv`, …). A part with no
confident match gets a generic 0.1" header with its pin count (`blkcon100vhtm2oew200N`), listed as
**placeholder (review)**, because Capture's PCB netlister stops (ORCAP-36002 / ORNET-1193) at any part without
a footprint. Verified: `pstswp` (Tools → Create Netlist → PCB) completes with 0 errors on Sample 2.

The KiCad path (Review → apply to KiCad) works the same way: a connector with numbered pins gets
`Connector_Generic:Conn_01xNN` / `Conn_02xNN_Odd_Even`; a part no KiCad library has (DIN 41612 `A5/B26/C20`
pins, 74F parts) gets a generated symbol `DeCad:<value>_<ref>` embedded in the schematic with exactly its
recognized pins. The design zip contains
`footprints.csv` (reference, value, library, package, footprint, source) and the workspace libraries used
(`libraries/*.olb`, listed in the `.opj`).

Library routes: `GET /library`, `POST /library/upload?name=` (raw body, ≤200 MB), `DELETE /library/{symbols|designs|footprints|partmap}/{name}`,
`POST /library/partmap {key, footprint, symbol}`, `GET /library/footprints?q=`, `GET /library/designs/{name}/preview.svg`,
`POST /library/designs/{name}/open`. Smoke test: `tools/eval/smoke_library.py`.

## API (all under the normal session)

| Method | Route | Result |
|---|---|---|
| POST | `/projects/{pid}/orcad/auto` `{"attachment": "references/x.jpg", "recognition_mode": "auto"}` | Recognize, generate, verify, save. Returns `{status, circuit, warnings}` |
| POST | `/projects/{pid}/export/orcad-dsn` `{"circuit": {...}, "source": "..."}` | Reviewed circuit → verified DSN (zip) |
| GET | `/projects/{pid}/export/orcad-dsn` | Current KiCad schematic → verified DSN (zip) |
| GET | `/projects/{pid}/orcad` | `{available, capture, design: status}` for the project's last design |
| GET | `/projects/{pid}/orcad/preview.svg` | Rendered preview of the saved DSN |
| GET | `/projects/{pid}/orcad/download` | Zip: `.DSN`, generated `.OLB`, circuit, mapping, verification, preview |
| POST | `/projects/{pid}/orcad/open` | Opens the DSN in the installed OrCAD Capture |

`status` fields: `design, size, passed, components, checked_pins, nets, rendered_parts,
generated_symbols, corrections, substitutions, implicit_power_pins, footprints {assigned, total, placed,
sources, without, not_in_library}, user_libraries, source, sha256`.

## Measured accuracy (2026-10-18, `tools/eval/run_eval.py`)

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
reader; 2, 4 and 5 were held out for these accepted measurements. Retraining on these
sheets would change that boundary and needs a new report. Fresh runs took 49–73 seconds per sheet on the GPU.

Every generated design reopens with all recognized connections intact, but recognition is **not**
complete: review the drawing, the `corrections` list and the warnings before using a design. Pin
numbers on blurred or 200 dpi scans are the main remaining gap. Scan at 300 dpi or better when possible.

## Fine-tuned text reader

`training/schematic_ocr.py` is a compact CRNN for schematic tokens, trained on synthetic plotter-font
text plus confident real crops (`tools/harvest_crops.py`). It trains on a 4 GB GPU (peak ~560 MiB,
3,000 steps in ~2 min) and runs in the backend through onnxruntime from
`checkpoints/schematic-ocr/model.onnx` as a second reader for pin numbers and labels. Longer runs
can use `training/Train_Schematic_OCR_Colab.ipynb`.
