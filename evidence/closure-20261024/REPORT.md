# Final closure - 24 October 2026

Baseline recovery point: `581c236`. Production OCR weights are unchanged.

| Measurement | 581c236 baseline | Closure |
| --- | --- | --- |
| Clear pin-to-net score | 228/245 | 228/245 |
| 300-DPI scan | 44/72 | 44/72 |
| Previously valid native pins retained | 131 | 131 |
| Native correct / wrong pairs | 10 / 0 | 10 / 0 |
| Unseen components / automatic pins | 8/8; 18/19 | 8/8; 19/19 |
| Raw Faculty XML exports | 11/18 | 18/18 |
| Backend / frontend passing tests | 412 / 18 | 421 / 19 |

The nineteenth op-amp terminal is recovered automatically from five visible boundary leads and four observed numbers that uniquely identify a standard inventory. Ambiguous inventories abstain. No manual edit or reference graph enters recognition.

Raw XML passing means schema/graph fidelity, including explicitly provisional review terminals. Provisional terminals stay on separate singleton nets with source `provisional_stub`, conservative confidence and amber review regions. Unread identifiers remain `STUB` identifiers rather than claims about physical package numbers. Real bodies without usable stubs remain unresolved. Caption-only zero-pin records retain their full contents in quarantine metadata.

There are 37 provisional terminals, including 0 explicit STUB identifiers. Native assigned physical-ID coverage totals 158, including provisional numeric identifiers that match the independent native inventory; all 131 previously correct IDs remain. The source still requires review before electrical use.

## Per-case provisional inventory

| Case | Provisional terminals | Explicit STUB identifiers |
| --- | --- | --- |
| S4-scan200 | 2 | 0 |
| S4-scan300 | 6 | 0 |
| S5 | 2 | 0 |
| native-3b2a49a524e2d50dcf26 | 2 | 0 |
| native-c4d7791b4ebdf13c3944 | 9 | 0 |
| native-c4d88e79bc63688e0e7c | 4 | 0 |
| native-c6bcc506a3200b19e089 | 12 | 0 |

## Caption-only records retained for review

| Case | Ref | Original value |
| --- | --- | --- |
| native-c4d88e79bc63688e0e7c | U4 | UNKNOWN |

Unseen literal numbered topology: 6 correct, 12 wrong, 12 missing. Symmetric R/C/L equivalence: 18 correct, 0 wrong, 0 missing. Canonical/export pin IDs are not renumbered by evaluation.

Validation: all 18 cases received cached-raster incremental checks; 6 affected cases additionally received fresh isolated OCR. The unseen filter and live API import were fresh. This was not a new full eighteen-case OCR run. Fresh cases: S5, S4-scan300, native-3b2a49a524e2d50dcf26, native-c4d88e79bc63688e0e7c, native-c4d7791b4ebdf13c3944, native-c6bcc506a3200b19e089.

Backend: 421 passed, 6 skipped, 2 warnings in 445.34s (0:07:25). Frontend: 19 passed. KiCad and OrCAD reopen: 18/18 each; 2210/2210 observed assignments preserved per format. Live project: `FinalClosure20261024`, including draft persistence and both native downloads.

Provisional API validation also passed in `ClosureProvisional20261024`: typed source/confidence survived persistence, and Faculty XML plus both native formats reopened successfully.

The 17 previously documented clear errors and limited native graph recall remain. XML exportability does not certify unresolved terminal numbering, symbol ownership or real electrical connectivity. Historical acceptance sections and unrelated local changes are preserved.

Receipts are under `evidence/closure-20261024`: `verification.json`, `accepted/gate.json`, `xml-corpus/report.json`, `native-exports/report.json`, `unseen-final/report.json`, and `live-automatic/report.json`.
