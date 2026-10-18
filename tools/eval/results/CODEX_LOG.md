# DeCad repair log — 2026-10-18

User request: source layout, sheet-supported net name repair, duplicate body assignment,
missing large IC, then measured documentation. No concurrent recognition jobs.

## Initial state

- Preserved supplied report in `backend/.state/codex-20261018/supplied-baseline.json`.
- Fresh unmodified clear-sheet evaluation started in `results/codex-baseline`.
- Confirmed source coordinates use sheet-width units for both axes; the writer currently
  discards their distances and packs by row. The existing documentation overstates layout.
- Product files will be copied once to `backend/.state/<filename>.before-codex` before editing.
- New measurement helper `tools/eval/codex_verify.py` runs clear and degraded inputs
  sequentially, checks score regressions, and invokes Capture's PCB netlister per design.
- Fresh S1: 23/28 parts, 29/56 labelled pins, 188 verified connections (144 s).
  Fresh S2: 21 parts; TC514100 7, 74F374 5, 74F244 2; 103 verified connections (147 s).
  Both match the supplied baseline. Both PCB netlists exited 0, produced all three PCB
  data files, and contain no ERROR entries (this Capture build writes no numeric summary).
- Frontend baseline: `npm test`, 5 passed. Source/DSN baseline comparison saved as
  `codex-baseline/S1-comparison.png`; source is 9917x7016, aspect 1.41348.
- Layout patch is prepared in `.state/codex-20261018/layout-staged`, compiled, and held
  until the unmodified baseline finishes so Tcl generation cannot change during that run.

## Task 1 — source layout (applied, validation running)

- All five fresh clear baselines reproduce the supplied scores; S5 is 19/25 parts,
  20/48 labelled pins, 210 verified connections (139 s). The unmodified native test
  preflight was stopped after 7 tests while it repeatedly indexed libraries in new
  temporary directories; no full-suite baseline pass is claimed.
- Backed up each modified file once in `backend/.state/*.before-codex`.
- `ingestion.Circuit` now carries source width/height as `sheet_aspect`; digital
  extraction, reviewed API export, automatic API export, and the evaluator preserve it.
- `placement()` retains both source distances on Capture's 10-unit grid, including
  circuits with only one positioned part. The Tcl writer centres the symbol at the
  requested point, searches nearest free offsets, and has a non-overlapping fallback
  below the placed content if that search is exhausted. Unpositioned parts use a
  bottom strip. The page grows with the source orientation/aspect.
- Added a native round-trip test for distances, coincident positions, orientation,
  and the bottom strip. Existing routing and per-pin reopen verification remain active.
- Backend restarted with the existing `start-native.ps1`; frontend code untouched.
- Full 5-image + 3-PDF evaluation is running in `results/codex-layout`.
- First candidate S1 kept 23/28 parts and 29/56 labelled pins, with 188 verified
  connections. Page: 3300x4500 before, 8500x6000 after. Similarity-fit RMS distance
  from the 20 recognized positions: 0.17266 -> 0.01485 of source sheet width;
  median 0.17121 -> 0.00651. Metrics: `codex-layout/layout-metrics.json`.
- The side-by-side check caught SVG content cropping turning that landscape page
  into a portrait preview. Generated source-position previews now retain the whole
  page; imported designs keep their existing crop behavior. Stopped the first
  candidate run during S2 and restarted the complete eight-input measurement after
  this fix. Corrected visual: `codex-layout/S1-comparison-fixed.png`.
- Initial focused native check: 3 passed in 126.95 s; the final rerun also checks
  that the saved SVG frame equals the actual landscape DSN page.
- Final frame test: 3 passed in 155.12 s. The candidate clear-sheet run reproduced
  S1–S4 but S5 fell from 20/48 to 19/48 labelled pins. Stopped the run immediately;
  Task 1 is **not accepted**. Preserved the failed report in
  `.state/codex-20261018/layout-rejected-report.json`.
