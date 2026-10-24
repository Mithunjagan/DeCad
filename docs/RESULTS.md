# Recorded measurements

[← Project overview](../README.md) · [Setup guide](SETUP.md) · [Machine-readable metrics](data/metrics.json)

The README's recognition table comes from the **24 October 2026** fresh,
process-isolated gate in [`recognition-report.json`](../evidence/release-20261024/recognition-report.json)
and [`recognition-gate.json`](../evidence/release-20261024/recognition-gate.json).
The original receipt records the source and model hashes and the ONNX execution
providers used by each worker. These are recorded results, not a claim that later
source edits received the same full OCR rerun.

## What the numbers mean

| Measurement | Denominator and scope |
|---|---|
| Exact labelled pin → net | A selected physical pin has the expected labelled net. The four clear sheets contribute 56 + 69 + 72 + 48 = 245 checkpoints. |
| Matched components | Recognized components matched against reference entries. Reported separately from extra detections and exact values. |
| Correct values | Exact accepted values among matched components; neither extras nor missed components disappear into an aggregate percentage. |
| Timing | Elapsed worker time for that specific recorded case and environment. It is not the old live-app CPU/GPU speed comparison. |
| Native observed-graph export | A native file preserves the graph supplied to the exporter. It does not establish that the graph correctly interprets a source image. |
| Source appearance | Symbol geometry, routes, junctions, and positions agree with source evidence. This audit can fail while assigned-pin readback passes. |

The clear-sheet sum is **54 + 63 + 69 + 42 = 228**, or **93.06%** of the 245
labelled checkpoints. The README rounds it to **93.1%**. This is not 93.1% of all
possible pins or a 93.1% complete-circuit success rate. Sample 2 lacks a labelled-pin
denominator in this report and is not part of that aggregate. The 300 dpi, 200 dpi,
and blurred cases are reported individually; the latter two remain 0/72 exact.

The prior October 18 README described a different saved-design evaluation stage.
The new table explicitly labels the October 24 recognition-before-library scope;
the two headline figures should not be treated as a controlled speed or accuracy
comparison of identical stages.

## Export, review, and appearance receipts

- [`native-export-summary.json`](../evidence/release-20261024/native-export-summary.json)
  records **19/19** observed-graph Capture exports and **2,229** checked pin
  memberships. It is a compact extraction of the full local regression audit;
  its original path and SHA-256 are retained. Detailed per-wire geometry is not
  duplicated in this compact summary.
- [`closure-summary.json`](../evidence/release-20261024/closure-summary.json)
  records **18** XML exports and **37** explicitly provisional terminals.
  Six affected recognition cases used fresh OCR; the remaining closure inputs
  reused cached raster postprocessing. This was not a fresh eighteen-case OCR run.
- [`visual-audit.json`](../evidence/release-20261024/visual-audit.json) records
  **0/3** source-faithful drawings despite electrical passes. The symbol, pin
  position, route, and junction discrepancies remain visible in each case.
- [`footprint-repair.json`](../evidence/release-20261024/footprint-repair.json)
  records a separate saved design with **24/24** footprint properties assigned
  and a successful native PCB netlist. **Five** proposed packages still need
  physical package review; the record's overall PCB readiness remains false.

The held-out amplifier in the closure record recovered 8/8 components and 19/19
physical pin IDs. Literal pairwise topology scored 6 correct and 12 wrong pairs;
allowing symmetric R/C/L terminal equivalence produced 18 correct and zero wrong
pairs. Full literal graph equality remained false. Keep that distinction when
reporting the example; component counts alone do not prove circuit correctness.

## Regenerate and inspect

```powershell
python tools\update_readme_stats.py
python tools\update_readme_stats.py --check
```

The generator verifies the clear-sheet sums, denominators, fresh-OCR flags, and
successful export cases, then updates the marked README section, JSON metrics,
and `docs/media/accuracy-clear-20261024.svg`. The chart presents the four clear sheets;
degraded-input measurements remain in the README table and source data.
`--check` exits nonzero if any output is stale.
The metrics file also records SHA-256 hashes of its published source receipts.
New measurements should be published as new dated evidence rather than silently
rewriting an older run. Keep raw measurements and evaluation truth separate from
recognition input, and serialize GPU gates on small-memory machines.
