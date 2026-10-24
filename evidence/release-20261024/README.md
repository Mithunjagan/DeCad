# Evidence used by the public README

These files preserve measured results from 24 October 2026. They are distinct
from the code checks executed while preparing the repository update.

| File | Original local record |
|---|---|
| `recognition-report.json` | `evidence/upgrade-20261024/final-fresh/original/report.json` |
| `recognition-gate.json` | `evidence/upgrade-20261024/final-fresh/gate.json` |
| `closure-summary.json` | `evidence/closure-20261024/final-summary.json` |
| `native-export-summary.json` | Compact extraction of `evidence/source-faithful-20261024/regression-corpus/report.json`; full source digest included. |
| `visual-audit.json` | `evidence/source-faithful-20261024/deliverables/report.json` |
| `footprint-repair.json` | `evidence/footprint-fix-20261024/oldsamp-fixed/footprint-repair-verification.json` |
| `validation.json` | Current code checks, focused native export reruns, setup checks, and their limits. |

The recognition report is fresh OCR before CAD library substitution. The native
regression checks previously recognized graphs. The closure mixes six fresh
affected cases with cached cases. The visual audit retains failed source-fidelity
outcomes, and the footprint receipt retains required package reviews. None of
these records is a new whole-corpus inference run of the later release source.

See [measurement definitions](../../docs/RESULTS.md) and run
`python tools/update_readme_stats.py --check` to check the public figures.
