# Verification — 11 October 2026

This is a release candidate, not a fully approved three-OS or general image-recognition release. The original Desktop ZIP was not modified.

## Observed results

- Final Linux-container regression suite: **73 passed**, one Starlette test-client deprecation warning, 17.58 seconds. See `test-results.txt`.
- Production frontend and final Docker images built successfully.
- Live same-origin API acceptance: **12 checks passed**, including native KiCad ERC, actual ngspice and Qucs-S simulation (divider 2.5 V), all four bundle checksums, waveform import, host bridge discovery and native synthetic generation. See `live-acceptance.json`.
- Actual pretrained qwen3:0.6b planning evaluation: 3/3 controlled cases. A separate live reviewed divider proposal produced 6 V from 12 V in 6.718 seconds. This is narrow evidence, not general model accuracy.
- Split-supply regression preserves separate VSS and GND rails in native ngspice and Qucs-S simulation. Dataset grouping also rejects renumbered topology leakage.
- Backend/GUI processes run under the configured host UID/GID after a root ownership bootstrap. The container and this Mac both read and wrote a private shared bridge probe successfully. Core restart and health recovery were checked.
- Actual ngspice binary RAW import recovered 108 samples, with voltage channels retained and current channels identified separately.
- Production npm and resolved/runtime Python dependency audits reported zero known vulnerabilities at audit time. Reports are in `evidence/`. This is not a security certification.

## Implemented operations and limits

Native KiCad placement, physical pin connections, source parsing, edits, undo/redo, SVG/XML/JSON/SPICE/EDIF/BOM export and ERC are exercised. Invalid mutations roll back. Text/PDF/DOCX/CSV imports, authentication/path isolation, history, model proposal review, external transient CSV/RAW import and bridge argument validation are covered. GitHub OAuth/push use mocked external responses in tests; live account acceptance remains unverified.

KiCad, ngspice, LTspice and Qucs-S export bundles are implemented. Qucs-S native schematics are compiled by the actual Qucs-S CLI and simulated using ngspice. Actual host KiCad discovery passed. Actual LTspice execution and Windows/Linux desktop launches remain unverified. LTspice is free proprietary software installed separately. Native OrCAD DSN is not implemented; connectivity EDIF is provided. Unsupported device models/simulation formats return errors.

CPU circuit recognition is now the default image mode. It associates OCR references/values with clean R/C/V symbol geometry and traces wire-connected pins. Labels-only OCR remains an explicit mode. Independently specified divider/RC pixel fixtures exercise exact component values and pin/net topology at multiple image sizes, plus PDF and native schematic/simulation checks. An unreadable reference and an unmarked crossing are rejected rather than silently accepted. Florence-2 and general vision acceptance remain unimplemented/unpassed respectively.

The package contains four image/JSON/SPICE pairs across two families, no trained checkpoint, and no installed CGHD/AMSnet/Masala-CHAI corpus. The training audit, GPU LoRA trainer, adapter server and held-out evaluator are supplied. GPU training and adapter inference have not run; protocol and failure handling tests use mocks. See `training/README.md`.

## Resource and remaining acceptance

Docker allocation remained approximately 4 GiB. Core caps are 1 GiB and 512 MiB. Optional language inference is capped at 2 GiB, two CPUs, one request/model and no extra swap; requests unload afterward. Large vision inference is opt-in or hosted separately. Launchers never increase Docker Desktop memory. These caps do not prove acceptable performance on every user's machine.

Current frontend source/build/API checks passed, but its latest UI could not receive visual acceptance because browser access was rejected by the browser security policy. No alternate browser was used. Previous screenshots are not evidence for the latest UI. Actual Windows/Linux installation, current UI interaction, real LTspice round-trip, GPU training/evaluation, licensing review and measured representative hardware performance remain release gates in `RELEASE_GATES.md`.

## Subsequent completion work

Adapter directory corrected to checkpoints/circuit-lora/adapter; three protocol tests passed after the change. Four recorded-release-gate tests passed. Unix launcher syntax validated; Windows launcher changes require its CI/native acceptance. Local model startup now requires explicit opt-in. An additional separate AMS-Net development bundle contains 734 checksum-recorded image/SPICE pairs with available bounding boxes and upstream LICENSE. Zero have been approved as training-ready annotations; they are not loaded by or packaged inside the runtime application. GPU training remains unexecuted.

## Latest PDF / OrCAD handoff changes

Final local Python regression: 71 passed, four skipped (native ngspice/Qucs-S unavailable in this host environment), one test-client deprecation warning. Earlier container suite had 73 passes before these changes; it is not evidence for the latest source. Current frontend production build passed; four release-evidence checks passed. Docker rebuild failed with socket permission denied despite requested/granted socket access, so latest container and live endpoint acceptance remain unverified. Latest UI visual acceptance also remains open.

PDF schematics with labels are routed through visual extraction unless explicit SPICE control directives identify embedded netlist text. PDF raster dimensions are bounded before rendering; vision multi-page hierarchy merging is rejected explicitly. OrCAD handoff exports reviewed graph JSON, connectivity-only EDIF and checksums without fabricating a DSN. Native editable OrCAD DSN generation and general image connectivity recognition remain unavailable/unvalidated respectively. See ORCAD_STATUS.md.

## Specctra clarification and implementation