- Root-cause comparison: U37.23 changes INDA5 -> INDA4 in **recognized.json**, before
  placement/export. Two other non-checkpoint label votes also vary. The recognizer
  uses `max(set(own), key=own.count)` to break tied votes, which depends on process
  hash order. A fresh unchanged token trace chooses INDA5 again. Capturing token and
  label geometry to replace arbitrary tied votes with wire-baseline evidence, then
  repeat the complete gate. No accuracy improvement or successful layout gate is
  claimed yet. This reproducibility repair is required before Task 1 can be measured
  reliably; signal-family snapping remains pending.
- Backend suite is split to respect the one-recognition-job rule: all tests except
  the real pixel-recognition module and the workflow image-recognition case run
  alongside the sheet evaluator; those image cases run sequentially afterward.
- Tie trace: U37.23's wire is at y=5545. INDA5's printed baseline is y=5556
  (11 px away); INDA4's is y=5609 (64 px away). Both OCR boxes touch the wire.
  Added `choose_wire_label`: preserve majority votes, resolve equal votes by text
  orientation, printed-baseline alignment, then confidence and a stable final key.
  It only chooses among names actually read on that wire. New horizontal/vertical
  order-independence tests: **8 passed** including the existing digital unit tests.
- Diagnostic replay of the *same* S5 OCR tokens after the repair: **19/25 parts,
  21/48 labelled pins, 210 verified DSN connections**. This is a token replay, not
  the fresh acceptance measurement. Both the old 20/48 baseline and failed 19/48
  candidate remain recorded. Full fresh eight-input gate must still pass.
- Backend non-recognition batch: **132 passed, 5 skipped, 3 known failures** in
  594.67 s (`test_model_failure_does_not_mutate`, `test_no_fake_bom`, spatial OCR).
  The excluded recognition cases are now running as a separate sequential batch.
- Recognition test batch: **9 passed, 1 skipped, 1 known failure** (`rc-0.5`) in
  15.02 s. Across the split suite, only the four failures listed in the request
  reproduced. New tie-breaking tests pass separately. API smoke is running before
  the fresh stable eight-input gate, keeping recognition jobs sequential.
- API smoke with the final layout/tie code: **HTTP 200, 110 s, 23 parts, 188 verified
  connections, 29/56 labelled pins exact**. Preview and zip both HTTP 200. Preserved
  design and source graph in `codex-layout-stable/api-smoke`; deleted
  `smoke-1792306248` via the app's normal recoverable-delete API and confirmed its
  live project directory is gone.
- Fresh complete gate restarted in `results/codex-layout-stable`, now also saving
  raw OCR tokens for reproducible diagnostics. No token replay is used in that gate.
- Stable **fresh clear** results: S1 23/28, 29/56; S2 21 parts with unchanged part-number
  counts; S3 27/34, 38/69; S4 24/30, 38/72; **S5 19/25, 21/48** (originally 20/48).
  All DSNs verify, with unchanged values and part precision. Runner then stopped on
  Windows CP1252 console-log decoding before PDFs; corrected the harness's log encoding
  and resumed at the three PDFs (`--skip-clear`). Completed measurements are retained.
- Blurred PDF recognition finished, but one native session failed with
  `ORDBDLL-1017: License not found`. A subsequent real DSN reopen succeeded;
  retried **only export of that freshly recognized graph**, preserving its input
  and recording `export_retry: true`. No license settings/services were changed.

### Task 1 accepted

All eight designs reopen and verify. Capture PCB netlister: **8/8 passed, 0 ERROR
entries**, all three PCB data files produced. Final gate: `codex-layout-stable/gate.json`.

