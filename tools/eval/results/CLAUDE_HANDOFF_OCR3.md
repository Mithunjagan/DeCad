# Claude → Codex handoff: OCR recovery + wiring (ocr3), 2026-10-18

Claude owns `digital_vision.py` and the OCR checkpoint for this work (COORDINATION_CODEX.md).
**The live recognizer was NOT replaced**: copying over `backend/app/digital_vision.py` was blocked by
the user's permission rules (shared live file). Everything below is staged and verified; apply it at
your coordinated backend restart, or the user may let Claude do it.

## Apply

```
copy backend\.state\claude-20261018\ocr3\digital_vision.staged.py  backend\app\digital_vision.py
copy backend\.state\claude-20261018\ocr3\test_ocr_recovery.py      backend\tests\test_ocr_recovery.py
```

| File | MD5 |
|---|---|
| live `backend/app/digital_vision.py` (base, = Task 3/4) | `fb46ab5ebadd90ecbf541b9cf5718140` |
| staged `ocr3/digital_vision.staged.py` | `9ca5e293e2025ccba87d2b267c778654` |
| staged `ocr3/test_ocr_recovery.py` | `a1f8778b3b7f8407204047ff11481a14` |
| `checkpoints/schematic-ocr/model.onnx` (**unchanged**) | `cfbd935ce69b195b0a7f8d2db9788af4` |

Diff: `ocr3/ocr3.patch` (773 lines, against the live file). Snapshot of the measured state: `ocr3/digital_vision.snap-213.py`.

## Verified results (8 inputs, saved OCR tokens + **live** pin strips, GPU venv; scored by run_eval's scorer, every DSN reopened and verified)

| Input | Exact pins (accepted → staged) | Parts | Values | Spurious |
|---|---|---|---|---|
| S1 | 34 → **51**/56 | 23 → 24/28 | 23 → 24 | 0 |
| S3 | 40 → **59**/69 | 27 → 30/34 | 25 → 29 | 1 → 1 (R1, pre-existing) |
| S4 | 60 → **64**/72 | 24 → 25/30 | 22 → 24 | 0 |
| S5 | 24 → **39**/48 | 19 → 22/25 | 15 → 21 | 0 |
| **Total** | **158 → 213/245 (64% → 87%)** | | | |
| S2 (partial GT) | – | TC514100 7/16, 74F374 4/8 (was 5: the 5th was a duplicate of U43, checked in the image), 74F244 2/4 | | U_n 10 → 9 |
| scan300 | 37 → 38/72 | 24 → 25/30 | 23 → 24 | 4 → 4 |
| scan200 | 0 → 0 | 18 → 18 | 18 | 1 → 2 (2nd half of U33/U25 as U_n) |
| blur300 | 0 → 0 | 12 → 12 | 12 | 2 → 3 (same: unreadable 2nd sections) |

Unit tests: `test_ocr_recovery.py` 10 passed; `test_digital_vision.py` passes against the staged module.
`test_ocr_review.py::test_spatial_ocr_ignores_net_labels_and_distant_values` fails **on the live module too**
(Tesseract `ocr_candidates` in ingestion.py, Codex-owned) – pre-existing.

A fresh full gate (`codex_verify.py`, fresh OCR) is still yours to run after applying.

## What changed (all evidence-based; each rule names its source case in a comment)

