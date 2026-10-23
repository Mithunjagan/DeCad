# Circuit reconstruction results, 22 October 2026

The deliverable being pursued is a reusable image-to-circuit recognition system. Exported DSNs are not evidence of model accuracy.

## Implemented recognition change

Generic IC captions were previously added after pin extraction, leaving identifiable chips with no recognized physical terminals. Recovered captions now supply chip bodies before pin extraction. A companion geometry guard prevents MCU pin-function labels such as P0.02 inside newly recovered chip bodies from being mistaken for external connector references. Existing caption/value identification rules remain in use.

The first version was rejected: it introduced three incorrect connected-pin pairs on an MCU pinout sheet. That rejected source and results are retained. The guarded revision passed all ten additional real native designs: valid physical-pin coverage rose from 62 to 103, with 60 correct component references retained, eight correct connected-pin pairs retained, and fourteen pre-existing incorrect pairs unchanged. The 41 additional physical pins are not 41 newly correct net assignments. Native targets can contain hidden fields/pins, so this is native-graph coverage, not certified image accuracy. Original-sample acceptance remains recorded separately.

## Actual complete-circuit VLM evaluation

Pinned Qwen/Qwen3-VL-8B-Instruct was evaluated on three original real complete schematic exports. Source answer graphs stayed local. This was inference, not model training. Full output prompts and runtime reports are retained. One revised prompt requested compact JSON, distinguished internal pin functions from external net labels, and rejected shared UNKNOWN/NC names that could short unresolved terminals.

Revision 1: two of three outputs parsed. On the 25-component three-timer design, the model read 25/25 references and 67/67 physical pins, but only 85/229 true connected-pin pairs, adding 81 wrong pairs. Revision 2 still failed two cases within its per-case generation budget. On the timer case, it found 25/25 references and 67/67 pins, but only 92/229 true pairs and 138 wrong pairs. Neither revision satisfies the no-regression requirement. Neither is activated as a replacement. More correct references or pins alone is insufficient to accept incorrect connectivity.

## Reusable candidate entry point

In a separate two-T4 CUDA environment with the tested transformers 5.20.2, bitsandbytes 0.50.2 and accelerate 1.15.0:

```powershell
python training/circuit_vlm.py --image "C:/path/to/new-real-schematic.png" --output "C:/path/to/new-candidate-result"
```

This loads the pinned base model, not the rejected OCR LoRA. It accepts a new image without a reference netlist and writes circuit.json only for a complete parseable prediction. This candidate is experimental and must not be presented as a reliable complete-circuit model. The Kaggle notebook reproduces the real inference check; its uploaded manifests contain no reference graphs. Local model serving and arbitrary-input correctness are not established.

See ../evidence/fullgraph-20261022/ for fresh recognition gates, original predictions, reference provenance, per-design missed/extra connectivity, rejected candidates and final acceptance decision. Source licenses accompany the private evaluation images. No new synthetic/AI training examples or pseudo-labels were introduced. The existing production OCR and circuit-adapter model weights remain unchanged.

## Final acceptance

The guarded caption/pin fix passed fresh recognition of all ten additional native designs and all eight original/degraded cases. All original component and net graphs are identical to their accepted baselines. Forty-one additional valid physical pins were measured across the ten-design native corpus, with no previously correct values/pins/connections lost and no additional incorrect connected-pin pairs. The existing fourteen wrong native pairs remain unresolved. Forty-nine relevant tests pass. Protected model.onnx SHA256 remains c5ad0e9ebe43373f1986ed5d6c39be0b73a29cb4dcb257e45ca7f91f41ce07cf. Clear-sample annotated pin-to-net score remains 217/245 (88.57%); Sample 2 has no complete reference and is excluded. Full-circuit and arbitrary-input accuracy remain unestablished.

## Maximum-accuracy pipeline sprint: Phase 1

The starting checkout was checkpointed in commit 874b921 before integration. Fresh baseline recognition reproduced all eight accepted component/net graphs exactly. Phase 1 is commit c68291d: a shared hybrid_max_accuracy profile now controls the API, native launcher, CLI benchmark, CUDA OCR checkpoint, and restricted RoI model configuration. PDF documents retain native paths/text through page dispatch; native PDF extraction was exercised on three original real KiCad designs. This is geometry extraction evidence, not proof of their complete circuit accuracy.