| Input | Parts before → after | Labelled pins before → after |
|---|---|---|
| S1 | 23/28 → 23/28 | 29/56 → 29/56 |
| S2 | 21 → 21; TC514100 7, 74F374 5, 74F244 2 | not transcribed |
| S3 | 27/34 → 27/34 | 38/69 → 38/69 |
| S4 | 24/30 → 24/30 | 38/72 → 38/72 |
| S5 | 19/25 → 19/25 | **20/48 → 21/48** |
| S4 scan300 | 24/30 → 24/30 | 26/72 → 26/72 |
| S4 scan200 | 18/30 → 18/30 | 0/72 → 0/72 |
| S4 blur300 | 12/30 → 12/30 | 0/72 → 0/72 |

Values and part precision also do not regress. Source-position RMS error (relative
to recognized centres, not a claim of OCR position accuracy): S1 **17.27% → 1.49%**,
S2 21.94% → 1.04%, S3 11.52% → 0.81%, S4 24.73% → 0.47%, S5 22.08% → 0.41% of sheet
width. Clear output pages are landscape 8500x6000. Measured records:
`codex-layout-stable/layout-metrics.json`; final visual reviewed:
`codex-layout-stable/S1-comparison.png`.

API smoke, focused native/digital tests, frontend tests and all backend test cases
have been run; only the four known failures reproduced. No regressing candidate is
accepted. The first S5 drop was traced and repaired before this final fresh gate.

## Task 2 — sheet-supported name snapping (candidate, validation running)

- Root cause: a clipped `CC[1:16]` header parses as C1..16, while the old vocabulary
  ignores the pin-strip readers' repeated CC11..16 observations. Correct CC16 then
  gets "corrected" back to C16. The first reader's unindexed BB also beats the
  second reader's explicit BB8. Other correct alternatives (AAA5, ADDA13, PRAD5,
  INDA0) are similarly discarded.
- Family evidence now combines sheet tokens with all pin-strip alternatives. A
  stronger complete prefix can repair a clipped header; isolated index outliers
  cannot expand a family (BB97 cannot manufacture BB17..96).
- Numeric readings keep their index when correcting a prefix. Plotter-font index
  glyphs decode only to existing family members. Two nearby labels on one body
  edge may resolve a missing index or choose between supported readings; a new
  family/member cannot be invented by interpolation.
- Captured pixel-strip replay support in `replay_tokens.py` to isolate label logic
  while keeping the fresh full gate separate. S1 replay: **23/28 parts, 34/56 exact
  pins, 188 verified connections**, versus 29/56 before; 182 strip cache hits,
  zero misses. Fixes CC16, CC12, BB10, BB8 and TTTTTD4 -> DD4. Other samples pending.
- Repeated local license failures interrupted diagnostic readback. Added a bounded
  native retry (3 attempts, 1 s pauses) **only** when the error identifies license
  failure at Dbo session creation, before writes. Errors after a write are never
  retried. The targeted safety test passes. No license services/settings changed.
- Focused digital + retry tests: **12 passed**. Task 2 still requires all clear and
  degraded scores, API smoke, backend/frontend tests and PCB netlists before acceptance.
- Additional clear-sheet diagnostic replays completed: S3 **40/69** (was 38),
  S4 **60/72** (was 38), S5 **24/48** (was 21 after Task 1). Parts, values and
  connection counts are unchanged. All four replay DSNs reopen and verify; these
  are cached OCR diagnostics, pending the fresh eight-input acceptance gate.
- User added mandatory unified KiCad/OrCAD library integration and requested
  continuous README updates. README now records accepted Task 1 measurements,
  explicitly distinguishes candidate snapping results, and tracks incremental
  library support without claiming unimplemented binary conversion. Original
  README backed up once at backend/.state/README.md.before-codex.
- User authorized direct coordination with the existing Claude Code process.
  Added a root README entry point and COORDINATION_CODEX.md with exclusive file
  ownership, current jobs, accepted scores, and a request for Claude to own new
  unified-library acceptance tests/research. Claude acknowledgement is pending;
  no claim that it has received or accepted the handoff yet. Recognition slot
  remains reserved for the fresh snapping gate; no second recognition job started.

