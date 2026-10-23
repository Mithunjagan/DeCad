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
