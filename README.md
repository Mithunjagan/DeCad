<div align="center">

<img src="docs/media/hero.svg" alt="DeCad: scanned schematic in, verified native OrCAD design out" width="100%"/>

<br/>

[![Stars](https://img.shields.io/github/stars/Mithunjagan/DeCad?style=for-the-badge&logo=github&labelColor=171819&color=e7b58b)](https://github.com/Mithunjagan/DeCad/stargazers)
[![Accuracy](https://img.shields.io/badge/exact%20pins-87%25-81b89b?style=for-the-badge&labelColor=171819)](#-measured-not-promised)
[![OrCAD](https://img.shields.io/badge/OrCAD%20X-native%20.DSN-e7b58b?style=for-the-badge&labelColor=171819)](#-how-it-works)
[![CUDA](https://img.shields.io/badge/OCR-CUDA-eac37c?style=for-the-badge&logo=nvidia&logoColor=eac37c&labelColor=171819)](#-gpu-accelerated-ocr)
[![Netlist](https://img.shields.io/badge/PCB%20netlist-0%20errors-81b89b?style=for-the-badge&labelColor=171819)](#-measured-not-promised)

![Windows](https://img.shields.io/badge/Windows%2010%2F11-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/Python%203.11%20%7C%203.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js%2016-000000?logo=nextdotjs&logoColor=white)
![KiCad](https://img.shields.io/badge/KiCad%2010-314CB0?logo=kicad&logoColor=white)
![ONNX](https://img.shields.io/badge/ONNX%20Runtime-005CED?logo=onnx&logoColor=white)

**[Quick start](#-quick-start)** · **[See it work](#-see-it-work)** · **[Product tour](#-product-tour)** · **[Accuracy](#-measured-not-promised)** · **[How it works](#-how-it-works)** · **[GPU OCR](#-gpu-accelerated-ocr)** · **[Roadmap](#-roadmap)**

</div>

---

## The problem

Decades of electronics live on paper: plotter printouts, scanned PDFs, photocopies of photocopies.
Bringing one sheet back into a CAD tool means **redrawing it by hand**: every part, every pin, every
net. That takes hours per sheet and invites mistakes.

**DeCad reads the drawing and writes the design for you.** It writes a **native OrCAD Capture `.DSN`**
through Capture's own database, then **reopens it and checks every pin** before giving it back.


## ✨ Why DeCad

<table>
<tr>
<td width="33%" valign="top">

### 🔁 Verified, not guessed
Each saved design is **reopened through Capture's database** and compared pin by pin with what was
read. Misreads it can prove wrong are removed and reported: a pin the part lacks, or a pin on two nets.

</td>
<td width="33%" valign="top">

### 📏 Measured, not promised
Accuracy is scored **from the saved `.DSN`** against **hand-transcribed ground truth**, with
**245 labelled pin checkpoints**. The scorer, the ground truth and the results are all in this repo.

</td>
<td width="33%" valign="top">

### 🧩 Native, not an export hack
Real Capture parts from **26k installed library packages**, generated symbols when no library part
matches, a **PCB footprint on every part**, and output that passes Capture's PCB netlister.

</td>
</tr>
<tr>
<td valign="top">

### 🌫️ Scan-aware
One **Automatic** mode for every input. It measures resolution, character height, stroke blur and
skew, then picks the enhancement itself. You never switch settings by hand.

</td>
<td valign="top">

### ⚡ GPU when you have one
OCR runs in a **CUDA worker**: about **2× faster** on a 4 GB laptop RTX 3050, with identical scores.
It works on CPU too, and strict CUDA mode never falls back to CPU silently.

</td>
<td valign="top">

### 📚 Your libraries, used
Bring your own **`.OLB` libraries, `.DSN` designs, footprints and part maps**. Every generated
design places parts from them first and ships the footprints it used.

</td>
</tr>
</table>

## 📸 Product tour

<sub>Real screenshots of the running app, in its default <b>Copper · Dark</b> theme. The project shown is a recognized scan of Sample 1.</sub>

<div align="center">
<img src="docs/screenshots/workspace.png" alt="DeCad workspace: projects, project files, KiCad schematic, BOM/Nets/Checks tabs, live system resources and the design assistant" width="100%"/>
<br/><sub><b>The workbench.</b> Projects and files on the left, the schematic with every design view in the middle, and live machine stats plus the design assistant on the right.</sub>
</div>

<br/>

<table>
<tr>
<td width="50%" align="center"><img src="docs/screenshots/welcome.png" alt="Welcome screen"/><br/><sub><b>Welcome.</b> Open a local workspace or continue with GitHub.</sub></td>
<td width="50%" align="center"><img src="docs/screenshots/blueprint-to-orcad.png" alt="Blueprint to OrCAD Capture drop zone"/><br/><sub><b>One drop.</b> Drop a scan or PDF on <i>Blueprint → OrCAD Capture</i>, or add your own libraries next to it.</sub></td>
</tr>
<tr>
<td align="center"><img src="docs/screenshots/review-components.png" alt="Review circuit: components"/><br/><sub><b>Review the read.</b> Every recognized part, value and symbol, editable before anything is written.</sub></td>
<td align="center"><img src="docs/screenshots/review-connections.png" alt="Review circuit: connections"/><br/><sub><b>Net-by-net editing.</b> Search 185 nets and fix any physical pin in place.</sub></td>
</tr>
<tr>
<td align="center"><img src="docs/screenshots/review-notes.png" alt="Review notes with input assessment"/><br/><sub><b>Honest notes.</b> The input assessment, removed misreads and every pin worth a second look.</sub></td>
<td align="center"><img src="docs/screenshots/orcad-verified.png" alt="OrCAD Capture design verified dialog"/><br/><sub><b>Verified in Capture.</b> 24 parts, 277 pins checked, 185 nets, 24/24 footprints, and the design rendered from the saved file.</sub></td>
</tr>
<tr>
<td align="center"><img src="docs/screenshots/orcad-netlist.png" alt="Physical netlist read back from the DSN"/><br/><sub><b>Physical netlist.</b> Read back from the <code>.DSN</code>. Filter by net or <code>part.pin</code>, and export to PCB Editor or CSV.</sub></td>
<td align="center"><img src="docs/screenshots/system-monitor.png" alt="Live system monitor showing the RTX 3050" width="70%"/><br/><sub><b>Live resources.</b> CPU, RAM and the actual GPU (VRAM, load, temperature) while recognition runs.</sub></td>
</tr>
<tr>
<td align="center"><img src="docs/screenshots/bom.png" alt="Bill of materials"/><br/><sub><b>BOM.</b> References, values, footprints and supplier lookups.</sub></td>
<td align="center"><img src="docs/screenshots/nets.png" alt="Electrical connections"/><br/><sub><b>Nets.</b> Real electrical connections from KiCad's netlist, searchable by net or pin.</sub></td>
</tr>
<tr>
<td align="center"><img src="docs/screenshots/component-database.png" alt="Unified KiCad and OrCAD component database"/><br/><sub><b>Unified component database.</b> Search KiCad and OrCAD sources, validate pin-to-pad mapping, and place the part.</sub></td>
<td align="center"><img src="docs/screenshots/command-palette.png" alt="Command palette"/><br/><sub><b>Command palette.</b> <kbd>Ctrl</kbd> + <kbd>K</kbd> for projects, imports, exports and every action.</sub></td>
</tr>
<tr>
<td align="center"><img src="docs/screenshots/applications.png" alt="Applications and models"/><br/><sub><b>Applications & models.</b> Bundles for KiCad, ngspice, LTspice and Qucs-S, plus local AI tasks.</sub></td>
<td align="center"><img src="docs/screenshots/history.png" alt="Git history"/><br/><sub><b>History.</b> Every change is a local Git commit, with optional GitHub push.</sub></td>
</tr>
<tr>
<td align="center"><img src="docs/screenshots/workspace-light.png" alt="Paper light theme"/><br/><sub><b>Paper · Light.</b> Follows your system theme automatically.</sub></td>
<td align="center"><img src="docs/screenshots/welcome-light.png" alt="Welcome screen in light theme"/><br/><sub><b>Designed both ways.</b> Every screen works in dark and light.</sub></td>
</tr>
</table>

## 📊 Measured, not promised

<div align="center">
<img src="docs/media/accuracy.svg" alt="Exact labelled pins: Sample 1 91%, Sample 3 86%, Sample 4 89%, Sample 5 81%, all clear sheets 87%" width="100%"/>
</div>

Fresh end-to-end run on the GPU, 2026-10-18 ([`tools/eval/results/claude-ocr3-gate`](tools/eval/results/claude-ocr3-gate)).
Every design was generated, saved, **reopened**, and scored from the reopened file.

| Input | Parts found | Precision | Values | Labelled pin → net exact | Time |
|---|---:|---:|---:|---:|---:|
| Sample 1 (clear) | 24/28 | 100% | 100% | **51/56 (91%)** | 53 s |
| Sample 3 (clear) | 30/34 | 97% | 93% | **59/69 (86%)** | 73 s |
| Sample 4 (clear) | 25/30 | 100% | 100% | **64/72 (89%)** | 49 s |
| Sample 5 (clear) | 22/25 | 100% | 95% | **39/48 (81%)** | 56 s |
| **All clear sheets** | | | | **213/245 (87%)** | |
| Sample 4, scanned PDF 300 dpi | 25/30 | 86% | 100% | 38/72 (53%) | 58 s |
| Sample 4, scanned PDF 200 dpi | 18/30 | 90% | 100% | 0/72 | 54 s |
| Sample 4, blurred PDF (σ = 2 px) | 12/30 | 80% | 100% | 0/72 | 55 s |

All 8 designs reopen cleanly, and all 8 pass Capture's PCB netlister (`pstswp`) with **0 errors**.

<details>
<summary><b>How to read these numbers</b></summary>

- *Labelled pin → net exact*: the pin exists in the saved design and sits on the hand-labelled net.
- Sample 2 (a 1600 px sheet with ~5 px text) has part-count ground truth only: TC514100 7/16,
  74F374 4/8, 74F244 2/4.
- Samples 1 and 3 contributed text crops to the fine-tuned reader. Samples 2, 4 and 5 are held out.
- Pin numbers on 200 dpi and blurred scans are the open problem (see the [roadmap](#-roadmap)).
  Those pages carry a "rescan at 300 dpi" review note.

</details>

## 🧠 How it works

<div align="center">
<img src="docs/media/pipeline.svg" alt="Pipeline: scan, assess and enhance, GPU OCR, pins and nets, library check, native verified DSN" width="100%"/>
</div>

```mermaid
flowchart LR
    A["Image / PDF"] --> B["Input assessment<br/>resolution · blur · skew"]
    B --> C["Enhancement<br/>deskew · super-sampling<br/>stroke-preserving binarization"]
    C --> D["GPU OCR worker<br/>RapidOCR + fine-tuned CRNN"]
    C --> E["Geometry<br/>wires · junctions · IC bodies"]
    D --> F["Pin strips<br/>pin number at the body edge<br/>net label along the wire"]
    E --> F
    F --> G["Sheet-evidence repair<br/>references · part numbers · signal families"]
    G --> H["Library check<br/>installed + workspace .OLB"]
    H --> I["Native writer<br/>Capture database via Tcl"]
    I --> J{"Reopen &<br/>verify every pin"}
    J -->|provable misread| I
    J -->|pass| K[".DSN · .OLB · .opj<br/>PCB netlist · preview"]
```

<details>
<summary><b>Where each stage lives</b></summary>

| Stage | Source |
|---|---|
| Input assessment, enhancement, OCR, bodies, pin strips, nets, repairs | `backend/app/digital_vision.py` |
| GPU worker dispatch and session verification | `backend/app/ocr_runtime.py`, `backend/app/ocr_worker.py` |
| Library matching with OCR-aware correction (`74F24U` → `74F240`) | `backend/app/orcad_capture.py`, `orcad_library.py` |
| Writing through Capture's database (`tclsh` + `orDb_Dll_Tcl64.dll`) | `backend/app/orcad_writer.tcl` |
| Reopen verification and physical netlist | `backend/app/orcad_dump.tcl`, `orcad_capture.py` |
| SVG preview of the saved design | `backend/app/orcad_render.tcl` |

In **Automatic** mode the logic-schematic recognizer runs first. If it finds no ICs and nets, the
simple discrete R/C/V recognizer (`circuit_vision.py`, Tesseract + OpenCV) takes over.

</details>

## 🚀 Quick start

> The OrCAD output needs **Windows** and a local **OrCAD X Capture** install. Without OrCAD, use the Docker setup (see *Docker* below).

| Requirement | Notes |
|---|---|
| Windows 10/11 | Tested on Windows 11 |
| [KiCad 10](https://www.kicad.org/download/windows/) | Default `D:\KICAD`, or set `S2SDN_KICAD_DIR`. Its Python 3.11 hosts the backend. |
| OrCAD X Capture 26.1 | Default `D:\tools`, or set `ORCAD_ROOT` |
| Node.js 20+ | Frontend (tested with Node 24) |
| *Optional:* NVIDIA GPU, CUDA 12 | For [GPU OCR](#-gpu-accelerated-ocr). 4 GB VRAM is enough. |

```powershell
git clone https://github.com/Mithunjagan/DeCad.git
cd DeCad
copy backend\.env.example backend\.env
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-native.ps1
```

Open **http://localhost:3100**. On first run, `start-native.ps1` builds `backend\.venv` from KiCad's
Python, installs the requirements, and starts the API on **:8100** and the workbench on **:3100**.

For a desktop icon that starts everything in its own window, run
`powershell.exe -ExecutionPolicy Bypass -File .\install-desktop-app.ps1` once. Stop everything with `stop.ps1`.

### Your first conversion

1. Create a project, then open **Libraries & footprints**.
2. Drop a drawing on **Blueprint → OrCAD Capture**. Try `samples/orcad/Sample 4.jpg.jpeg`.
3. The **OrCAD Capture design** dialog shows:
   - the verification badge, parts, pins and nets;
   - PCB footprint coverage;
   - the drawing rendered back from the saved file;
   - a searchable physical netlist, downloadable as `.net` or `.csv`.
4. Click **Open in OrCAD Capture**. In the tree, expand `<design>.dsn` → `SCHEMATIC1` and double-click `PAGE1`.

To review the read first, attach the file in the assistant and send `convert to OrCAD` instead. The
**Review circuit** dialog lets you:
- compare with the source;
- edit one net at a time;
- then **Generate verified OrCAD .DSN**.

## ⚡ GPU-accelerated OCR

Recognition runs in a separate **CUDA Python** (`S2SDN_OCR_PYTHON`), independent of KiCad's Python.
Each job runs as a hidden worker process. The worker checks which provider each ONNX session actually
uses before it reports `cuda`, and frees GPU memory when it exits.

```powershell
py -3.12 -m venv backend\.state\gpu-venv
$py = "backend\.state\gpu-venv\Scripts\python.exe"
& $py -m pip install -r backend\requirements.txt
& $py -m pip install --no-deps -r backend\requirements-ocr.txt
& $py -m pip uninstall -y onnxruntime
& $py -m pip install onnxruntime-gpu==1.22.0
& $py -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121   # CUDA 12 / cuDNN 9 DLLs
```

```ini
# backend/.env
S2SDN_OCR_PYTHON=D:/path/to/DeCad/backend/.state/gpu-venv/Scripts/python.exe
S2SDN_OCR_DEVICE=cuda      # strict: fail loudly instead of falling back to CPU
IMAGE_MODE=auto
```

| Sample 1, live app | Time | Exact pins |
|---|---:|---:|
| CPU | 98.8 s | 51/56 |
| **RTX 3050 Laptop (4 GB)** | **49.8 s** | **51/56** |

The status route `GET /api/vision/status` reports the verified device and each session's providers.
Sessions use a bounded memory arena with a heuristic convolution search, because RapidOCR's defaults
can exhaust a 4 GB card.

## 🧰 Everything else in the box

| | |
|---|---|
| 📚 **Libraries & footprints** | Drop `.OLB` libraries, existing `.DSN` designs (their parts are extracted), Allegro/KiCad footprints, or a part map like `74F174 → soic16`. |
| 🔎 **Find any component** | Unified KiCad + OrCAD search. It acquires permitted assets, validates pin-to-pad mapping, and saves the symbol and footprint into your project. |
| 🖥️ **Native KiCad, docked** | The real `eeschema` runs inside the DeCad window, next to the project list and assistant. |
| 💬 **Assistant** | `create a voltage divider` · `add U1 74xx:74LS244` · `connect R1 pin 2 to C1 pin 1` · `run ERC` · `undo` |
| 📈 **Simulation** | ngspice, or a built-in MNA transient solver, with an oscilloscope view |
| 📦 **Exports** | KiCad · OrCAD `.DSN` · Specctra DSN (Freerouting) · EDIF · SPICE · BOM · netlists · LTspice/Qucs-S bundles |
| 🕓 **History** | Local Git commits, plus optional GitHub push |

## 🔬 Reproducing the evaluation

```powershell
$py = "backend\.state\gpu-venv\Scripts\python.exe"   # or backend\.venv\Scripts\python.exe (CPU)

& $py tools\eval\run_eval.py 1 2 3 4 5 --out tools\eval\results\my-run          # clear samples
& $py tools\eval\make_degraded.py 4                                              # 300/200 dpi + blurred PDFs
& $py tools\eval\run_eval.py --images tools\eval\degraded --variant scan300 4 --out tools\eval\results\my-run
& $py tools\eval\codex_verify.py my-gate --baseline tools\eval\results\claude-ocr3-gate\report.json   # full gate
```

Each run writes `report.md` and `report.json`. For every input it also saves the design,
`recognized.json`, `ocr-tokens.json` and `pin-debug.json`. Run one evaluation at a time on 8 GB machines.

<details>
<summary><b>⚙️ Configuration reference</b></summary>

`backend/.env` (template: `backend/.env.example`). It is git-ignored; never commit it.

| Variable | Purpose |
|---|---|
| `IMAGE_MODE` | Default recognizer: `auto` (recommended), `digital`, `circuit`, `ocr`, `vision` |
| `S2SDN_OCR_PYTHON` / `S2SDN_OCR_DEVICE` | OCR worker Python, and `cuda` (strict), `cpu`, or unset for auto |
| `S2SDN_CUDA_DLLS` | Extra folder with CUDA 12 / cuDNN 9 DLLs |
| `S2SDN_TEXT_MODEL` | Override path of the fine-tuned reader |
| `ORCAD_ROOT` / `S2SDN_KICAD_DIR` | OrCAD and KiCad install roots |
| `TESSERACT_DIR` | Tesseract folder, if not in a default location |
| `ALLOW_LOCAL_LOGIN` | Local workspace without GitHub sign-in |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | Optional OAuth for pushing projects |
| `OLLAMA_URL`, `CHAT_MODEL` | Optional local language model for the assistant |
| `CHAT_API_URL`, `NVIDIA_API_KEY`, `CHAT_API_MODEL` | Optional cloud chat for explanations and planning only. Recognition always stays local. |

</details>

<details>
<summary><b>🔌 HTTP API</b></summary>

The frontend reaches the backend through a same-origin `/api` proxy.

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/projects/{pid}/orcad/auto` | Attachment → recognize → write → verify (`{"attachment": "references/x.jpg", "recognition_mode": "auto"}`) |
| `POST` | `/projects/{pid}/export/orcad-dsn` | Reviewed circuit JSON → verified `.DSN` zip |
| `GET` | `/projects/{pid}/orcad` | Last design status: `passed`, `checked_pins`, `corrections`, `footprints`, … |
| `GET` | `/projects/{pid}/orcad/preview.svg` · `/orcad/netlist` · `/orcad/download` | Preview, physical netlist, design zip |
| `POST` | `/projects/{pid}/orcad/open` | Open in the installed Capture |
| `GET` | `/vision/status` | Recognizer mode and verified OCR runtime |
| `POST` | `/ai/chat` | Assistant with attachments and `recognition_mode` |
| `POST` | `/library/upload` | Add `.OLB` / `.DSN` / footprints / part map / zip |
| `GET` | `/components/search` | Unified component search |

Full list: `backend/app/main.py`.

</details>

<details>
<summary><b>🗂️ Repository layout</b></summary>

```text
backend/app/      FastAPI app, recognizers, GPU worker, OrCAD Tcl scripts, libraries
backend/tests/    pytest suite
frontend/app/     Next.js 16 / React 19 workbench
desktop/ bridge/  native Windows host (docked KiCad, WebView2) and desktop bridge
checkpoints/      schematic-ocr (CRNN, ONNX + PyTorch) · circuit-lora (experimental VLM adapter)
samples/orcad/    the five evaluation schematics
tools/eval/       ground truth, scorer, degraded-scan generator, gates, results
training/         CRNN and LoRA training (local GPU + Colab notebooks)
docs/media/       README graphics
```

</details>

<details>
<summary><b>🐳 Docker (without OrCAD)</b></summary>

On macOS, Linux or Windows, the containers provide KiCad editing, simulation, exports and the CPU
recognizers. They do not write OrCAD designs.

```sh
./start.command                                         # macOS / Linux
powershell -ExecutionPolicy Bypass -File .\start.ps1    # Windows
```

Ports: 3100 (workbench), 8100 (API), 6180 (embedded KiCad), and optionally 11434 (Ollama).

</details>

<details>
<summary><b>🧪 Development and tests</b></summary>

```powershell
cd backend;  .venv\Scripts\python.exe -m pytest tests -q
cd frontend; npm ci; npm test; npm run dev
```

Measure every recognition change end-to-end with `tools/eval/codex_verify.py`. Gains on single text
crops have lowered end-to-end wiring scores before.

</details>

## 🤖 Models

| Model | Role |
|---|---|
| **RapidOCR** (PaddleOCR det/cls/rec on ONNX Runtime) | Primary text detection and reading, on CUDA or CPU |
| **Schematic CRNN** (`checkpoints/schematic-ocr`) | Second reader for pin numbers, references and labels. Trained with `training/schematic_ocr.py` on synthetic plotter-font text plus confident real crops: about 2 min on a 4 GB GPU. |
| **Qwen2.5-VL LoRA** (`checkpoints/circuit-lora`) | Experimental whole-image extraction. Not used for OrCAD output: it failed the reference wiring check ([details](WINDOWS_VISION.md)). |

For longer runs, use the Colab notebooks in `training/`. Build their upload bundle with `python tools/build_colab_bundle.py`.

## 🧭 Roadmap

- [x] Native OrCAD Capture `.DSN` with reopen-and-verify
- [x] PCB footprint on every part; PCB netlister passes with 0 errors
- [x] Automatic handling of low-resolution and blurred scans
- [x] CUDA OCR worker with verified sessions
- [x] 87% exact labelled pins on clear sheets
- [ ] **Pin numbers on blurred / 200 dpi scans**: infer them from the library pinout when digits are unreadable
- [ ] Recover ICs dropped on blurry pages
- [ ] Multi-sheet designs with hierarchical ports
- [ ] Broader ground truth beyond the five evaluation sheets

## ⚠️ Limitations

- **Always review before use.** 87% of labelled pins are exact on clear sheets, and far fewer on
  degraded scans. The review dialog and the `corrections` list show what is uncertain.
- OrCAD output needs Windows, a local OrCAD X Capture installation, and the native backend.
- The discrete R/C/V recognizer covers clean resistor, capacitor and source drawings only.
- Allegro geometry (`.dra`, `.psm`, `.brd`) is cataloged but not converted.
- The desktop services are for one local user. Do not expose ports 3100/8100 publicly.

## 📖 Documentation

[DEMO.md](DEMO.md) (demo runbook) · [ORCAD_STATUS.md](ORCAD_STATUS.md) (pipeline internals) ·
[COMPONENT_LIBRARIES.md](COMPONENT_LIBRARIES.md) · [WINDOWS_VISION.md](WINDOWS_VISION.md) ·
[SPECCTRA.md](SPECCTRA.md) · [RELEASE_GATES.md](RELEASE_GATES.md) · [STATUS.md](STATUS.md) (dated log) ·
[THIRD_PARTY.md](THIRD_PARTY.md)

## 🤝 Contributing

Issues and pull requests are welcome, especially:
- new hand-transcribed ground truth sheets;
- blurred-scan pin recovery;
- support for more EDA formats.

Please measure recognition changes end-to-end with the gate before opening a PR.

<div align="center">

### ⭐ If DeCad saves you from redrawing a schematic, star the repo. It helps others find it.

<br/>

<sub>OrCAD, Capture and Allegro are trademarks of Cadence Design Systems. OrCAD itself is not distributed.
KiCad, ngspice, RapidOCR and the other components are used under their own licenses (see <a href="THIRD_PARTY.md">THIRD_PARTY.md</a>).
<b>License:</b> proprietary, all rights reserved by the authors, until an open-source license is designated.</sub>

</div>
