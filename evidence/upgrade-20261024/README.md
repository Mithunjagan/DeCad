# Precision upgrade evidence - 24 October 2026

The accepted result is defined by `final-fresh/gate.json`,
`post-verification.json`, `live-automatic/report.json` and `final-summary.json`.
The implementation source fingerprints and protected OCR model digest are
recorded in the fresh gate. Each recognition case starts in an isolated GPU
worker, with loaded execution providers recorded in its report.

`xml-corpus` validates raw Faculty XML. `native-exports` reopens the observed
graphs through KiCad CLI and OrCAD Capture. Export fidelity is distinct from
image interpretation accuracy. `unseen-automatic` saves raster predictions
before reading independent evaluation truth. `live-automatic` additionally
checks API recognition, review persistence and native file downloads in a new
project without manual correction.

The dated report and PDF use actual completed acceptance receipts. Historical
cached probes are labeled `fresh_ocr: false`; they are not final acceptance.
The `pre-slash-fresh` run was rejected because one false nRF connector pair
remained. The first slash-only revision was also rejected when it exposed an
additional invalid connector pin. The final dotted-port guard includes fused
alternate functions and adjacent grid annotations; its focused fresh result is
in `fused-gpio-fresh`.

Intermediate raw predictions, failed experiments and source rollback copies
remain available locally. The commit includes final verification evidence and
focused receipts, without duplicating every intermediate raster/cache file.
Pre-existing unrelated working-directory changes are preserved.