## Unified component library — incremental implementation

- Added workspace SQLite records, recursive read-only discovery/indexing, manual
  locations, strict source-license permissions, normalized symbol/pin/pad/model
  metadata, source hashes and versions, stale-cache invalidation, shared search,
  bounded scan continuation, and pin-to-pad validation/cache.
- Implemented KiCad symbol inheritance/units/graphics/pins and footprint pads,
  model references and geometry; native Capture package indexing and line/box
  symbol extraction through the installed 26.1 API. Unsupported vectors are
  partial, not silently considered complete. Allegro/3D binaries are catalog-only.
- New browser and API work without Capture. Uploads/downloads require recorded
  permissions; external providers are opt-in via a bounded HTTPS asset protocol.
  Provider wiring and browser still need dedicated acceptance checks.
- Native OLB -> package-only OLB export uses Cadence's database writer and cache
  extraction, then independently reopens and compares physical pins/graphics.
  It works on the original CC0 fixture. KiCad -> OLB and Allegro binary writing
  remain unavailable. No extensions are relabeled.
- Acceptance utility tools/eval/check_component_import.py: original CC0 symbols
  from both ecosystems + two-pad KiCad footprint pass shared search, pin mapping,
  verified cache, actual schematic placement, KiCad CLI SVG export, and native
  OLB export/readback. Source-tree hashes/file set unchanged in final check.
- Initial native export created a lock beside the owned fixture source. Fixed
  by giving Capture's design writer an authorized scratch copy; final check
  confirms no source-side writes. No installation settings were changed.
- Read actual DLL ProductVersion 26.1.0 d001; its fixed-file version misleadingly
  says 6.0.0.0. New adapter gates on product release and lets Cadence check its
  license. Other native releases remain metadata-only until verified.
- Claude's staged Tasks 3/4 handoff received. Live MD5 matches its base exactly;
  no recognition code changes until the current fresh eight-input gate completes.
- Task 2 non-recognition backend batch: **138 passed, 5 skipped, 3 known failures**
  in 938.99 s. Frontend: **5 passed**. Clear fresh scores all confirm replay gains:
  S1 34/56, S3 40/69, S4 60/72, S5 24/48, no part/value regressions. PDFs pending.

### Task 2 accepted

Fresh all-eight gate: regressions **[]**, Capture reopen verification **8/8**,
PCB netlists **8/8**, zero error entries. S1 34/56 (was29), S3 40/69 (was38),
S4 60/72 (was38), S5 24/48 (was21 after Task1,20 originally), scan30037/72(was26).
Scan200 and blur300 remain0/72. Parts/values unchanged across all eight inputs.
Real API smoke:34/56,23parts188pins; temporary live project deleted. Recognition
unit batch:9passed1skipped1known rc-0.5failure. Non-recognition batch138passed5skipped
3knownfailures. Frontend5passed. Source/DSN visual comparison reviewed. Accepted
checkpoint: backend/.state/codex-20261018/accepted-snapping.

### Tasks 3/4 — Claude handoff under diagnostic replay

Confirmed staged patch base MD5 matches live exactly. Applied staged source after
Task2 acceptance. Synthetic Claude checks + existing digital tests:15passed. Now
replaying saved raw OCR and pin strips S1–S5 sequentially; no second recognition
job active. Scores must not regress before a fresh eight-input gate. A combined
Task3/4 candidate follows the user's explicit request to evaluate Claude's staged
patch. Existing originals and accepted Task2 checkpoint are preserved.

- Unified library running-API acceptance passed discovery/index/search, validation,
  verified cache, real schematic placement+preview, internal/KiCad export, and
  unsupported Allegro rejection. Smoke project removed and fixture index removed.
- Headless Edge UI check passed with no page errors. Reviewed screenshot and added
  scoped control spacing/styles; recheck pending after that visual adjustment.

