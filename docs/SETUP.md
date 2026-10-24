# Set up DeCad on Windows

[← Project overview](../README.md) · [Measured results](RESULTS.md) · [Screenshot tour](SCREENSHOTS.md)

This guide follows the current `start-native.ps1` launcher and the checked-in
`hybrid_max_accuracy` profile. The full native workflow uses Windows, KiCad, a
separate CUDA OCR environment, and your own licensed OrCAD installation for `.DSN`
generation. The OCR checkpoint is a separate required asset: cloning the code does
not download it. The profile rejects a missing or different checkpoint.

## 1. Prepare the prerequisites

| Item | Purpose and location |
|---|---|
| Git | Clone the project and store local design history. |
| Node.js 20.9+ and npm | Build/run the frontend. The pinned Next.js package requires at least 20.9; the Docker frontend uses Node 22. |
| KiCad 10 for Windows | Native schematic CLI, symbols, footprints, Python, and the desktop editor. Set `S2SDN_KICAD_DIR` to its installation root. |
| Python 3.12 | The separate CUDA OCR environment. The backend uses KiCad's bundled Python; the recorded local backend is Python 3.11.5. |
| NVIDIA GPU and driver | Required by the pinned production CUDA profile. The recorded GPU environment uses a 4 GB RTX 3050 Laptop GPU. |
| Production OCR checkpoint | Obtain the accepted model asset separately from the project maintainers and place it as described below. |
| OrCAD X Capture | Optional for KiCad-only work, required for native Capture exports. Set `ORCAD_ROOT` to the **directory containing `tools/`**. A valid local license is required. |

Install these applications from their vendors. KiCad, OrCAD, CUDA runtimes, model
weights, installed libraries, and license files are not supplied by this repository.
Memory needs depend on the input and model configuration; run one OCR job at a time
on small-memory machines.

## 2. Clone the code

```powershell
git clone https://github.com/Mithunjagan/DeCad.git
cd DeCad
```

Run the remaining commands from this directory. GitHub sign-in is optional for a
local workspace. The application can link an account later when you want to push
design projects.

## 3. Place and verify the OCR model

Copy the supplied accepted checkpoint into:

```text
checkpoints/schematic-ocr/model.onnx
```

Verify it before starting the production profile:

```powershell
Get-FileHash .\checkpoints\schematic-ocr\model.onnx -Algorithm SHA256
```

Expected SHA-256:

```text
c5ad0e9ebe43373f1986ed5d6c39be0b73a29cb4dcb257e45ca7f91f41ce07cf
```

This value comes from [`backend/pipeline_profiles.json`](../backend/pipeline_profiles.json).
Do not rename a different model to satisfy the filename. `checkpoints/` is ignored
by Git, and no public download URL for this accepted artifact is configured in the repo.

## 4. Create the native backend environment

Set your KiCad root first. The examples use `D:\KICAD`; replace that path if needed.

```powershell
$env:S2SDN_KICAD_DIR = 'D:\KICAD'
$kicadPython = Join-Path $env:S2SDN_KICAD_DIR 'bin\python.exe'
& $kicadPython -m venv --system-site-packages backend\.venv

# Match start-native.ps1's Python 3.11 compatibility bounds.
(Get-Content backend\requirements.txt) `
  -replace '^numpy==.*','numpy>=2.2,<2.5' `
  -replace '^scipy==.*','scipy>=1.14' |
  Set-Content -Encoding utf8 backend\.venv\req-native.txt

& backend\.venv\Scripts\python.exe -m pip install -r backend\.venv\req-native.txt
& backend\.venv\Scripts\python.exe -m pip install --no-deps -r backend\requirements-ocr.txt
```

Keep `--no-deps` on the OCR requirements command. The project uses
`opencv-python-headless`; installing a second OpenCV distribution can shadow its
`cv2` module. The requirements comment explains this boundary.

## 5. Create the separate CUDA OCR environment

These versions match the installed OCR environment used for the recorded run.
Creating the environment can require substantial downloads.

```powershell
py -3.12 -m venv backend\.state\gpu-venv
$ocrPython = (Resolve-Path backend\.state\gpu-venv\Scripts\python.exe).Path
& $ocrPython -m pip install -r backend\requirements.txt
& $ocrPython -m pip install --no-deps -r backend\requirements-ocr.txt
& $ocrPython -m pip uninstall -y onnxruntime
& $ocrPython -m pip install onnxruntime-gpu==1.22.0
& $ocrPython -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121
```

The backend and OCR environments have different roles. Do not install GPU packages
into KiCad's bundled Python. CUDA availability alone does not prove inference ran
on the GPU; each OCR job records the providers its sessions actually used.

## 6. Configure local paths and install the frontend

On a **new checkout**, copy the example and edit it:

```powershell
Copy-Item backend\.env.example backend\.env
notepad backend\.env
```

For an existing installation, edit its current file and preserve its settings.
Set `S2SDN_OCR_PYTHON` to the full path printed by `$ocrPython`, set your KiCad root,
and set the correct OrCAD root if you use Capture. For an install with
`D:\tools\bin\orDb_Dll_Tcl64.dll`, the OrCAD root is `D:/`.

