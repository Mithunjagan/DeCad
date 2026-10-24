# Precision and unseen-circuit upgrade - 24 October 2026

Verified against baseline `9985afa`. The serialized eighteen-case gate uses fresh raster recognition. No previously correct clear assignment, valid native pin or correct native pair was lost. Protected OCR model SHA-256: `c5ad0e9ebe43373f1986ed5d6c39be0b73a29cb4dcb257e45ca7f91f41ce07cf`.

| Measurement | Before | After |
|---|---:|---:|
| Clear exact pin-to-net assignments | 227/245 | 228/245 (93.06%) |
| Degraded 300-DPI scan | 44/72 | 44/72 |
| Native valid physical pins | 103 | 131 |
| Native correct connected pairs | 9 | 10 |
| Native wrong connected pairs | 13 | 0 |
| Raw Faculty XML exports | 7/18 | 11/18 |
| Zero-pin components blocking raw XML | 37 | 18 |
| Automatic unseen components | 2/8 | 8/8 |
| Automatic unseen physical pins | 0/19 | 18/19 |
| Native observed-graph exports | 18/18 | 18/18 |
| Matched observed assignments per CAD format | 2206/2206 | 2173/2173 |

Backend: 412 passed, 6 skipped, 2 warnings in 483.93s (0:08:03). Frontend: 18/18 passed. Faculty fixture: 129/129 nodes across 41 nets, with semantic and graph fidelity verified. KiCad and OrCAD exports independently reopen and preserve the current observed graph; this is serialization fidelity, not a claim that every raster connection is correct.

## Clear and degraded samples

| Sample | Before | After | Change |
| --- | --- | --- | --- |
| S1 | 54/56 | 54/56 | +0 |
| S2 | 0/0 | 0/0 | +0 |
| S3 | 62/69 | 63/69 | +1 |
| S4 | 69/72 | 69/72 | +0 |
| S5 | 42/48 | 42/48 | +0 |
| S4-scan300 | 44/72 | 44/72 | +0 |
| S4-scan200 | 0/72 | 0/72 | +0 |
| S4-blur300 | 0/72 | 0/72 | +0 |

## Ten native sources

| Native source | Valid pins | Correct pairs | Wrong pairs |
| --- | --- | --- | --- |
| Grove Vision AI V2 / 3b2a49a524e2d50dcf26 | 29 -> 36 | 5 -> 5 | 11 -> 0 |
| a39a7a1fc84f921b27fd | 17 -> 17 | 1 -> 1 | 0 -> 0 |
| fedf29b44113e135f31f | 13 -> 13 | 0 -> 0 | 0 -> 0 |
| ESP32 / c4d88e79bc63688e0e7c | 4 -> 6 | 0 -> 0 | 0 -> 0 |
| XIAO nRF52840 / 37735b083f0b9f56549f | 0 -> 0 | 0 -> 0 | 1 -> 0 |
| 0a236a74292d04d831fa | 14 -> 14 | 0 -> 0 | 0 -> 0 |
| e9b7597c67252bf7707d | 3 -> 11 | 0 -> 0 | 0 -> 0 |
| 901de51001a98cc2361a | 7 -> 9 | 0 -> 0 | 0 -> 0 |
| c6bcc506a3200b19e089 | 12 -> 12 | 3 -> 3 | 0 -> 0 |
| CM4Card / c4d7791b4ebdf13c3944 | 4 -> 13 | 0 -> 1 | 1 -> 0 |

## Implemented changes and evidence boundaries

- Recognized two-terminal passives receive anchors only when an actual body and opposing leads are visible. Unprinted IDs use left/top=1 and right/bottom=2; known observed orientation is retained. Each synthesized terminal is tagged `implicit_passive_terminal` and highlighted for review.
- A separate DC connectivity view vetoes capacitor plate gaps while retaining the existing OCR terminal coordinate system. Capacitor bodies are erased again after gap healing. A printed value fused with a net name and five-sided port labels are resolved only on the affected DC conductor.
- Exact MCU port tokens such as P0.00 and P0.31 cannot spawn a P0 connector. Existing connector syntax remains unchanged. An external literal IC caption owns its verified outline; internal phantom references with no independent caption are suppressed.
- Zero-pin aliases require absent independent body verification and corroborating source evidence. Quarantined components and their source regions remain in image metadata and review hotspots. Legitimate unresolved components remain active and can still block raw XML export.
- A missing IC terminal can be recovered from a printed package pin, aligned external indexed label and continuous outside lead. Existing assignments are retained. Two other clear-recovery experiments produced no gain and were reverted.

The native stress corpus includes hidden pin and field information. Coverage remains incomplete, including the nRF source; removing phantom connected pairs does not mean that circuit was fully recovered.

## Unseen Sallen-Key result

Raster-only recognition recovers 8/8 components and 18/19 physical pins. Literal numbered-pair score: 5 correct, 12 wrong, 13 missing. Allowing only R/C/L terminal swaps: 17 correct, 0 wrong, 1 missing. The native reference was read only after the raw raster prediction was saved. Canonical/export IDs are never changed by equivalence scoring. U1's unread power terminal still requires review.

## Remaining raw XML blockers

- S5: R19
- S4-scan300: R1, R11, R14
- S4-scan200: R11
- native-3b2a49a524e2d50dcf26: R32
- native-c4d88e79bc63688e0e7c: R15, R2, U4
- native-c6bcc506a3200b19e089: R1, R2, R4, R5, R7, R8
- native-c4d7791b4ebdf13c3944: R6, R9, U4

## Remaining clear-source assignments

| Physical pin | Observed label | Independent expected label |
| --- | --- | --- |
| S1.U64.4 | WZPLJ6 | DD6 |
| S1.U64.13 | unread | CC7 |
| S3.U6.14 | KAAI | AAA1 |
| S3.U8.14 | AAA6 | AAA9 |
| S3.U8.11 | unread | AAA12 |
| S3.U27.17 | unread | AR12 |
| S3.U27.7 | RG9 | AR3 |
| S3.U28.19 | unread | AR10 |
| S4.U31.27 | unread | ADDA11 |
| S4.U33.14 | unread | ADDA9 |
| S4.U34.9 | unread | ADDA7 |
| S5.U36.21 | unread | INDA14 |
| S5.U36.2 | N00549 | INDA12 |
| S5.U49.2 | ~TT2 | INDA8 |
| S5.U49.9 | N00619 | INBU8 |
| S5.U37.9 | unread | INBU4 |
| S5.U50.9 | unread | INBU0 |

Live API verification: new project `PrecisionAuto20261024` recovered 8 components and 18 physical terminals from the raster. Saving and reopening the draft, Faculty XML download, KiCad download/readback and Capture DSN download/reopen all passed without manual correction or a reference graph supplied to recognition.

Receipts: `evidence/upgrade-20261024/final-fresh/gate.json`, `xml-corpus/report.json`, `native-exports/report.json`, `unseen-automatic/report.json`, `live-automatic/report.json`, `faculty-roundtrip.json`. Raw predictions, failed experiments and rollback checkpoints are retained separately.