| Fresh CUDA case | Before exact labelled pins | Phase 1 exact labelled pins |
|---|---:|---:|
| S1 | 52/56 | 52/56 |
| S3 | 59/69 | 59/69 |
| S4 | 67/72 | 67/72 |
| S5 | 39/48 | 39/48 |
| Clear total | 217/245 | 217/245 |
| S4-scan300 | 38/72 | 38/72 |
| S4-scan200 | 0/72 | 0/72 |
| S4-blur300 | 0/72 | 0/72 |

S2 remains excluded from labelled-pin accuracy because its annotation is incomplete. All eight measured cases passed per-observation regression checks. Phase 1 ran 103 relevant tests successfully. A broader baseline run with actual local KiCad paths found 272 passing tests, six skips, and four pre-existing failures: three outdated second-reader test callbacks and a training/inference prompt contract mismatch. The callbacks and shared prompt metadata were repaired without training or altering weights; their targeted checks pass. A final complete-suite rerun is still pending at this stage.

Raw fresh predictions, per-case CUDA provider records, logs, vector-PDF exports and gate decisions are in evidence/pipeline-sprint-20261022/. Protected model.onnx SHA256 remains c5ad0e9ebe43373f1986ed5d6c39be0b73a29cb4dcb257e45ca7f91f41ce07cf.

## Pipeline sprint: Phase 2

Fresh CUDA recognition and the cached library check retain 217/245 clear labelled pins, with degraded scores 38/72, 0/72 and 0/72. All eight component/net graphs are identical to the fresh baseline. 107 relevant tests pass. Extreme-scale and uneven-paper normalization, stroke measurement and exhaustive overlapping tile coordinates were added. Additional tiled/inverted text views are restricted to cases where the original OCR pass reads no confident reference; three confident references are required before adding their observations. Existing clear and degraded reads remain the primary pass.

Rejected experiments are preserved in phase2-probe/, phase2-trial/ and phase2-revised/. Using 1024px tiles on clean S4 retained 67/72 labelled pins but added two false components and lost the correct U16 value. Global quarter-turn normalization misinterpreted a mixed-orientation sheet: S1 fell from 52/56 to 12/56. Smaller tiles on degraded S2 lost TC514100 and 74F374 counts. Those policies were rolled back; they are not enabled as defaults. The remaining orientation helper is experimental and is not used to rotate the sheet in production. No accuracy improvement is claimed for these rejected trials.

## Pipeline sprint: Phase 3

The final fresh gate passed all eight original/degraded cases and all ten original real native designs. Clear labelled-pin score remains 217/245; valid native physical-pin coverage remains 103, correct connected-pin pairs remain eight, and the fourteen pre-existing incorrect pairs remain unchanged. 118 relevant tests pass. Catalog size was checked directly from the read-only SQLite database: 91,494 unique names.

Component helpers use only a bounded symbol crop plus 48px margin and a strict schema with reference, literal marking, physical pin number, internal function and side; netlists and external connections are excluded from that schema. New pin recovery requires package agreement and observed ordering anchors. Functionally reordered symbols are not forced into a package's counter-clockwise numbering order. Internal function spelling and body geometry jointly exclude phantom ports, including P0.02. The first broader body-only filter removed the real J1 connector in S5 and was rejected; its gate artifacts remain in phase3/.

Live service limit: the base Qwen3-VL-8B endpoint was unavailable. The configured original Qwen2.5-VL-7B circuit adapter was started and queried on one real U15 crop, but timed out at 90 seconds without an accepted response. It was stopped before the OCR gate because this 7.3GB-RAM machine had only about 0.1GB free with that service loaded. No RoI-model accuracy improvement is claimed. The successful final OCR/native gate preserves local readings when helpers are unavailable. Actual attempts, timeout and source crop coordinates are retained in roi-live/; final gate artifacts are in phase3-revised/.

