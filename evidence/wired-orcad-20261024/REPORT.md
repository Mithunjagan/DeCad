# OrCAD visible wiring and source layout — 2026-10-24

The observed-pin exporter previously produced labeled terminal stubs without routing the
connections between them. The normal exporter could silently revert to that representation.
Both OrCAD options now require visible wiring between every reviewed multi-pin net.

## Verified outcome

- All 18 accepted closure graphs plus the unseen Sallen-Key graph: **19/19 native exports passed**.
- **2,229/2,229** reviewed pin/net assignments preserved, with no missing or extra pins,
  changed component values, or wrong net assignments in reopened Capture readback.
- **332 multi-pin nets** are physically wired. An independent continuity check ignores net
  aliases, rejects disconnected same-label stubs, and checks for unintended wire junctions.
- The **1,262 singleton pins** remain isolated. A missing reviewed connection is not inferred
  merely to add a visible wire.
- **910 measured source pin positions** checked after native reopen; source-position checks
  passed in every case. This check covers measured geometry, not fallback symbols.
- Source coordinates and orientations are retained where measured; resistors, capacitors,
  voltage sources, five-terminal amplifier triangles, split IC bodies, and distributed
  connector terminals have source-aware generated geometry.
- Routing failure now stops export. Net labels remain as names on actual wires and as
  annotations for isolated terminals; they do not replace a missing multi-pin connection.

## Actual application project

`demosample1-wired` was created through the live API from the saved `demosample1` review.
The original review remained byte-for-byte equal at the API level. Recognition was not rerun.
Both the saved review and the native export preserve all 24 components and 300 assigned pins.
Its 52 multi-pin nets are visibly wired; 141 singleton pins have no reviewed partner.
139 source pin positions were verified with zero offset after Capture reopen.

Open `live/demosample1-wired.zip`, or select the project in the running app.
In the review export selector, use **OrCAD Capture · wired schematic** or
**OrCAD · exact pins + wires**, then **Generate & verify OrCAD .DSN**.
Extract the downloaded ZIP and open the included `.opj`/`.DSN` in Capture.

## Visual matching limits

This is **not an exact reproduction of every input drawing**. Wire routes are generated
from reviewed connectivity rather than copied from every source trace. Symbol geometry
missing from or ambiguous in recognition uses an explicitly reported fallback. Sample 1
has 11 components with retained source geometry (including its three distributed connector
references) and 13 fallback components. Its 141 isolated assigned pins are not proof that
the input contains 141 electrically isolated terminals; they reflect the recognized graph.
Compare the preview with the source and correct unresolved recognition before electrical use.

The Sallen-Key example has all eight component geometries and all 19 measured pin positions,
with seven physically wired nets. Its source-layout fallback list is empty. Native/source
colours, text styling, power-wire routes and some symbol details still differ.

## Validation and recovery

- Full backend suite: **428 passed, 6 skipped, 2 existing warnings**, 783.40 seconds.
  The suite was collected before the last three focused source-layout tests were added.
- Final routing/source-layout tests: **12 passed**, including those three additional tests.
- Separate actual native export tests: **15 passed**.
- Frontend: **19 passed**; the running page compiled and returned HTTP 200.
- The final application export also passed source position verification and physical wire
  continuity. `live/report.json` records its download hash and the unchanged original review.
- Accepted recognition graphs were reused; this was an export change, not a fresh OCR gate.
  Recognition modules and checkpoint were not modified.
- Protected checkpoint SHA-256:
  `c5ad0e9ebe43373f1986ed5d6c39be0b73a29cb4dcb257e45ca7f91f41ce07cf`.
- Recovery commit: `73d8ddc`, with `581c236` retained in its ancestry. Pre-edit source copies
  are in `backend/.state/wired-orcad-20261024/`.

Machine-readable native results: `accepted/report.json`.
Actual application receipt and rendered preview: `live/report.json`, `live/preview.png`.
An initial full test attempt lacked the KiCad environment; it was stopped and replaced by
the passing configured run in `backend-tests-configured.log`.
