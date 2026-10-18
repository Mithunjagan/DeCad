# Implementation status log

> Detailed, dated implementation and verification notes (formerly the README). For an overview, setup and measured results see [README.md](README.md).

A local circuit workbench with native KiCad editing, real electrical connectivity, post-edit ERC, Git history, connectivity-preserving EDIF/XML export, and circuit simulation. The small local model runs through Ollama; an optional circuit vision adapter can run on a separate GPU server. No paid API key is required.

## Current implementation and measured status

Claude Code and Codex coordinate through [Codex's active handoff](COORDINATION_CODEX.md)
and `COORDINATION_CLAUDE.md`. Check claimed files and the recognition queue before
editing or starting evaluations; this laptop runs one recognition job at a time.

Updated 2026-10-18. On the configured Windows laptop, start the existing native
installation with `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-native.ps1`
and open **http://localhost:3100**. This uses installed KiCad and OrCAD; Docker is
not required for this native path. The container setup below is an alternative.

For everyday launch, double-click **DeCad** on your desktop. The existing launcher
`DeCad.vbs` starts the services and opens the workbench. Choose your project and
**Edit in KiCad** for the native desktop editor. If typing the launch command,
include **`.exe`** in `powershell.exe` so a file named `powershell` cannot shadow
the executable. Close any Windows “Select an app to open powershell” dialog and
run the command again with the extension; no file association change is needed.

**GPU recognition:** the native backend can dispatch automatic/digital image
recognition to an existing CUDA Python via `S2SDN_OCR_PYTHON`, independently of
KiCad's Python. On this laptop it uses the existing
`backend/.state/claude-20261018/gpu-venv/Scripts/python.exe`; no packages were
installed or changed. `backend/.env` selects `S2SDN_OCR_DEVICE=cuda`. Explicit
CUDA mode rejects a failed GPU initialization instead of silently falling back
to CPU. `S2SDN_OCR_DEVICE=cpu` remains available. The default without a separate
runtime continues to use the backend's installed OCR dependencies.

The assistant now reports verified CUDA sessions and actual preparation/text/
connection stages, also available at `/api/vision/status`. Configuration alone
is labelled unverified. GPU memory is released after each request. Text detection,
classification and reading can use CUDA; image preparation, geometric wiring
and library checks also use the CPU, so GPU utilization varies during a request.
The existing recognition code, models and review gates are preserved. The runtime
probe recorded **851 CUDA kernel events**, and CPU/GPU text matched on its crop;
this establishes acceleration, not improved schematic accuracy. Evidence and
the real application sheet check are under
`backend/.state/codex-20261018/gpu-runtime/`.

On Sample 1, the actual upload/assistant/review/native-DSN flow used the RTX 3050,
reached **52% sampled GPU utilization**, and recognized the page in **49.8 s**.
A fresh CPU reference took **98.8 s**. Both saved designs scored **24/28 parts,
24 correct values, zero spurious parts, and 51/56 exact labelled pins**. This is
a Sample 1 runtime/nonregression check, not a new eight-input accuracy gate.
The app's CUDA worker also preserves the source user's uploaded library mappings.
Claude's digital recognizer, OrCAD exporter and schematic OCR checkpoint were
left unchanged. Separately, the old text-only OCR path no longer invents
`10k`, `100nF` or `IC` when a value is missing; it requires readable pairs.
Final live repeat took **51.8 s**, retained the same scores, and verified uploaded
library context and visible runtime status. **20 focused backend tests and 10
frontend tests passed**. Test projects were removed; the user's `new` project was
left untouched. `gpu-runtime/final-check.json` records the final source hashes,
scores and live configuration. This does not replace Claude's full accuracy gate.

Project management: every sidebar project has a visible **trash button**. Confirm
**Move to trash**, then use **Undo** to restore its files and local Git history.
Deletion saves and closes the matching DeCad-owned KiCad editor first, including
when requested from another browser window. If a stale local lock remains, the error dialog offers
**Force move to trash**. It checks running KiCad processes and local lock ownership;
unknown external editors and locks from other computers remain protected. Verified
owned editors displaying another project can keep running. All files, including
the stale lock, stay in recoverable trash. No editor is force-terminated. Recovery never
overwrites another project with the same name. This is recoverable local storage,
not permanent deletion.

Windows can also hold an OrCAD subfolder open after its editor closes. For that
case, **Force move to trash** creates and verifies a complete recovery copy before
removing the project from DeCad's list. The locked original stays on disk with a
private trash marker; DeCad blocks further access to that removed project. **Undo**
restores the retained original, preserving any later writes by the external app.
Nothing is force-terminated, and a failed or changing copy leaves the project
visible. This fallback does not free the original folder's disk space or clean it
up automatically. To reuse its name, restore it, close the application holding the
folder, then delete normally; a different project name also works.

Deletion verification: **14 recovery tests and 8 frontend tests passed**. A real
Windows directory handle plus an off-screen native KiCad editor and separate
browser verified Save/close, force removal, cross-window updates, Undo with
unchanged schematic bytes, and repeated deletion. The user's blocked `sample`
project was removed with all **72 asset entries** matching its recovery copy.
Evidence: `backend/.state/codex-20261018/folder-trash/` and
`backend/.state/codex-20261018/sample-force-result.json`. No OCR/model job ran.
The browser schematic uses a compact pan/zoom view without the redundant vertical
KiCanvas toolbar; DeCad's project and library controls remain in the workbench.

**Circuit review:** recognition opens a bounded review workspace with a fixed
header and footer. Search component references/values, use **Connections** to find
a net or physical pin and edit one net at a time, or open **Compare source** for
image/PDF comparison and image zoom. **Undo edit** restores the last draft change;
**Review notes** separates structural errors from recognition warnings. Renaming
a component updates its net endpoints. The JSON editor preserves source positions
and other circuit metadata, and unapplied JSON changes block import. Confirm the
review, then select **KiCad project** or **OrCAD Capture** and apply. Structural
checks do not establish recognition accuracy; source comparison remains necessary.

The netlist has its own fixed table header, net/pin search and explicit all /
multiple-pin / single-pin filters. Schematic controls appear only on the schematic
tab; ERC findings remain visible instead of being summarized as a clean check.
Assistant failures show a concise message, expandable details and **Retry request**.
Retries retain actual attachment metadata. Copied `[Attached: filename]` labels
are resolved only when the exact file exists in the current project (including
Windows paths); otherwise the app asks you to attach the source again.

Review verification: **8 frontend tests passed**, plus browser interaction with
a **24-component / 235-net fixture** at 125% scale and widths 320–1920px. Checked
reference/pin preservation, duplicate-pin rejection, JSON guards, source zoom,
readable confirmation/footer/target controls, import payloads, attachment retries,
net filters, and table-header scrolling. This UI check runs no OCR or model, writes
no imported design, and makes no new recognition or EDA export accuracy claim.

**Native editor in the center (Windows):** click **Edit in KiCad** to open the
DeCad desktop window. It docks the installed `eeschema.exe` alongside the project
list and assistant using KiCad's bundled wxPython and WebView2. No additional
runtime install is needed on this configured laptop. **KiCad editor** is editable;
**KiCad view** and **Preview** are browser previews. Native menus/toolbars execute
KiCad's own commands. The editor initially zooms to the actual components.

**Appearance:** **System · Auto** follows Windows app light/dark mode in the
desktop shell and your browser's system preference on the web. The appearance
selector also retains explicit theme choices. The desktop title bar, native menus
and taskbar now use DeCad's icon and Windows appearance; schematic paper/colors
remain controlled by KiCad. Native system appearance uses wxWidgets'
[system appearance API](https://wxpython.org/Phoenix/docs/html/wx.PyApp.html).
Text uses local Segoe UI at readable sizes, with per-monitor DPI awareness and no
scaled text effects. The assistant shows an animated circuit, the current operation
and elapsed time while a request runs. It stops on completion or error and respects
reduced-motion preferences; it does not display invented progress percentages.
Browser light/dark, manual theme persistence, pending/error states, 125% rendering,
and responsive widths 360–1920px passed focused checks. Native Windows theme,
appearance notifications, icon handles and 125% WebView rendering were checked too.

**Older schematic warning:** use native **File → Save** to let the installed KiCad
perform a real format conversion. The open `Circuit-4beec24e` schematic was saved
through KiCad 10.0.6 as format `20260306`, with its three components/values and all
net endpoints verified unchanged. Original files and the comparison are preserved
under `backend/.state/codex-20261018/format-upgrades/`. Other older schematics may
show the same message until their first native save.

Switching projects saves and gracefully closes this desktop's editor first.
App-generated changes suspend it before writing, then reopen the updated file.
KiCad dialogs must be completed or cancelled before these operations proceed;
timeouts leave the schematic unchanged. Separately opened KiCad windows are never
terminated, and their lock files block conflicting DeCad writes. Verified desktop
checks include a real mouse/keyboard component move with saved coordinate readback,
native Save, zoom, component acquisition with editor close/reopen, and HTML dialogs
appearing above the editor. Imported IC reference/value fields retain their library
positions. Desktop docking is verified with Windows and KiCad **10.0.6**;
browser previews continue to work independently.

Component assembly uses automatic positions on the KiCad grid with spacing around
existing symbols, wires and connection markers; the reference advances after each
successful addition. Refine placement and wiring in the native editor. BOMs show
only assigned footprints: a guessed package is never presented as a verified asset.

Image-to-OrCAD placement now preserves recognized component positions and source
sheet orientation, moves overlapping symbols to nearby free space, and puts
components without coordinates below the main drawing. All five supplied images
and three degraded PDFs reopen successfully in Capture and pass its PCB netlister
with zero error entries. These checks do **not** establish complete recognition:

| Input | Recognized parts / annotated parts | Exact labelled pin-to-net assignments |
|---|---:|---:|
| Sample 1 | 23/28 | 34/56 |
| Sample 2 | 21; no complete reference annotation | not measured |
| Sample 3 | 27/34 | 40/69 |
| Sample 4 | 24/30 | 60/72 |
| Sample 5 | 19/25 | 24/48 |
| Sample 4, 300 dpi scan | 24/30 | 37/72 |
| Sample 4, 200 dpi scan | 18/30 | 0/72 |
| Sample 4, blurred 300 dpi | 12/30 | 0/72 |

Recognition evidence: `tools/eval/results/codex-snapping/report.json` and `gate.json`.
Layout evidence: `tools/eval/results/codex-layout-stable/layout-metrics.json`.
Sample 1's layout RMS error relative to recognized centres
fell from 17.27% to 1.49% of sheet width; recognition accuracy is reported separately
above. Sheet-supported signal-name correction passed the fresh eight-input gate:
parts and values did not regress, and every native PCB netlist has zero error
entries. Exact labelled assignments improved from 29/38/38/21 to 34/40/60/24 on
Samples 1/3/4/5. That recognition checkpoint reproduced four known backend
failures; the BOM footprint failure has since been fixed and its focused test
passes. All five frontend tests pass. Claude's staged body/reference fixes completed
S1–S5 diagnostic replays without regressions, recovering U43 on S1 (24/28 parts).
Those candidate results still need a separate fresh acceptance gate. Further OCR
and training changes belong to Claude's current work.

### Unified KiCad and OrCAD libraries: implementation in progress

The required architecture includes a common component record, shared local
search, manual and automatic library discovery, source/license provenance,
pin-to-pad validation, caching, and explicit export capabilities. Current native
Capture workflows already use installed/uploaded `.olb` libraries and extract
symbols from `.dsn` designs. The existing library panel catalogs Allegro package
symbols/padstacks and uploaded KiCad footprints; cataloging a binary asset does
not establish that its geometry was extracted or converted.

The unified database now has KiCad symbol/footprint adapters, native Capture OLB
package indexing and on-demand symbol extraction, source/license records, a
pin/pad validation cache, and explicit target-export errors. An original CC0
two-pin fixture from each ecosystem passed shared search, symbol extraction,
schematic placement, and KiCad library export through the installed CLI. Source
files were unchanged. Evidence:
`backend/.state/codex-20261018/component-acceptance/report.json`.

The running API has also passed discovery/indexing, shared search, validation,
placement and preview, Internal/KiCad downloads, and explicit unsupported Allegro
export rejection. Native package-only OLB export passes independent readback on
the original fixture. See [library usage, support matrix and limitations](COMPONENT_LIBRARIES.md).

This is a bounded acceptance check, not comprehensive format coverage. Capture
line/box graphics are converted; unsupported vector types are flagged. Allegro
`.dra`, `.psm`, `.pad`, `.brd` and independent `.step`, `.stp`, `.wrl` assets are
currently cataloged as references; their geometry conversion is not verified.
The browser's **Find component and add to project** flow passed a real UI check.
Local `Timer:NE555P` acquisition and an independent run with local lookup disabled
both produced an 8-pin/8-pad match and a real KiCad schematic. The latter downloaded
the symbol, inherited parent, footprint and license from the official KiCad 10.0.5
repository; native KiCad also reopened the footprint successfully. The project
contains its own footprint library, provenance and license records.
Cadence binary files require supported native tools or a verified parser;
renaming another format never counts as conversion. Assets need suitable license
permissions before copying or redistribution. This section and
[the change log](tools/eval/results/CODEX_LOG.md) track implementation and checks.

### Find a component and add it

Open a project → **Libraries & footprints** → enter a part number or exact symbol
such as **Timer:NE555P** → set a free reference such as **U1** → **Find component and
add to project**. The app checks local records and KiCad/OrCAD sources, then permitted
external assets if enabled, validates pin/pad mapping, caches the result, and saves
the symbol and footprint into your project. Unresolved parts leave it unchanged.

The built-in public fallback uses official KiCad libraries. Additional commercial
providers require authorization/configuration; a missing provider or unsupported
asset is reported. Arbitrary unknown parts and package substitutions are not
invented. See [the library guide](COMPONENT_LIBRARIES.md) for permissions and limits.

## Start

1. Install/start Docker Desktop with Docker Compose v2.24 or newer.
2. Double-click **start.command** on macOS, or run `./start.command` in a terminal. On Linux, run the same shell script.
3. On Windows, run `powershell -ExecutionPolicy Bypass -File .\start.ps1` from the extracted folder.
4. Open **http://localhost:3100** and choose **Open Local Workspace**.

The launcher builds the services. Local model downloads and loading are disabled by default. Core editing, simulation, exports and OCR work without a local language or vision model. Keep the terminal open until setup finishes.

For an optional small local language model (requires sufficient Docker memory):

```sh
ENABLE_AI=true ./start.command
```

Stop the services with `./stop.command`. Project data is stored in `backend/workspaces`; stopping/rebuilding containers does not remove it. Server-side sessions live in `backend/.state` and synthetic samples in `backend/datasets`.

Ports are 3100 (workbench), 8100 (API), 6180 (embedded KiCad), and optionally 11434 (Ollama). They bind only to this computer. These differ from the original application's ports so both versions can coexist.

The initial container/model downloads require several GB of disk space. Allow at least 12 GB of free storage. Core services are capped at 1 GiB and 512 MiB. With approximately 4 GiB allocated to Docker, an explicit ENABLE_AI=true can enable the small pretrained qwen3:0.6b model under a 2 GiB cap. Requests run sequentially with 2048 context tokens and two threads, and unload model weights afterward. It does not change Docker Desktop settings.

For the supplied Qwen2.5-VL adapter on Windows, use [the Windows vision setup](WINDOWS_VISION.md). Native inference has been exercised on this laptop, but the supplied adapter failed the reference circuit's wiring check. Exact image-to-circuit conversion is not verified.

Image imports default to CPU circuit recognition: Tesseract reads references/values and OpenCV detects clean resistor, capacitor and voltage-source symbols and traces their wire-connected pins. The attachment selector also offers labels-only OCR or a configured vision server. Every recognized graph requires review; unsupported symbols, ambiguous crossings and unmatched closed symbols are rejected. This bounded R/C/V recognizer is not general schematic recognition. Full vision is opt-in: `ENABLE_VISION=true ./start.command` on a Docker allocation of at least 7.5 GB selects vision mode and a configurable 4 GiB model cap. This general vision path has not passed a circuit-accuracy benchmark; see [release gates](RELEASE_GATES.md). `ENABLE_AI=false ./start.command` starts only the core. For a separate Ollama server, set OLLAMA_URL in a root .env file (or export it before running the launcher).

## Four application adapters

Open **Applications & models** in the workbench. KiCad, ngspice, LTspice and Qucs-S each have a portable bundle generated from the circuit's actual pin graph. KiCad uses native schematic/project files. LTspice and ngspice use SPICE; Qucs-S uses a native schematic with a SPICE subcircuit wrapper. ngspice and Qucs-S run inside the workbench. The scope can import uncompressed real transient RAW or CSV results from external simulators (time in seconds; maximum 20,000 samples).

The launcher starts a Python desktop bridge if Python 3 is installed. It has no network listener and opens only registered application artifacts. Install LTspice separately from its vendor; its binary is not redistributed. Set S2SDN_KICAD_PATH, S2SDN_LTSPICE_PATH, S2SDN_QUCS_S_PATH or S2SDN_NGSPICE_PATH for nonstandard installations. Downloaded bundles remain available without the bridge.

## Models and training

**Plan with model** selects between divider and RC templates using the local pretrained language model. Native code parses specified values and constructs connectivity; review the proposal before applying. Three controlled end-to-end planning cases passed; this is not a general design benchmark.

The archive supplied four synthetic pairs across two topology families. Audited records and group-disjoint manifests are in backend/datasets/provided. Supplied Qwen2.5-VL LoRA weights are present in this checkout; their tested pin-connection accuracy did not pass the known reference circuit. See [Windows vision verification](WINDOWS_VISION.md). `training/dataset_tools.py` prepares verified paired data; `training/finetune.py` is a separate CUDA LoRA pipeline with preflight gates. It deliberately refuses the included insufficient dataset. See [the training guide](training/README.md) for exact data, GPU training, evaluation and adapter-serving commands. See RELEASE_GATES.md before shipping broader model claims.

## First circuit

Create or select a project, choose **Output software** beside the assistant, then enter:

```text
create a voltage divider
```

This creates V1=5 V, R1=10k and R2=10k with VIN/VOUT/GND pin connections. The saved native schematic appears in **Preview**, and a verified bundle downloads for the selected software. A Download design button remains in the assistant reply. If references conflict with an existing design, a separate project preserves that design. Use **Edit in KiCad** for interactive editing and **Preview** to return. The Nets tab shows actual KiCad netlist nodes. ERC runs after the edit. Waveform Scope runs the circuit and shows VOUT=2.5 V.

Useful commands:

```text
add R3 4.7k
add C1 100nF
add U1 74xx:74LS244
change R3 to 22k
R3 = 10k
remove R3
connect net GND to C1 pin 2
connect R1 pin 2 to C1 pin 1
run ERC
undo
redo
```

Use a new project for `create RC lowpass` or to import files whose references already exist. Duplicate references and unknown device pinouts are rejected rather than silently substituted. Exact symbols use `Library:Symbol`; footprints can be supplied in circuit JSON. Native KiCad remains available for the full graphical editing workflow.

Edits are transactional. Invalid syntax, unknown symbols, bad pin mappings, and conflicting imports leave the previous schematic intact. Undo/redo restores schematic snapshots; the Commit button records the current files in local Git. These operations do not require a GitHub account.

## Import

The Import/Attach buttons accept SPICE `.cir`, `.spice`, `.net`, typed circuit `.json`, component text, PDF/DOCX text, and images. `examples/` contains powered divider, RC step, diode-model, and JSON examples.

Circuit JSON uses:

```json
{
  "components": [{"ref":"R1","value":"10k","library":"Device:R","footprint":"Resistor_SMD:R_0805_2012Metric"}],
  "nets": [{"name":"GND","nodes":[{"ref":"R1","pin":"2"}]}]
}
```

Text/component-list documents supply component values; their pin connections must be specified explicitly. Image/single-page scanned-PDF imports use CPU R/C/V symbol and wire recognition by default, producing component and pin/net proposals for review. Labels-only OCR remains available as an explicit option. Opt-in vision extraction also produces JSON for review. Inspect values, exact library symbols, and pin-to-net assignments against the source before selecting **Apply reviewed circuit**. ERC checks electrical rules; it cannot prove that a recognized diagram matches its source. Unreadable/unsupported inputs produce a visible error, never a fake successful conversion.

Legacy `.doc` files should be saved as `.docx`. SPICE imports support R/C/L/V/I/D/Q devices, values, node names, and `.model` declarations. Arbitrary SPICE scripts, `.include` files, and ambiguous subcircuit-to-symbol mappings are rejected. Supply complex device models and pinouts in native KiCad for workflows beyond these imported device types.

## Editing and exports

- **Schematic:** embedded native KiCad with zoom, grid, save, and fit controls.
- **Source:** read/edit exact `.kicad_sch`; Save Source first asks native KiCad to save its active document, then verifies the new file with KiCad. A failed parse rolls back.
- **BOM:** actual references, values, footprints and specified LCSC fields. Supplier links open searches. Prices/stock are not claimed unless queried from a supplier.
- **Nets:** actual component-pin connections from the native XML netlist.
- **Checks:** actual ERC errors/warnings and explicit unavailable states.
- **History:** actual Git commits. Commit is local; Git Push requires optional OAuth configuration.
- **Scope:** transient simulation using ngspice in Docker. Native installations without ngspice can use the verified linear R/C/L/V/I modified-nodal-analysis solver. Floating/unpowered/unsupported-model circuits fail visibly. Set step/stop with SPICE units, such as `1u` and `5m`. The API limits runs to 20,000 time steps.
- **Downloads:** KiCad source, SVG, XML netlist, EDIF, SPICE, BOM CSV/JSON, nets JSON, ERC JSON, and Git history JSON. The circuit.json sidebar row downloads the full typed graph.

EDIF exports preserve real port-to-instance connectivity. With OrCAD Capture installed on the same Windows computer (native backend), DeCad also writes **native OrCAD Capture `.DSN` designs**, verified by reopening them pin by pin, with an in-app preview and one-click image → DSN. See [ORCAD_STATUS.md](ORCAD_STATUS.md).

The shared embedded desktop is designed for one local user at a time. Close KiCad modal dialogs before changing projects or running automated edits. Automated edits save the active editor first and reopen the schematic gracefully; an unsaved dialog is never force-killed.

## Optional GitHub

Copy `backend/.env.example` to `backend/.env`. Create a GitHub OAuth app with callback `http://localhost:8100/auth/callback`, and set GITHUB_CLIENT_ID/GITHUB_CLIENT_SECRET. Restart the backend. Sign in with GitHub, then push a project; a private `s2sdn-<project>` repository is created if needed.

OAuth state is verified. The browser cookie contains only a random session ID. GitHub tokens remain in the local server session database and are supplied to Git through a temporary askpass helper, not saved in repository URLs. The original ZIP's embedded credentials are not bundled in this package.

Live GitHub authorization/push requires your account and is not part of automated testing. Never expose these local desktop services publicly without adding a proper deployment/authentication layer.

## Verification and development

Backend checks use Python 3.12+ and KiCad CLI 9+ with its symbol libraries installed:

```sh
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q
```

On macOS the installed KiCad path is detected automatically. Elsewhere set KICAD_CLI/KICAD_SYMBOL_DIR as needed. For a native development server, set OLLAMA_URL=http://localhost:11434, run the backend on port 8100, and run the frontend on port 3100:

```sh
cd backend
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8100
# In another terminal:
cd frontend
npm ci
npm run dev
```

The frontend uses a same-origin /api proxy. Docker builds route it to the internal kicad service; native development routes it to localhost:8100.

Synthetic generation is authenticated at `POST /datasets/synthetic/generate?count=4`. It generates actual KiCad schematics, native SVG previews, full connectivity JSON, EDIF, and SPICE. Dataset summary reports only generated samples; this package does not claim a fine-tuned model or downloaded research corpus.

Production completion steps: [PRODUCTION_PLAN.md](PRODUCTION_PLAN.md). Run `python tools/check_release.py --output release-status.json` to inspect recorded blockers. Additional AMS-Net data is distributed separately for development and requires annotation/pin-mapping review; it is never loaded on end-user startup. See [training hardware notes](training/HARDWARE.md) for the RTX 3050 assessment.

Two DSN formats are supported: Specctra PCB autorouter DSN (see [SPECCTRA.md](SPECCTRA.md)) and native OrCAD Capture schematic DSN (see [ORCAD_STATUS.md](ORCAD_STATUS.md)).

## Guided review and PCB export

Image proposals open a component/net editor with a source preview. Edit references, values, exact symbols, net names and physical pin assignments without writing JSON. Renaming a component updates its pin references; duplicate pin assignments block apply. Advanced JSON remains available. Failed requests preserve attachments and text for retry.

Choose Download → Specctra to open the PCB form. Search installed footprints, check physical pad numbers, enter board/routing dimensions and positions, then download the editable PCB and DSN. The placement preview shows origins, not package outlines; inspect the PCB before routing.

The experimental 3B training profile includes a required measured smoke step for 8 GB GPUs. See [hardware setup](training/HARDWARE.md). Training is separate from the normal desktop install and has not been executed on a CUDA machine here.