## Pipeline sprint: Phase 4 rejected candidates and safety guard

Mask-then-trace adds a text/body-masked wire canvas, banded directional gap repair and one-pixel skeletonization, explicit conductor ports at crossings, terminal anchors, and physical-before-symbolic graph metadata. Plain crossings remain separate unless a junction dot is verified; ambiguous intersections use bounded crop helpers when a service is available. The geometry and review metadata are diagnostic whenever the terminal-anchoring gate is incomplete. Confidence values here are heuristics, not calibrated accuracy probabilities.

The first revised fresh gate kept all four clear sample scores at 217/245, then failed the first real design (Grove Vision AI V2): its 29 valid pins stayed unchanged, but correct connected-pin pairs fell from 5 to 3 and incorrect pairs increased from 11 to 19. It was rejected. Masking observed opposing passive terminals and limiting terminal projection to verified IC bodies reduced that design's incorrect pairs to 13, but its three correct pairs still failed the baseline of five. That candidate was also rejected. Neither trial is an accepted accuracy improvement.

The remaining paths crossed unrecognized symbol ink and propagated external labels into incorrect groups. That intermediate checkpoint required complete terminal anchoring and retained prior connectivity on incompletely anchored sheets. The user rejected that sheet-wide bypass; the local additive revision below supersedes it and is the current production policy. This is a conservative limitation: tracing metadata does not imply that reconstructed connectivity is verified. Phase 4 targeted verification passes 136 pipeline tests plus four benchmark-regression tests. Fresh final gate results are recorded separately below once the complete eight-sample and ten-design run finishes.

Rejected artifacts: evidence/pipeline-sprint-20261022/phase4-revised/ and phase4-passive-probe/. The subsequent phase4-guarded/ run also failed: two workers failed at runtime and CM4Card gained four incorrect pairs. Requiring verified masks for every recognized component and restricting numeric power labels to literal known package pins removed those CM4Card regressions in a fresh focused probe. A separate fresh Wio ESP32S3 probe recovered the correct R1.2--R3.2 connection with no new wrong pairs. This is provisional until the entire phase passes.

The complete fresh gate phase4-awake-final/ passed all eight original/degraded cases and all ten native designs. It held a temporary system power request during the benchmark after Windows Modern Standby interrupted previous CUDA runs. All 147 targeted tests passed. Clear cases remained S1 52/56, S3 59/69, S4 67/72 and S5 39/48: 217/245, or 88.57%, a zero percentage-point change. Native valid physical pins remained 103; correct connected-pin pairs increased from eight to nine, recovering Wio ESP32S3 R1.2--R3.2; incorrect pairs remained fourteen. The first Wio worker crashed after writing its report; the preserved second fresh attempt exited successfully. Every accepted worker exited zero. The phase checkpoint is cba4f08. Protected OCR weights were not changed.

## Local additive revision and Phase 5 diagnostics (not final acceptance)

Following the user's revised execution instructions, production no longer requires complete sheet masking or 100% anchored terminals to apply recovery. Existing observations are retained; each proposed addition is checked against its own source region, observed wire ink, physical package numbers, and cropped-reader agreement. Targeted body-edge OCR runs on locally uncovered or conflicting terminals even when the sheet already has confident references. The old global connectivity replacement is no longer used.

The exact failure diagnostic is evidence/pipeline-sprint-20261022/local-recovery-diagnostic/failures.md and failures.json. It enumerates the twenty missing physical pins and eight wrong/anonymous assignments making up the twenty-eight clear failures, plus all fourteen incorrect native connected-pin pairs. Ground truth is used only by evaluation scripts; production recovery receives no reference answers or benchmark identities.

Fast diagnostic local-probe-06-pixels-clear/ reused saved observations and read actual bounded source crops with the unchanged CUDA readers. It took 92.95 seconds and measured S1 54/56, S3 62/69, S4 69/72 and S5 43/48: 228/245 (93.06%), eleven more correct labelled pins, with none of the original 217 correct labelled pins lost. local-probe-07-scan300/ measured 38/72 to 45/72 with no previously correct labelled pin lost. These are diagnostic scores, not fresh whole-pipeline acceptance.

