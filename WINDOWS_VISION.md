# Windows setup using the supplied circuit adapter

> Historical workflow notes. Use the [current setup guide](docs/SETUP.md) and
> [recorded results](docs/RESULTS.md) for the pinned production profile and current published statistics.
> Older timings and experimental model settings below retain their original scope.

The supplied adapter is in `Jrk_Adapter/adapter` beside `Jrk_DeCad`. It targets
`Qwen/Qwen2.5-VL-7B-Instruct`. The adapter is approximately 40 MB; the separate
base-model and vision-projector weights are also required.

This setup uses the official llama.cpp Windows Vulkan runtime, a Q4_K_M base
model, a Q8_0 vision projector, and the supplied LoRA. It does not use the CUDA
training profile's 12 GiB GPU-memory requirement. All 224 supplied attention
tensors are preserved as float32 and checked during conversion; unknown tensor
layouts are rejected. Quantizing the base model can change predictions compared
with another computer or precision setting.

## First setup

Requirements: Python 3.11+, Docker Desktop running, and an updated NVIDIA
graphics driver with Vulkan support. Keep the supplied folder layout intact.
Allow approximately 12 GB on the project drive for downloads and preparation.

In PowerShell, from this directory:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-vision.ps1
```

The setup creates an isolated preparation environment under `backend/.state`,
downloads a pinned Windows native runtime and about 5.54 GB of base/projector
weights, checks published SHA256 hashes, converts the local adapter, configures
the Docker-to-host endpoint, starts vision, and rebuilds/starts DeCad.
Interrupted model downloads retain their byte-range blocks for resuming.
The supplied adapter and project schematics are not overwritten.

Runtime: llama.cpp b11669. Base/projector repository:
`ggml-org/Qwen2.5-VL-7B-Instruct-GGUF`, revision
`508edd0afaa66bb9e9f40587acc2184f02daf1f6`.

## Normal startup

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

The launcher detects the configured vision endpoint and starts the native model
server. To start only that process:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-vision.ps1
```

The initial profile offloads 22 language-model layers and the output tensor to the NVIDIA GPU, keeps
the vision projector on the CPU, uses one inference slot and an 8192-token
context, and unloads idle model weights after 120 seconds. If GPU memory is
insufficient, stop the process recorded in `backend/.state/vision-server.pid`
and retry with `-GpuLayers 18`. This is a memory-limited inference profile;
successful installation alone does not establish its fit or accuracy.

## In the application

Open http://localhost:3100. The vision status must report the model
`schematic2sdn-qwen-vl` as available. Image/PDF recognition automatically selects
**Vision: components and connections** when the backend is configured for vision.
An explicitly selected alternative remains selected for that browser session.

Attach the schematic. Recognition produces a circuit proposal for review.
Check references, values, exact KiCad symbols, physical pin numbers and every
net against the source before applying it. A vision error is reported directly;
the application no longer silently substitutes the basic R/C/V CPU recognizer.
Truncated or empty model output is rejected.

After a reviewed circuit is applied, **Download > PCB autorouter Specctra DSN**
opens footprint/placement settings and produces `board.dsn` plus an editable
`board.kicad_pcb`. This is Specctra PCB routing DSN. OrCAD Capture schematic DSN
requires a separate licensed workflow.

## Diagnostics and limits

```powershell
Invoke-RestMethod http://localhost:3100/api/vision/status
docker compose ps
Get-Content backend/.state/vision-server.stderr.log -Tail 40
```

The host inference server listens on port 11436 with an API key generated in
`backend/.state/vision-api-key`; Docker uses `host.docker.internal`, not its own
localhost. The key is saved in the ignored local `.env` and is not printed.

Model loading, successful inference and source-equivalent connectivity are
separate checks. Dense scans such as `Sample 1.jpg.jpeg` may require crops and
manual reconstruction. No general circuit-accuracy benchmark is supplied with
this adapter, and an ERC pass cannot establish agreement with the source image.

## Observed Windows verification, 16 October 2026

The native runtime loaded the supplied adapter on this RTX 3050 Laptop GPU
(4 GB VRAM, approximately 8 GB system RAM). All 224 adapter tensors matched the
supplied float32 weights exactly, both model downloads passed their published
SHA256 checks, and the adapter tokenizer matched the GGUF vocabulary.
The application reported the model available and native inference completed.
Fifteen targeted backend tests, five frontend tests and the frontend production
build passed.

Accuracy checks failed. On `examples/divider.png`, the supplied adapter found
V1=5 V and R1=R2=10k, but connected the pins incorrectly. The same check with
the adapter disabled returned a pin assigned to multiple nets and was rejected.
A large-sheet trial on `Sample 1.jpg.jpeg` did not finish within its 14-minute
request budget. No recognized proposal was applied to the user's project.
These observations establish Windows runtime compatibility, not exact
automatic schematic reconstruction. The test evidence is in
`evidence/windows-vision-2026-10-16.json`.
