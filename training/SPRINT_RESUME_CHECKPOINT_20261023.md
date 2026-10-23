# Schematic2SDN sprint: completed 23 October 2026

The user resumed this sprint with "continueee". All six phases and required final
gates are complete. The pause and remaining-work sections below are historical.
Final results: fresh 18-case gate passed; clear 227/245 (92.65%, +10 pins),
S4-scan300 44/72 (+6), native 103 valid pins / 9 correct pairs / 14 wrong pairs.
All previously correct observations were retained and no new incorrect native
pairs were added. Final backend suite: 361 passed, six skipped. Frontend:
14 tests and production build passed. Actual native KiCad and Capture readback:
18/18 graphs each, 2208/2208 observed assignments preserved in each format.
Protected OCR weights are unchanged. See PIPELINE_SPRINT_FINAL_20261023.md for
the exact per-sample and ten-design diffs, remaining errors and evidence.

Saved on 23 October 2026, approximately 12:59 IST. Resume in
`D:\DeCad-main\Jrk_DeCad\Schematic2SDN`.

The user asked to stop now and continue later. Do not restart work until they ask
to resume. The frontend build was intentionally stopped; no benchmark is running.
No automation or scheduled continuation was created.

## Last verified accuracy and commits

Phase 4 checkpoint: **cba4f08**, full fresh eighteen-case gate passed in
`evidence/pipeline-sprint-20261022/phase4-awake-final/`.
Clear score 217/245; ten native designs: 103 valid physical pins,
9 correct connected-pin pairs, 14 incorrect pairs. The Wio ESP32S3 pair
R1.2--R3.2 is the one accepted additional correct native connection.

Phase 5 commit: **6fd75bb**, fresh four-clear-case gate passed in
`evidence/pipeline-sprint-20261022/phase5-clear-fresh/`:

| Sample | Before | Fresh verified result | Change |
|---|---:|---:|---:|
| S1 | 52/56 | 54/56 | +2 |
| S3 | 59/69 | 62/69 | +3 |
| S4 | 67/72 | 69/72 | +2 |
| S5 | 39/48 | 42/48 | +3 |
| Total | 217/245 (88.57%) | 227/245 (92.65%) | +10, +4.08 percentage points |

All 217 previously correct labeled pins were retained, checked individually.
Recovered checkpoints: U62.13, U62.3, U24.4, U26.9, U7.11, U31.20,
U31.24, U37.21, U49.11, U58.3. The fresh gate has no errors and every
worker exited zero. Its `diff.md` and `diff.json` contain the exact comparison.

The cached crop probe scored 228/245; do not substitute that for the actual
fresh result of 227/245. The S4-scan300 cached crop probe improved 38 to 45/72,
but this degraded improvement still needs fresh full-pipeline verification.
The cached native probe retained 103/9/14 without regression; the final fresh
native gate has not run on the new local recovery code.

## User's required implementation direction

No sheet-wide all-or-nothing masking or terminal-anchoring veto. Preserve existing
confident assignments; recover individual missing/anonymous/ERC-conflicted pins
only with local source evidence. New targeted body-edge OCR runs regardless of
how many references the rest of the sheet recognizes. Production receives no
benchmark answers, pin identities to fix, or sample-specific rules.

Use fast cached/source-crop diagnostics and the four clear cases before an
expensive full gate. Do not return to repeated eighteen-case gates for each small
rule. Phase 5's four-case gate has passed, so finish Phase 6 and then run the final
full eighteen-case gate once the relevant source is frozen.

## Implementation already saved

`local_recovery.py`: local trace-to-label additions and catalog/order-supported
fused-digit repair. Global `require_complete` / `mask_complete` veto removed.
`terminal_recovery.py`: local perimeter stubs, bounded two-reader crop recovery,
package checks, duplicate/anonymous-terminal handling, local ink evidence.
`erc.py`: image-only pre-validation repair; duplicate flags, directional passive
snap within 8px, orphan labels within 15px, uncertain power/ground path splitting.
Manual JSON imports remain strict.

Phase 6 is **partly implemented**, saved in the pause checkpoint commit:

- `confidence.py`, ingestion evidence fields and source-coordinate hotspots.
  Scores are heuristics, not calibrated accuracy. Manual imports default to
  unscored; image proposals populate scores and sources.
- Source affine inversion, source dimensions, page frames and multipage metadata
  preservation in `recognition.py`.
- Authenticated bounded PDF/TIFF raster preview through the existing project
  file endpoint, with page selection and path checks.
- Next.js review panel amber overlays, per-region confirmation, score display,
  and stale-evidence handling after manual edits. Confirmation does not raise
  scores. UI source regions use actual source pixels, not PDF iframe chrome.