The ten-design cached/native-crop diagnostic local-native-probe-01/ retained 103 valid physical pins, nine correct pairs and fourteen incorrect pairs, with no regression. Its limitation is explicit: older native caches do not contain the pre-deduplication terminal observations now recorded by production. The final fresh native gate must validate those additional paths. 166 targeted tests pass. The subsequent fresh four-clear-case gate passed in phase5-clear-fresh/; its accepted result follows.

## Phase 5 fresh acceptance and user-requested pause

The fresh four-clear-case gate phase5-clear-fresh/ passed: S1 54/56, S3 62/69, S4 69/72 and S5 42/48, totaling **227/245 (92.65%)**, ten additional correct labelled pins and +4.08 percentage points over 217/245. Every previously correct labelled pin was retained individually. All four workers exited zero and gate errors are empty. This is the verified number; the cached diagnostic's 228/245 was one higher. Phase 5 is commit 6fd75bb.

Work was paused at the user's request on 23 October 2026 at approximately 12:59 IST. Phase 6 confidence/schema/UI work is partially implemented. Its selected 21 backend tests and 14 frontend model tests passed, but the frontend build was intentionally interrupted. Browser QA, the complete final suite, final fresh eighteen-case gate, and native DSN/KiCad export fidelity verification remain pending. No Phase 6 completion or full-corpus accuracy claim is made. Resume instructions are in training/SPRINT_RESUME_CHECKPOINT_20261023.md.

## Phase 6 resumed verification (final benchmark pending)

The user resumed the sprint on 23 October. The complete backend suite passed **359 tests, with six skipped**, including actual KiCad CLI and Capture database round trips. All **14 frontend model tests** passed and the production build passed on **Next.js 16.4.2**. Logs are `phase6-full-tests.log`, `phase6-final-frontend-tests.log` and `phase6-final-build.log` under `evidence/pipeline-sprint-20261022/`.

Explicit observed-pin export modes now preserve literal pin numbers and compare every component, value and pin-to-net assignment after native reopen, including unexpected extras. Three focused export checks passed, including literal IDs B12/00/0/01, zero-pin components, /RESET, and reversible case-colliding Capture net aliases. These modes use generated symbols; this verifies observed-graph fidelity, not source recognition accuracy or functional symbol equivalence. Existing normal library export modes are separately available.

The final fresh eighteen-case gate will protect the accepted Phase 5 clear results with an explicit baseline overlay on the other four Phase 4 records. This combined comparator is not a new fresh eight-case run. The native comparator is the accepted Phase 4 result: 103 valid physical pins, nine correct connected pairs, fourteen incorrect pairs.

Phase 6 live UI verification passed using the real Sample 4 image and actual CUDA recognition through the running API. This exposed and fixed a genuine attachment aggregation bug that discarded image_metadata and review_hotspots. The single-file proposal now retains source frames, scores and regions; additional-source regions are separately retained in attachment metadata and cannot overlay the first file. Sixteen post-fix confidence/attachment/routing tests passed. The live review displayed 271 regions on the actual 9917x7016 source, preserved every evidence score when a region was confirmed, cleared affected scores and marked two regions stale after a manual net edit, restored the graph with Undo, and successfully downloaded a native-readback-verified KiCad archive. PDF page selection switched authenticated 1800x1440 previews from page 1 to page 2 using a small synthetic UI fixture. That fixture recovered two components and zero connections and is excluded from every accuracy result. Browser error logs were empty. Screenshots and structured checks: phase6-review-overlay.jpg, phase6-pdf-page2.jpg, phase6-browser-qa.json.

All application source is frozen during the final fresh gate phase6-final-fresh/. No cached/cropped probe output substitutes for any final worker. Scores are heuristic evidence scores, not calibrated probabilities; a click changes only the review flag. Raw JSON editor tab changes on the large Sample 4 graph sometimes exceeded browser-tool click deadlines; actual state was verified before proceeding. Import other image files separately to inspect their own source overlays; no cross-file geometric alignment is inferred.

<!-- FINAL-SPRINT-20261023 -->
# Schematic2SDN final pipeline sprint — 23 October 2026