### Component acquisition and desktop UI, 2026-10-18

- Real local and live official KiCad fallback acceptance passed for Timer:NE555P:
  eight electrical pins, eight physical pads, native pcbnew footprint readback,
  project-local footprint table/assets/licenses, cache reuse, actual schematic
  placement and CLI SVG rendering. Browser Find-and-add acceptance passed.
- Component boundary/acquisition unit checks: 16 passed after final cache fixes;
  frontend checks: 5 passed. No image recognition/model loading in these checks.
- Added visible project trash buttons, accessible confirmation, recoverable delete
  receipt and collision-safe restore. Browser acceptance passed cancel/delete/Undo,
  byte-identical schematic restore, collision/path rejection, no page errors.
- Removed redundant KiCanvas activity rail through its supported basic controls.
- New Windows desktop/native host docks only its own eeschema process. Initial
  docking candidate was visibly clipped and rejected; fixed DPI awareness and
  WebView2 window-region overlap. Subsequent checks run off screen. Native command
  IDs are captured from the real menu before reparenting, and Save readback
  confirms KiCad 10 actually writes the schematic. Native zoom and modal visibility
  checks passed. App component acquisition also passed editor close/write/reopen.
- Preserved library reference/value offsets during imported IC placement; genuine
  NE555P acceptance checks field coordinates and native SVG/footprint readback.
- Live mouse move/save check passed twice after safe activation of the owned test
  window. First attempts correctly stopped without keys when a user modifier was
  held or the owned window lacked focus. Final saved component coordinates changed
  (49.53,49.53) -> (52.07,52.07) mm through actual canvas mouse/keyboard interaction.
  Evidence: `.state/codex-20261018/native-move-check.json`.
- Claude's OCR/checkpoint files remain untouched by this UI work. His separate
  replay processes were observed; no Codex image gate started.

Final UI/component checks:
- Native project switching, source synchronization after native edits, browser
  preview/native switching, Delete/Undo and byte-identical recovery all passed.
- Fixed stale project locks exposed by the first switch test: only locks created
  by the owned editor are removed after exit, with file identity/content checks.
- Browser acquisition added U1 and U2 successfully, advanced the reference and
  selected separate grid positions. A final native acquire/reopen also passed,
  placing U2 at (83.82,50.8) mm. Native footprint and symbol-field readback passed.
- Removed BOM footprint guesses; `test_no_fake_bom` now passes. Final focused
  backend checks: 17 component/BOM + 4 project recovery passed. Frontend: 5 passed.
  These are focused checks, not a new full OCR acceptance gate.
- All owned native smoke projects were moved to recoverable trash. Verification
  desktop/CDP listener closed. Existing user projects were not deleted.

2026-10-18, appearance/readability and legacy format warning:
- Converted active Circuit-4beec24e through real native KiCad File > Save; format
  20231120 -> 20260306. Canonical refs/values/footprints/library IDs and all net
  endpoints compare equal (3 components, 3 nets). Original schematic/project and
  before/after hashes/graph: .state/codex-20261018/format-upgrades/.
- Desktop now opts into Windows system appearance before creating HWNDs, sets
  DeCad.Workbench taskbar identity and existing multi-resolution decad.ico.
  Verified small/large native icon handles and dark native title/menu rendering.
- Browser System Auto follows matchMedia changes; native uses Windows app mode
  from the desktop bridge because Edge media emulation can report a different
  preference. Native appearance notification handles later Windows changes.
- Increased small workbench labels to 11–14px Segoe UI, preserved native per-monitor
  DPI awareness, removed text transform effects from new animations. Actual native
  WebView reports 1.25 device scale and 14px composer font. Native schematic canvas
  colors remain KiCad preferences, independently of app chrome.