- `wire_graph.py` now exposes geometrically corroborated label graph nodes for
  ERC. This is a recognition-support change and must be covered by the final gate.

Phase 6 tests completed: **21 selected backend tests passed**, including confidence,
finite coordinates, multipage scopes, actual authenticated PDF preview, ERC and
simple geometry. **14 frontend model tests passed**. Earlier Phase 5 targeted
suite: **166 passed**. The Next.js production build was interrupted at user pause;
do not claim that build or browser verification passed.

## Remaining work after resume

1. Recheck saved source and status. Finish Phase 6 confidence/UI checks. Run the
   frontend build, fix real failures, and inspect the actual review overlay in
   the browser, including raster, PDF, page selection, confirmation and editing.
2. Complete actual KiCad and OrCAD DSN export/readback fidelity verification.
   This has **not been implemented or run** for this sprint's final pipeline.
   Existing OrCAD export can substitute/remap/drop pins and only checks an
   expected subset, so it is not proof of complete observed-graph fidelity.
   Read the export preparation notes in `backend/.state/sprint-20261022/PROGRESS.md`.
   A separately explicit lossless observed-graph mode should retain literal pin
   IDs, avoid hidden pins/remaps/drops, use reversible Capture net aliases, and
   compare all refs/values/pins/nets, including extras, after actual native reopen.
   KiCad already supports exact custom definitions via `engine.generated_symbol`
   and one-pin `connect()` calls to avoid accidental routed shorts.
3. Run the full backend suite, appropriate frontend tests/build and browser QA.
   Serialize memory-heavy checks, GPU evaluation and native CAD processes.
4. Freeze backend app source and run the final fresh eight-original/degraded plus
   ten-native gate. Baseline must preserve the new Phase 5 clear gains and Phase 4
   native gain. The Phase 5 report contains only four originals: construct an
   explicitly documented comparator combining those four with the other four
   actual Phase 4 records, or add an evaluator baseline overlay. Do not describe
   that comparator as a fresh eight-case run. Native baseline is
   `phase4-awake-final/native/` (103 valid / 9 correct / 14 incorrect).
5. Generate exact four-clear and ten-native deltas with `sprint_diff.py`; retain
   all previously correct observations and permit no new incorrect native pairs.
   Fix/rollback any genuine regression and rerun the necessary scope.
6. Update `training/COMPLETE_CIRCUIT_RESULTS_20261022.md` with final actual results,
   remaining errors, verification limits and phase logs. Commit completed Phase 6.

## Commands and guardrails

CUDA interpreter:
`backend/.state/claude-20261018/gpu-venv/Scripts/python.exe`.
Ordinary backend tests: `backend/.venv/Scripts/python.exe`, with `PYTHONPATH=backend`.
Native KiCad paths: `KICAD_CLI=D:/KICAD/bin/kicad-cli.exe`,
`KICAD_SYMBOL_DIR=D:/KICAD/share/kicad/symbols`,
`KICAD_FOOTPRINT_DIR=D:/KICAD/share/kicad/footprints`,
`KICAD_PYTHON=D:/KICAD/bin/python.exe`.
Frontend: `npm test`, `npm run build` in `frontend/`.

Never modify `checkpoints/schematic-ocr/model.onnx`. Protected SHA256:
`c5ad0e9ebe43373f1986ed5d6c39be0b73a29cb4dcb257e45ca7f91f41ce07cf`.
Do not train weights or activate rejected OCR adapters. Crop helpers only for
Qwen3-VL-8B, never full-page netlist generation. The local RoI service was
unavailable; no successful RoI accuracy gain was claimed.

Windows Modern Standby previously interrupted CUDA. `sprint_gate.py` holds a
temporary system-awake request and releases it in `finally`. Each worker exit
must be zero; a written provisional report alone is not success. A transient
GPU crash can retry once with separately preserved logs; accuracy regressions
are never retried as runtime failures. No power request remains after a gate.

There are extensive pre-existing dirty/deleted files and datasets. Never reset,
delete or stage unrelated changes. Stage only owned paths explicitly. Checkpoint
`digital_vision.py` in the task's `.state` folder before each edit. Do not spawn
subagents unless the user explicitly requests them. No permissions are needed
between authorized phases.

Browser skill was read and announced, but browser runtime was not initialized.
Use the browser-client module at the skill's absolute plugin path through the
Node REPL tool; read full browser documentation before interaction. The frontend
AGENTS.md and relevant installed Next.js guides have been read.

Detailed historical evidence and preparations remain in
`backend/.state/sprint-20261022/PROGRESS.md`. The master prompt remains in the
original attachment `C:\Users\mith1\.codex\attachments\3528dac1-591e-4eae-81eb-7e22f5c5abfe\Pasted text.txt`.