Phase 6 is complete. Fresh clear-sample pin-to-net checkpoints: **227/245 (92.65%)**, **+10 correct pins** versus the original 217/245. All previously correct checkpoints were retained.

Completion means implementation and its required gates finished; it does not mean 100% source recognition accuracy.

Phase gate: PASS

| Sample | Before | After | Correct-pin delta | Percentage-point delta |
|---|---:|---:|---:|---:|
| S1 | 52/56 | 54/56 | +2 | +3.57 |
| S3 | 59/69 | 62/69 | +3 | +4.35 |
| S4 | 67/72 | 69/72 | +2 | +2.78 |
| S5 | 39/48 | 42/48 | +3 | +6.25 |
| **Total** | **217/245** | **227/245** | **+10** | **+4.08** |

Native-design metrics are valid physical-pin coverage and connected-pin pairs against the native reference. These are separate from the manually annotated clear-sample pin-to-net label score; native targets may include hidden pins.

| Native design | Valid pins before -> after (delta) | Correct pairs before -> after (delta) | Incorrect pairs before -> after (delta) |
|---|---:|---:|---:|
| Grove Vision AI V2 Library/Grove - Vision AI Module V2.kicad_sch | 29 -> 29 (+0) | 5 -> 5 (+0) | 11 -> 11 (+0) |
| Seeed Studio Wio SX1262 for XIAO ESP32S3/Wio-SX1262 for ESP32S3.kicad_sch | 17 -> 17 (+0) | 0 -> 1 (+1) | 1 -> 1 (+0) |
| Seeed Studio Wio SX1262 for XIAO nRF52840 v1.3/Wio-SX1262 for XIAO nRF52840.kicad_sch | 13 -> 13 (+0) | 0 -> 0 (+0) | 0 -> 0 (+0) |
| Seeed Studio XIAO ESP32S3/ESP32S3.kicad_sch | 4 -> 4 (+0) | 0 -> 0 (+0) | 0 -> 0 (+0) |
| Seeed Studio XIAO nRF52840 v1.3/Seeed Studio XIAO nRF52840 v1.3.kicad_sch | 0 -> 0 (+0) | 0 -> 0 (+0) | 1 -> 1 (+0) |
| XIAO Family/XIAO.kicad_sch | 14 -> 14 (+0) | 0 -> 0 (+0) | 0 -> 0 (+0) |
| 12AU7-Amplifier/source.kicad_sch | 3 -> 3 (+0) | 0 -> 0 (+0) | 0 -> 0 (+0) |
| raccoon/source.kicad_sch | 7 -> 7 (+0) | 0 -> 0 (+0) | 0 -> 0 (+0) |
| pl_test_pcb/source.kicad_sch | 12 -> 12 (+0) | 3 -> 3 (+0) | 0 -> 0 (+0) |
| CM4Card.kicad_sch | 4 -> 4 (+0) | 0 -> 0 (+0) | 1 -> 1 (+0) |
| **Total** | **103 -> 103 (+0)** | **8 -> 9 (+1)** | **14 -> 14 (+0)** |

Gate errors: none

Accuracy numbers above are read from persisted actual evaluation reports. Unit tests and export fidelity are not counted as recognition accuracy.


## Degraded cases

| Case | Before | Final fresh | Delta |
|---|---:|---:|---:|
| S4-scan300 | 38/72 | 44/72 | +6 |
| S4-scan200 | 0/72 | 0/72 | +0 |
| S4-blur300 | 0/72 | 0/72 | +0 |

S2 is included in graph regression and export checks but excluded from labelled-pin percentages because its annotation is incomplete.

## Recovered clear checkpoints

| Sample | Newly correct pin → net |
|---|---|
| S1 | U62.13 → CC3, U62.3 → DD1 |
| S3 | U24.4 → AAA12, U26.9 → AR4, U7.11 → AAA8 |
| S4 | U31.20 → PRAD7, U31.24 → PRAD9 |
| S5 | U37.21 → INDA6, U49.11 → INBU10, U58.3 → INBU12 |

## Verification