- Circuit trace/chip loading animation is tied to real pending upload/design/
  recognition/review/export requests; elapsed time, no invented percent/stages.
  Error/completion unmounts it; reduced-motion disables movement.
- check_appearance.cjs PASSED light/dark changes, explicit override persistence,
  real pending/error UI with locally held response (no inference), responsive
  widths 360,390,900,1024,1280,1440,1920 and 125% screenshots. npm test: 5 PASSED.
- check_native_appearance.cjs PASSED real Windows dark preference, synthetic host
  appearance event without changing Windows settings, real Save, native DPI/font.
  Initial checks exposed timing/media preference differences; fixed the Windows
  bridge, then waited for actual editor readiness. One off-screen PrintWindow
  capture was black after a media transition; do not use it as visual evidence.
  Earlier native dark title/menu/DC icon capture was inspected successfully.
- Owned verification shell closed gracefully and its project moved to recoverable
  trash. Production desktop reopened via the existing authenticated API so changes
  take effect. A status-file read during shutdown raced Windows atomic replacement;
  re-read confirmed closed=true before launching. No force termination.
- Recognition files/models untouched; no full OCR gate run alongside Claude.

Production appearance verification complete: existing Circuit-4beec24e reopened
and maximized. Native small/large DeCad icon handles are present; window DPI=120
(125%). No visible older-format warning. Actual production screenshot inspected:
.state/codex-20261018/appearance/production.png. Production has no CDP listener.
Both appearance browser and 5 frontend tests passed after the final changes.
Production screenshot now inspected successfully: real docked editor, dark native
title/menu, DeCad icon, System Auto and larger text. production-check.json confirms
DPI 120 and older_format_warning_visible=false. One browser smoke project needed
an explicit cleanup retry after browser closure; it is now in recoverable trash.
The browser helper now drains pending requests and verifies cleanup instead of
ignoring an HTTP conflict. No user project was deleted.

2026-10-18 user-authorized force delete:
- Circuit-4beec24e retained a pre-existing local-host KiCad project lock from
  11:11. Its editor was closed, but normal deletion blocked every `.lck`.
- Added explicit `DELETE ?force=true` and error-dialog "Force move to trash".
  Validates lock hostname/type and running KiCad processes; unknown/unverifiable
  editors block. Fresh owned other-project editors are exempt only after actual
  HWND PID/title checks. No editor is killed, no lock asset removed separately.
- Lifecycle tests: 10 passed, including complete byte preservation/restore,
  live-editor block, unrelated owned-editor exemption, foreign/unreadable lock
  rejection, inspection failure, auth and recovery collision/path protection.
- Live native accessibility interaction invoked the exact project's Delete,
  normal Move to trash (409), then Force move to trash (200). Original project
  now at `.trash/Circuit-4beec24e-1792318664703807100`, Undo visible. User's current
  `working` editor PID 86576 and HWND 7079698 remained open unchanged. Screenshot:
  .state/codex-20261018/force-delete-after.png. Deletion was explicitly authorized.
- Backend restarted once to load the route. No new OCR/model job/check started;
  Claude's source/checkpoints remain untouched. README documents force recovery.
- Fixed native Undo notification airspace: the toast now appears over the web
  assistant sidebar, outside KiCad's HWND cutout, rather than underneath the editor.

2026-10-18 review circuit and workbench UX:
- Replaced the single long components/nets form with scoped CircuitReviewPanel
  and CSS module, fixed header/footer, searchable component rows and a searchable
  net navigator editing one net at a time. Source image/PDF comparison and image
  zoom, draft Undo edit, separate structural issues/recognition notes, target
  selection and guarded JSON editing. Checkboxes use explicit natural width;
  fields cannot stretch the confirmation label off screen.
- All edits preserve original source positions and other payload metadata.
  Ref renaming preserves net endpoints. Duplicated pin membership and unapplied
  JSON edits block import; any edit resets review confirmation.