```powershell
Push-Location frontend
npm ci
Pop-Location
```

The production profile owns `IMAGE_MODE`, `S2SDN_OCR_DEVICE`, and
`S2SDN_TEXT_MODEL`; setting `IMAGE_MODE=vision` in an environment file does not
replace the pinned pipeline. Optional regional readers and resource bounds are
defined in `backend/pipeline_profiles.json`. Their availability is separate from
the local OCR checkpoint and from recognition accuracy. See
[recognition configuration](GENERAL_RECOGNITION.md).

## 7. Run the setup check and launch

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\check_setup.ps1

# Also require Capture's native automation files:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\check_setup.ps1 -RequireOrcad

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-native.ps1
```

The setup checker is read-only: it reports prerequisites and exits nonzero for a
missing required item. It does not install software, load a design, or certify a
license. The launcher creates missing environments, starts the services, waits
for their health endpoints, and opens the workbench. Follow the explicit setup
steps first so failures are easy to locate.

| Address | Service |
|---|---|
| `http://localhost:3100` | Workbench; use this host name for the Next.js assets. |
| `http://127.0.0.1:8100/health` | Backend health. |
| `http://localhost:3100/api/vision/status` | OCR configuration and last recorded execution status. |

After launch:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\check_setup.ps1 -ProbeServices
```

For a shortcut, run `install-desktop-app.ps1`. It adds Desktop and Start Menu
shortcuts pointing to this checkout; keep the checkout at that location.
The browser workspace includes a KiCad schematic viewer. The owned native KiCad
window is provided by `desktop/native_host.py`, which uses KiCad's `wx` runtime
and Windows WebView2; the browser app window is a distinct launch surface.

## 8. Make a first design and import a drawing

1. Choose **Open local workspace**, create a project, and send
   `create a voltage divider` in the assistant to exercise local design commands.
2. Attach `samples/orcad/Sample 4.jpg.jpeg` to the assistant and request recognition.
3. Inspect **Review circuit**: component values, physical pins, source comparison,
   review notes, and any provisional evidence. Save the review if needed.
4. Choose your export target. Confirm the review only after checking it against
   the source, then generate the design.
5. For Capture, inspect the saved-design preview and native readback report.
   **Open in OrCAD Capture**, expand the design and `SCHEMATIC1`, and open `PAGE1`.

The **Libraries & footprints → Blueprint → OrCAD Capture** drop zone also provides
a direct conversion path. Export readback checks that the saved file contains the
supplied graph; compare its interpretation and drawing with the original source.

## Troubleshooting

| Symptom | Check |
|---|---|
| Missing checkpoint or production hash mismatch | Verify the model path and hash in step 3. No fallback checkpoint is substituted. |
| CUDA requested but not confirmed | Check the separate worker path, NVIDIA driver, GPU runtime packages, and `api/vision/status` error. The production worker fails explicitly rather than silently switching to CPU. |
| Capture not found | `ORCAD_ROOT` must contain `tools/bin/tclsh.exe` and `tools/bin/orDb_Dll_Tcl64.dll`; a directory named `tools` is one level too deep. |
| Footprint/netlisting error | Inspect missing or review-required package assignments. A connectivity match does not certify physical package suitability. |
| Backend launch failure | Read `backend/.state/backend.log`. |
| Frontend launch or asset failure | Read `backend/.state/frontend.log`, use `localhost:3100`, and check Node/npm dependencies. |
| Changed environment but old behavior | The launcher reuses listeners already on ports 3100/8100. Restart the native server processes belonging to this checkout before retrying. |

`stop.ps1` currently stops Docker and the optional vision runtime; it does not
stop the native API/frontend listeners started by `start-native.ps1`. Avoid
terminating every Python or Node process on the machine. Workspaces live in
`backend/workspaces/`; runtime state and logs live in `backend/.state/`.

## Docker and CPU-only installations

Docker files remain in the repository, but this release's pinned production
profile requires a separate checkpoint and CUDA worker. The current container
packaging does not supply that complete native profile. Docker and CPU-only
startup have **not** been validated for this release; use the native guide above
for the published workflow. Neither the Windows Capture API nor a Capture
license is provided by the Linux containers.

## Developer checks

```powershell
& backend\.venv\Scripts\python.exe -m pip install pytest
$env:KICAD_CLI = 'D:\KICAD\bin\kicad-cli.exe'
$env:KICAD_SYMBOL_DIR = 'D:\KICAD\share\kicad\symbols'
$env:KICAD_FOOTPRINT_DIR = 'D:\KICAD\share\kicad\footprints'
$env:KICAD_PYTHON = 'D:\KICAD\bin\python.exe'
Push-Location backend
& .venv\Scripts\python.exe -m pytest tests -q
Pop-Location
Push-Location frontend
npm test
npm run build
Pop-Location
python tools\update_readme_stats.py --check
```

Tests that need installed CAD tools or local services depend on that machine's
configuration. Code tests, graph serialization, native readback, and source-image
recognition measure different things; the release results label their scope.