- Complete final backend suite: 361 passed, 6 skipped. The live attachment-metadata fix also passed 16 focused confidence/attachment/routing tests.
- Frontend: 14 model tests passed; Next.js 16.4.2 production build passed.
- Live workbench: actual Sample 4 CUDA recognition; 271 source regions on the 9917×7016 image; confirmation preserved all scores; zoom, stale evidence after editing, Undo and a native-verified KiCad download passed.
- Actual authenticated PDF page previews switched between pages 1 and 2. The synthetic UI fixture recovered two components and zero connections and is excluded from accuracy metrics.
- Confidence/source and source-coordinate validation passed on 18 final predictions.
- Final recognition ran serially with fresh OCR and successful worker exits, per-observation regression checks, recorded CUDA providers and an application-source snapshot held throughout the gate.
- The primary original baseline is Phase 4, with the four latest Phase 5 clear records overlaid explicitly. This comparator is assembled from accepted fresh runs and is not itself a new eight-case run. The native gate protects Phase 4’s accepted nine correct pairs.

## Actual native export readback

| Format | Graphs passing | Observed pin assignments matched |
|---|---:|---:|
| kicad | 18/18 | 2208/2208 |
| orcad | 18/18 | 2208/2208 |

Explicit observed-pin modes use generated symbols with literal observed IDs. KiCad CLI XML and actual Capture reopen compare every component reference, value and pin-to-net assignment, including unexpected extras. Capture net-name aliases are reversible and saved in the bundle. Native readback fidelity applies to these observed graphs; it does not prove recognition accuracy, original symbol appearance or faithful substitution in the separate normal library export modes.

## Remaining errors and limits

- S1: U64.4: WZPLJ6 → expected DD6; U64.13: missing → expected CC7.
- S3: U6.14: KAAI → expected AAA1; U6.11: missing → expected AAA4; U8.14: AAA6 → expected AAA9; U8.11: missing → expected AAA12; U27.17: missing → expected AR12; U27.7: RG9 → expected AR3; U28.19: missing → expected AR10.
- S4: U31.27: missing → expected ADDA11; U33.14: missing → expected ADDA9; U34.9: missing → expected ADDA7.
- S5: U36.21: missing → expected INDA14; U36.2: N00549 → expected INDA12; U49.2: ~TT2 → expected INDA8; U49.9: N00619 → expected INBU8; U37.9: missing → expected INBU4; U50.9: missing → expected INBU0.
- 14 incorrect native connected-pin pairs remain. The native corpus includes hidden pins/fields and uses physical-pin coverage and connected pairs, separately from the 245 manually labelled checkpoints.
- Confident observations are retained; uncertain local recovery requires observed anchors, source ink and reader/catalog support. There is no sheet-wide complete-anchoring bypass. Unresolved regions remain for review rather than receiving guessed connections.
- Evidence scores are heuristic, not calibrated probabilities. Confirmation changes only a review flag. Unknown or unlocated pins may retain low evidence scores without invented precise coordinates.
- Base RoI vision helpers were unavailable or timed out in live attempts. No successful RoI-model gain is claimed. No weights were trained and rejected adapters stayed inactive.
- Multiple source files retain separate region metadata; the current compare panel overlays the first attachment. Import other files separately to inspect their own source regions.

## Evidence

- Fresh recognition and exact diffs: `evidence\pipeline-sprint-20261022\phase6-final-fresh`.
- Native export/readback artifacts and verification: `evidence\pipeline-sprint-20261022\phase6-native-exports`.
- Original 28-pin / 14-pair diagnostic: `evidence/pipeline-sprint-20261022/local-recovery-diagnostic/failures.md`.
- Final remaining-error inspection: `evidence/pipeline-sprint-20261022/phase6-final-failures/failures.md`.
- UI checks/screenshots: `phase6-browser-qa.json`, `phase6-review-overlay.jpg`, `phase6-pdf-page2.jpg` under the sprint evidence folder.
- Protected OCR checkpoint SHA256: `c5ad0e9ebe43373f1986ed5d6c39be0b73a29cb4dcb257e45ca7f91f41ce07cf`.