- New netlist view owns its scroller/opaque fixed header, pin tags, search and
  explicit single/multiple-pin filters. Hidden schematic toolbar outside its tab,
  accurate view labels and visible ERC finding counts. Footer truncates long
  status messages; original content stays available in the title/details.
- Chat user attachments now have structured metadata instead of appended text.
  Retry retains filenames. Copied legacy labels resolve only exact files in the
  current project; initial browser test found Windows backslash paths, now
  normalized. Unknown filenames never silently become attachments.
- UI-only browser acceptance: 24 components/235 nets, 125% rendering, widths
  320/390/768/1024/1440/1920, source/zoom, net search, renamed refs/pins, duplicate
  pin gate, malformed/dirty JSON guard, readable checkbox/footer/target, target
  switching, captured import payload, copied attachment and error Retry, netlist
  filters/sticky header. PASSED, no browser page errors. Source/analysis/import
  fixture routes were held locally; no OCR/model or real schematic import.
- Frontend unit tests: 8 passed. New shape validation returns useful errors for
  malformed JSON instead of throwing on null objects/numeric net names.
- Inspected dark source comparison, light review, mobile 320px and netlist images
  under .state/codex-20261018/review-ui/. Fixed mobile target selector squeezing
  discovered in the first visual check. Test projects cleaned into recoverable
  trash; user's sample project and recognition source were not edited.
- Updated README/root README and coordination. No backend restart in this task;
  Claude's OCR source/checkpoints and recognition queue remain untouched.

2026-10-18 launcher troubleshooting:
- User's bare powershell command resolves to a zero-byte file at
  C:\Windows\System32\powershell, causing the Windows app-selection dialog.
  powershell.exe resolves to the real Windows PowerShell executable. System file
  and file associations left unchanged. Existing DeCad.vbs uses powershell.exe.
- Services on 3100/8100 healthy. Opened sample through the authenticated native
  desktop endpoint. README launch command corrected to explicit powershell.exe.
  No OCR/training or unrelated process interference; launcher files unchanged.

2026-10-18 Windows-held OrCAD folder / force deletion:
- Actual sample had no KiCad lock or open editor, but parent rename returned
  WinError5. DELETE-access probes identified sample/orcad with WinError32 sharing
  violation. A Cadence file watcher was running; exact handle owner was not
  established and no watcher/unrelated editor was terminated or modified.
- Added project_trash.py: normal rename first; explicit force fallback creates a
  full SHA256-verified snapshot, rechecks original for concurrent changes, then
  writes a private retained-original trash marker. Marker is written last.
  Project list/pdir/embedded activation reject removed projects; SSE notifies
  other open windows. Undo removes the marker and preserves any later writes.
  Rejects junctions and checks snapshot/rollback boundaries and directory identity.
  Original remains on disk; there is no automatic deferred cleanup or space claim.
- Browser DELETE now asks matching owned native desktop to Save/close using its
  mailbox. Existing stale-lock/process-ownership guards remain; no force kills.
- First real locked-folder test exposed read-only Git-object rollback cleanup;
  fixed writable retry only inside the identity-checked partial recovery copy.
  Failed/changed copy tests leave the original visible and no partial trash.
  One replay harness failed before logs were captured; captured subprocess output
  and compared Undo against the schematic after real native format-upgrade Save.
  One pytest invocation from app root failed collection (app import); corrected
  backend cwd, then 14 tests passed in 8.90s. No dependency installation.
- Frontend 8 unit tests passed. Final real Windows folder-handle + off-screen
  native KiCad + separate headless browser acceptance PASSED with zero page
  errors: normal conflict, Save/close, force removal, source 404, other-window
  pane removal, Undo byte equality and repeated force. Evidence:
  backend/.state/codex-20261018/folder-trash/result.json and browser screenshot.
  Own smoke host closed and own fixture physically archived after handle release.