References / parts (user's tasks 1–3, 5):
- Misread U references repaired beside an unclaimed IC part number: `!84 L61 US8 089 C17 |59` → U84 U61 U58 U89 U17 U59;
  a blurred S tries 5 then 8 and takes the one already on the sheet with the same part (`US5` → U85).
- Zoomed area re-read must agree at two enlargements; the fine-tuned text reader reads a reference RapidOCR cuts short
  (`U` for U7 in S3: three crops, all must agree ≥ 0.95).
- `UNKNOWN` from one drawing of a gate is replaced by the part number printed on another drawing (S5 U4 → 74F00).
- Part numbers prefer their reference's text direction (rotated pin text "31822" no longer beats horizontal "2148").
- Sheet-evidence family repair: `74F!61` → 74F161, `74F24U` → 74F240, `745174` → 74F174 when 74F174 is printed elsewhere
  (74S174 is a real family and is kept).
- Fused all-digit tokens split at the printed space (`BB2 65`); all-digit numbers outside a body or without a reference are
  never parts (`88463` = "BB4 63").
- U_n placeholders kept for lettered part numbers on clear sheets too (task 1); never for all-digit strings.
- **Blurred / < 300 dpi pages: no guessing.** No enlarged re-reads and no non-U repairs there (they invented U187 for U87);
  a "Review required … rescan at 300 dpi" note is added to those pages (task 5).

Wiring (pins):
- `_bridge` tolerates ~0.18 ch sideways drift of a long edge; `seg_boxes` chains broken edges, and a box's top/bottom must
  reach its corners (one of them each) → U43 (S1) gets its real box; the bus-paired composite boxes around U13–U16 are gone.
- `_merge_boxes` keeps a much smaller box inside a larger one (bodies inside wire rectangles); `body_at` picks by pin ends.
- `_cells`: a narrow run merges into a glyph only within 0.3 ch (was: any distance) – a sliver of the body outline no longer
  turns "6" into "61"; `_strip_words` drops such a sliver at the pin end and splits "SPWE4 14" (narrow 1) at its widest step.
- `pin_sequences`: per body edge, fill unread/duplicated/overlong numbers from the edge's numbering (≥3 reads, 60% fit;
  unique plausible reads never overridden – AM2910's 34 36 38 40 2 4 stays).
- `symbol_consensus`: identical drawings of one part (4× 74F194) lend pin numbers; a copy is changed only where ≥2 of its own
  pins already agree, so other sections of a multi-section part are never renumbered.
- Label families: a lost thin leading glyph (`NBU14`) joins its family (INBU14).

Robustness / speed:
- `char_height`, `dots`, `segments` run in overlapping bands (identical output, checked on S1) – S5 (14k px) no longer
  dies with `cv::OutOfMemoryError` when ~1 GB RAM is free.
- **GPU**: `use_gpu()` turns on CUDA when onnxruntime-gpu + CUDA 12/cuDNN 9 are present (`S2SDN_OCR_DEVICE=cpu` turns it
  off). RapidOCR's sessions are rebuilt with heuristic conv search, exact-size arena and a 1.5 GB cap (its built-in
  EXHAUSTIVE/power-of-two settings exhaust Windows commit). S4 token OCR: CPU 63.0 s → GPU 21.8 s; end-to-end S4 on GPU
  scores exactly as on CPU (25 parts, 24 values, 60/72 then). To enable in the live backend at your restart:
  `pip uninstall onnxruntime` + `pip install onnxruntime-gpu==1.22.0` in `backend\.venv`, and set
  `S2SDN_CUDA_DLLS=<py3.12 site-packages>\torch\lib` (torch 2.5.1+cu121 there ships cudart/cublas/cudnn 9). Without it the
  code runs on CPU exactly as before. A tested GPU environment exists at `backend\.state\claude-20261018\gpu-venv`.

Rejected after measurement (not in the staged file):
- Retrained text reader (`ocr3/model-new`, fine-tuned on S1–S3 crops on the RTX 3050 in 122 s): holdout crops 83.5% → 86.6%,
  but S4 end-to-end exact pins 60 → 52. **Checkpoint left unchanged.** Training script now supports `--init` and `export`.
- Row-wide strip side choice (S1 34→33, S4 60→59) and wire-to-text gap side choice (all four sheets worse). Reverted.

## Also fixed (live, outside recognition)

- `backend/app/formats.py`: `Path` was used without import – SPICE export of any diode/transistor without explicit models
  raised `NameError`. Added `from pathlib import Path` (backup `claude-20261018/formats.py.before-claude`). The four related
  test files fail identically with and without the fix when `KICAD_CLI` is unset; with `KICAD_CLI` set, 52 pass.

## Findings for Codex-owned files (not changed)

- `tests/test_integrations.py::test_model_failure_does_not_mutate`: `/ai/plan` now returns 200 for a malformed model reply
  (`{"kind":"bad"}`), the test expects 422 – an intended local fallback or a regression in the assistant route.
- `tests/test_ocr_review.py::test_spatial_ocr_ignores_net_labels_and_distant_values` fails on the live code (ingestion).
- Backend tests that need KiCad fail with "KiCad CLI is unavailable" unless `KICAD_CLI` is set (start-native.ps1 sets it;
  a bare pytest run does not) – consider a conftest default to `D:\KICAD\bin\kicad-cli.exe` when present.

## Design assistant: opt-in cloud chat (user request, 2026-10-18 ~16:20 IST)

The user asked Claude to add NVIDIA's `nvidia/nemotron-3.5-super-vl-120b-a12b` to the design assistant.
Changed (Codex-owned file, user-authorized; backup `claude-20261018/model_runtime.py.before-claude`, md5 678f9bd6…):
- `app/model_runtime.py`: `chat_provider()` / `cloud_chat()` – OpenAI-compatible chat for `explanation` and
  `circuit_planning` only, **off unless `CHAT_API_URL` and `CHAT_API_KEY`/`NVIDIA_API_KEY` are set**; temperature 0,
  `enable_thinking: false`, strict JSON schema when given, 60 s limit. Any cloud failure falls back to the local
  Ollama model (`notice` in the result). Results carry `provider`. `/models/status` gains `cloud`
  {model, host, ready, data_leaves_device: true} and per-task `provider`/`local_fallback` – the UI could show a
  "sent to NVIDIA" notice from it. Image recognition never uses it.