The requested .DSN is clarified as free Specctra PCB autorouter format. Native export, editable board/project, explicit footprint/placement/routing plan and independent PCB/DSN pin/net comparison are now implemented. Full local suite: 72 passed, four skipped; frontend production build passed. A targeted native test passed again after pad-bound checks, with custom track-width and invalid physical-pad/path rejection. Authenticated API export passed. Freerouting 2.0.1/Java 21 routed a fixture and KiCad reimported its SES (seven tracks); memory cap 512 MiB/two CPUs. Evidence and actual examples are included. Latest Docker rebuild, current visual UI, Windows/Linux and broader design/routing/manufacturing acceptance remain unverified. General recognition and custom training gates remain open. Native OrCAD schematic DSN is a different unsupported format.

## CPU recognition and toolbar update — 11 October 2026

The editor toolbar wraps inside its own grid column, and the central column can shrink without spilling Download controls over the assistant title. Circuit recognition is selectable per attachment and defaults to the bounded CPU path, with no model download. Low-pass spelling variants and missing-attachment feedback are implemented. GitHub credentials are preserved in the active installation and excluded from release archives.

Recognition scope is clean R/C/V schematics with readable references/values and explicit wires. The four supplied dataset pairs did not reach exact graph agreement; their annotations/source drawings need review. This is not an approved general-purpose recognition model, a trained checkpoint, or proof of Windows/Linux/current visual UI acceptance.

Final native Docker suite: 89 passed, including attachment upload → recognition proposal → explicit reviewed import → native simulation. Production frontend/core images built successfully. Live localhost health returned ready, native KiCad/ngspice available, GitHub configured, and CPU circuit mode ready. A fresh run of the four provided image pairs rejected all four for unresolved symbol/reference associations (0/4 exact graphs); raw results are in evidence/cpu-provided-pairs-benchmark.json. Successful independent fixture tests are engineering regressions, not a held-out accuracy benchmark. Current browser UI appearance could not be visually checked in this session.

## Guided workflow and bounded training update — 11 October 2026

- Added editable component/net review with source preview, component-reference propagation, duplicate pin validation, explicit reviewed apply, and optional advanced JSON. Failed assistant requests retain their text and attachments.
- Replaced the Specctra JSON prompt with board dimensions, routing rules, placement preview, installed-footprint search, and required physical-pad checks. Native export retains independent PCB/DSN pin/net comparison. Server validation rejects malformed/nonfinite plans and unsafe library identifiers.
- Added an experimental Qwen2.5-VL-3B four-bit training profile with bounded image/text tokens, frozen vision parameters, mandatory matching smoke report, memory-headroom reporting, OOM stop, and preservation of existing adapters. The adapter server supports both registered profiles. No CUDA training or 8 GB GPU fit validation was performed.
- Final validation: **104 backend/native tests and 5 form-model tests passed**, frontend/core production images built, live health and authenticated native footprint lookup passed, GitHub remained configured. The existing Desktop .env was checksum-checked as unchanged during deployment.
- Six serial 800×800 R/C/V fixture recognitions under a 1 GiB/two-CPU container cap took 0.728–0.970 seconds. Python peak RSS was 111,840 KiB; this is a process measurement on narrow fixtures, not whole-container peak usage or minimum-hardware certification.

Evidence is in evidence/product-*. Current browser visual acceptance, broad recognition accuracy, actual CUDA training, LTspice native round-trip, and Windows/Linux desktop acceptance remain pending. The release checker still reports blockers; no unavailable check was marked passed.

## Assistant submission and selected-output repair — 11 October 2026

- Reproduced the reported upload failure: filenames containing spaces were rejected by the project-name validator. Upload names now support spaces and normalized Unicode, retain safe cross-platform filename restrictions, and return canonical paths. Image previews have correct MIME types and encoded Unicode download headers. Failed uploads no longer trigger an analysis of nonexistent attachments; errors appear in the assistant.
- “create a voltage divider”, “Describe a voltage divider”, and “I need a voltage divider” create a real native circuit. Existing conflicting components are preserved in a separate project when using the assistant.
- Assistant output selection now generates and verifies KiCad, ngspice, LTspice or Qucs-S bundles; successful results provide a download. Reviewed image imports use the same selected output. LTspice output is a SPICE netlist, not a native drawn ASC schematic; Qucs-S uses its tested SPICE wrapper.
- Generated diagrams use saved native KiCad SVG previews by default, with separate embedded editing. Switching display mode no longer clears assistant messages. Editor switching uses graceful window closure, handles KiCad’s confirmed empty standalone frame, and ignores exited zombie processes. Loaded schematics and unsaved-change dialogs are never forcibly terminated. Docker init reaps child processes.
- Final suite: **118 backend/native tests, 5 form tests passed**. Frontend/core production images built. Live API checks recovered three components/three nets and 2.5 V for the exact user request, validated every bundle SHA-256 manifest, and completed spaced-name fixture upload → review → native import → LTspice output. Two successive embedded project activations passed. Evidence is in workflow-* and native-switch-check files. Current browser visual acceptance was not performed.
- The actual Sample 1 image uploaded successfully, but CPU recognition rejected its 69.6-million-pixel size with an explicit 422 message. It is a complex IC/bus schematic outside the current clean R/C/V recognizer’s supported scope. No general extraction accuracy, custom trained checkpoint, or completed cross-OS shipping approval is claimed.
- Actual divider application bundles are included in examples/voltage-divider-output.