- User explicitly authorized sample deletion. Live force returned 200 with
  receipt sample-1792323443014372800, retained_original=true. All 72 asset entries
  match the verified snapshot and original (excluding the private marker).
  Recovery copy: workspaces/local/.trash/sample-1792323443014372800. Removed
  sample is absent from /projects. Original remains at local/sample while locked.
- Backend reloaded once to apply fix; README/root README and coordination updated.
  No OCR/model jobs or edits to Claude's files/checkpoints.

2026-10-18 live GPU OCR integration:
- User's app process used backend/.venv: Python 3.11, CPU-only ORT 1.31.0,
  Azure/CPU providers, no Torch. Claude's existing separate gpu-venv uses Python
  3.12, ORT GPU 1.22.0 and existing Torch CUDA DLLs. RTX 3050 Laptop 4GB initially
  idle at 9MiB. No new packages were installed and gpu-venv was not modified.
- New ocr_runtime.py/ocr_worker.py dispatch auto/digital recognition to configured
  local Python in a hidden process with a JSON file result. The worker verifies
  actual sessions for detector/classifier/reader/optional schematic reader;
  explicit CUDA rejects CPU downgrade/errors/timeouts. CPU mode remains available.
  Models/algorithms are unchanged; GPU/RAM resources release when each job exits.
- Existing backend .env now points to gpu-venv with S2SDN_OCR_DEVICE=cuda. First
  backend reload happened after the user's CPU request returned 200 and was idle.
  A later reload attempt was blocked by automatic review. Kept live PID106092;
  implemented/tested rolling-worker compatibility to recover only the source
  user's workspace library context. No additional process was terminated.
  New backend protocol explicitly passes the ContextVar library store; the live
  earlier protocol also preserves it via the strictly scoped source path.
- /vision/status and assistant report configuration vs verified sessions,
  preprocessing/OCR/wiring stages and CPU usage honestly. Status polling while
  recognition runs, stage-triggered scrolling keeps the device line visible.
  Removed unsupported 'clear/scanned/blurry ready' claim. No fake progress/load.
- Real OCR probe profiled 851 CUDA /12 CPU kernel events; crop text identical on
  CPU/GPU: U43, IDT7210L, R14 1K00, SPWE6. Four model sessions list CUDA. This
  establishes runtime use, not a new schematic accuracy result.
- First browser harness sent a copied attachment label before project files
  finished loading; app correctly rejected it. Corrected the harness to use the
  real file-input upload flow and fixed unhandled test response rejection.
  The generated failed smoke project was explicitly cleaned to recoverable trash.
- Live app S1 upload -> assistant -> CUDA worker -> review -> native verified DSN
  PASSED twice with no page errors. First 49.8068s, final 51.8167s; GPU telemetry
  peak 52%, ~1.5GiB VRAM. Save/reopen verification: 24 parts, 277 pins. Fresh CPU
  reference 98.797s. Scored reopened DSNs: both24/28 parts,24 correct values,
  zero spurious parts,51/56 exact labelled pins,53 present. Not an eight-input gate.
  Final repeat also confirms workspace_libraries=true. Test projects removed;
  user's new project and open external editors were untouched.
- Focused legacy OCR test exposed existing fake defaults 10k/100nF/IC; removed
  them in vision_local.py. Missing values now require readable pairs; added R/C/U
  tests. Digital_vision.py, orcad_capture.py and model.onnx SHA256 unchanged.
- 20 focused backend tests passed (runtime, recognition selection, text review),
  10 frontend tests passed. Earlier 14 project recovery tests still passed in the
  initial integration batch. One test command used an incorrect backend/backend
  diagnostic path; corrected cwd without changing app behavior. No full suite or
  recognition/training gate was claimed. README/root README and handoff updated;
  GPU/check slot released for Claude. Evidence: .state/codex-20261018/gpu-runtime/,
  gpu-probe.log, gpu-app-check*.log, gpu-cpu-comparison.log.