- `plan()` no longer substitutes a voltage divider when the model reply is unusable: it raises (422). This makes the
  previously failing `test_model_failure_does_not_mutate` pass; `test_integrations.py` 12 passed with KICAD_CLI set.
- `.env.example`: commented settings + data notice. New `tests/test_cloud_chat.py` (5 passed).
The running backend needs your coordinated restart to load it. No key is stored anywhere.
- 16:30 IST: user supplied an NVIDIA key; it is in `backend/.env` (gitignored) as `CHAT_API_URL` + `NVIDIA_API_KEY`.
  Live check through `model_runtime`: status ready; planning "blink an LED once a second" -> `timer_555` (1.0 s,
  schema-valid); explanation correct (1.3 s); provider=cloud, no fallback. **Restart the backend to load it.**

## APPLIED (user approved, ~16:35 IST)

`backend/app/digital_vision.py` is now the ocr3 version (md5 `9ca5e293e2025ccba87d2b267c778654`; previous live copy
`ocr3/digital_vision.live-before.py`, md5 `fb46ab5e…`), and `backend/tests/test_ocr_recovery.py` is in the suite.
Tests on this exact content: test_ocr_recovery 10 passed, test_digital_vision passed (run against the identical staged
file). The running backend still has the old module and env loaded: **restart it** to pick up the recognizer, the
cloud chat and `backend/.env`. Your fresh eight-input gate (`codex_verify.py`) is the next acceptance step.

## Compact DSN layout (user request after seeing dead space in Capture, ~16:45 IST)

User-authorized change to Codex-owned `orcad_writer.tcl` / `orcad_capture.py` (backups
`claude-20261018/*.before-claude`). Source placement stays as the starting point; with `set compact 1` (now the
default whenever parts have source positions; `DSN_LAYOUT=source` restores exact source distances) the writer
slides parts left then up, twice, each stopping one channel (150 x 120 units, beyond the keep-out box that already
holds stubs and labels) from the parts it faces. Facing order is kept, keep-out boxes never overlap. Stubs are now
drawn after the final placement. Unpositioned parts (connectors) start in a strip right of the sheet instead of
below it. Page = content.
Pages: S1 6600x~4700 -> 3900x2600, S3 5900x2700, S4 4800x2800, S5 4700x2100, S2 4400x2300; all reopen-verified,
all **routed wires** (no label fallback). Tests: `test_positioned_dsn_...` pinned to DSN_LAYOUT=source; new
`test_compact_dsn_keeps_arrangement_without_overlap`; with test_orcad_route: 4 passed (real Capture, 167 s).

## Fresh full gate on live ocr3 (2026-10-18, Claude, GPU venv)

`gpu-venv python tools/eval/codex_verify.py claude-ocr3-gate` - fresh OCR on CUDA, all 8 inputs, every DSN reopened,
all 8 PCB netlists 0 errors. Live `digital_vision.py` MD5 `9ca5e293...` (= staged ocr3).

| Input | Exact pins | Parts | Values | Spurious | Time |
|---|---|---|---|---|---|
| S1 | 51/56 | 24/28 | 24 | 0 | 53 s |
| S3 | 59/69 | 30/34 | 28 (replay 29: U36 read 74S163, U83 74BCI2244) | 1 (R1) | 73 s |
| S4 | 64/72 | 25/30 | 25 | 0 | 49 s |
| S5 | 39/48 | 22/25 | 21 | 0 | 56 s |
| **Total** | **213/245 (87%)**, identical to the replay | | | | |
| scan300 | 38/72 | 25/30 | 25 | 4 | 58 s |
| scan200 | 0/72 | 18/30 | 18 | 2 | 54 s |
| blur300 | 0/72 | 12/30 | 12 | 3 | 55 s |

Gate exit 1, flags vs the old `supplied-baseline.json`, all expected in this handoff: S2 74F374 5->4 (the 5th was a
duplicate of U43), scan200/blur300 +1 spurious each (unreadable 2nd gate sections kept as U_n). Suggest re-baselining.

## 20:30 restore (Claude)
Antigravity's interrupted blur-pin attempt lowered S1 51->45, S4 64->63, scan300 38->26 (blur/scan200 still 0) in its
19:58 gate, then edited again at 20:06 unmeasured. Restored live `digital_vision.py` to ocr3 (MD5 9ca5e293..., the
claude-ocr3-gate version); 21 recognizer tests pass. Antigravity's file + report saved in `backend/.state/antigravity-20261018/`.
Its `backend/app/library-pin-sides.json` and `orcad_pin_sides.tcl` are left in place and unused by ocr3.
