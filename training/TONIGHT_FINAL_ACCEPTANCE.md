# DeCad tonight acceptance — 23 October 2026, Asia/Kolkata

## Precision continuation from 871ee61 - final accepted result

Application commit: **b0d6c9b**. Recovery branch: `recovery/precision-871ee61`. The prior report below is a historical baseline; this section supersedes its current accuracy/status figures.

**Review-assisted application verified. Automatic schematic recovery remains incomplete.** Only the corroborated two-terminal passive guard was accepted. It requires the explicit R/C/L/D library type and observed terminals 1 and 2 with collinear, opposed outward anchors before quarantining extra pin IDs. Original nodes, prior nets, source anchors, warnings and review regions survive in `rejected_pin_observations`. No replacement pin number or net is inferred. Existing XML imports and manual review graphs use their existing paths.

| Measurement | At 871ee61 | Accepted result |
|---|---:|---:|
| Clear exact assignments | 227/245 (92.65%) | 227/245 (92.65%) |
| Valid native assigned pins | 103 | 103 |
| Correct native connected-pin pairs | 9 | 9 |
| Incorrect native connected-pin pairs | 14 | 13 |
| Native pair precision | 39.13% | 40.91% (+1.78 percentage points) |
| Raw corpus faculty XML | 7/18 complete | 7/18 complete; same 11 blocks |
| KiCad and Capture native readback | 18/18 each | 18/18 each, 2,206/2,206 assignments each |

The removed false pair is Wio **R1.1--R1.4**. Invalid observations R1.4 and R1.55 move out of the electrical graph into explicit review evidence. R1.1 remains anonymously labeled; LORA_RST was not invented. No known correct pin, source label or connected pair was lost. The other **13 false pairs** remain: 11 Grove U2 ground-related pairs, one nRF phantom P0 pair, and CM4 U504.4--U504.9 (a misidentified U6, whose real junction must remain connected). All 18 clear errors remain: 11 missing anchors and 7 incorrect assignments. [Individual source audit](PRECISION_ELECTRICAL_AUDIT_2026-10-23.md).

The broader connector-boundary experiment was **rejected**. It removed a phantom pair but introduced a new spurious P3.2 through regex reference backtracking on another native design. Execution stopped and `digital_vision.py` was restored byte-for-byte to the accepted parser. Its S3 removals and apparent nRF improvement are not shipped or included in accepted gains.

**Evidence boundary:** after rollback, fresh current-code Wio and ESP32 workers passed. An exact guard-only replay over all 18 baseline graphs proves the guard inert on the other 17. Sixteen final cohort outputs therefore reuse accepted recognition, and two are current fresh targets. This is not claimed as a new full 18-case fresh recognition run. Candidate fresh results remain archived separately. The accepted gate verifies that only `local_recovery.py` differs from baseline source, preserves every previously correct native source label/pin/pair, and records unchanged model hashes.

Tests on the final code: **384 backend passed / 6 environment-dependent skipped**, **65 focused passed**, and **18 frontend passed**. Independent ElementTree checks retain all **129 faculty nodes, 41 nets and every meaningful attribute**, including unused pins and used-but-unassigned J2.15. The 11 blocked exports contain 37 components with zero observed pins; source inspection distinguishes visible missed terminals, unprinted numbering, reference aliases and prose/USB false detections. No exporter defect was found. Real TD9 vendor import remains **NOT VERIFIED**.

### Independently checked unseen Sallen-Key demonstration

Source: installed, unchanged KiCad `simulation/sallen_key/sallen_key.kicad_sch`, raster only supplied to recognition. Raw output was fixed before native reference readback: **2/8 components, 0/19 assigned pins, 0/18 correct pairs**, no false pairs. This is an automatic-recognition failure, not an automatic accuracy gain.

The initial manual image transcription guessed R/C pin numbering and failed independent readback (6 correct / 12 wrong pairs). The image omits these IDs. Embedded symbol pin positions and instance rotations established that R1/R2/C1 pin 1 is at the right and C2 pin 1 is below. The original transcription and failed comparison are retained. After explicit native pin-number lookup, manual review has **8/8 components and values, 19/19 pins, 18/18 positive pairs and 153/153 negative pairs**. XML and both native readbacks pass with 19 assignments and zero extras. All 11 named-label assignments match after root-sheet slash normalization; only 8/19 literal full names match because unprinted intermediate nets use different generated names.

Live HTTP upload, recognition proposal, review save/reopen, faculty download and native downloads were exercised. Visual browser interaction was disabled by Work settings, so the visual UI test was not repeated. Existing frontend tests pass; the earlier browser evidence below remains historical. No UI redesign, model training, model download, dependency installation or connection fabrication occurred.

### Launch and reproduce

1. `Set-Location D:\DeCad-main\Jrk_DeCad\Schematic2SDN`; run `& .\start-native.ps1`.
2. Open `http://localhost:3100`, Open local workspace, choose **PrecisionUnseenFilter**, then **Saved review**. Its actual raster source is attached. Existing QmaxTonight and QmaxUnseenRectifier projects remain available.
3. Compare all reviewed source conductors and native pin-number evidence; download Faculty XML or observed-pins KiCad/OrCAD files. The reviewed demo uses manual correction and native pin lookup.
4. Recheck the existing demonstration without repeating OCR: `backend/.venv/Scripts/python.exe tools/eval/precision_demo.py --verify`.
5. Reproduce corpus analysis: `backend/.venv/Scripts/python.exe tools/eval/precision_acceptance.py --baseline evidence/tonight-20261023/final-fresh --wio evidence/precision-20261023/accepted-wio-fresh --esp32 evidence/precision-20261023/accepted-esp32-fresh --out evidence/precision-20261023/reproduced-acceptance` (choose a new output folder).

Evidence: [summary](../evidence/precision-20261023/final-summary.json), [exact changes](../evidence/precision-20261023/accepted-fresh/precision-changes.json), [accepted gate](../evidence/precision-20261023/accepted-fresh/gate.json), [native readbacks](../evidence/precision-20261023/native-exports/report.json), [unseen workflow](../evidence/precision-20261023/unseen-workflow.json), [backend tests](../evidence/precision-20261023/backend-tests-accepted.log). Full raw/candidate workers and source crops remain in `evidence/precision-20261023`; unrelated pre-existing workspace changes remain outside these commits.

## Historical acceptance at 871ee61

**DEMO-READY for the tested review-assisted workflow. Automatic recognition remains incomplete.**

Final automated verification and live restart checks passed on 23 October 2026. The automatic error-reduction objective remains open; the 18 clear misses and 14 native wrong pairs were not solved. Current handoff Git HEAD and the remaining pre-existing dirty state are recorded after the handoff commit in `evidence/tonight-20261023/final-git-state.json`.

## Source and preservation

- Accepted starting commit: `2202e54`.
- Application source freeze: frontend `c6763c1dd8dd0081c9a27ec35aa4cfa50e30a80c`, backend recognition `40ddbf7`. Backend source remains unchanged throughout the fresh eighteen-case gate.
- Resource-monitor commit: `0a078d963e2065a2711ebd3f57c9760c9943f734`.
- 1003 pre-existing working-tree entries were preserved. Initial status and binary tracked diff: `backend/.state/tonight-20261023/initial-status.txt` and `initial.patch`. No reset, unrelated staging, public push, training, large download or dependency installation.
- Owned implementation: `backend/app/{faculty_xml,review_store,ingestion,main,confidence,erc,recognition,digital_vision,pipeline_profile}.py`, `frontend/app/{CircuitReviewPanel,page,review-model,source-net}`, `start-native.ps1`, focused backend/frontend tests, and `tools/eval/tonight_*.py`.
- Protected OCR model expected SHA256: `c5ad0e9ebe43373f1986ed5d6c39be0b73a29cb4dcb257e45ca7f91f41ce07cf`; final gate and a separate final SHA256 check both confirmed it unchanged.

## Implemented workflow

Faculty XML imports through the existing attachment/review workflow. The typed XML tree and records preserve known/unknown attributes, missing versus empty values, literal physical IDs, aliases, unused pins, declaration ordering, and independent power metadata. The canonical Circuit now has a physical-pin inventory independent of resolved nets. Unknown types remain internally unknown; generated XML uses documented conservative Unknown/FALSE/empty mappings. Power is never inferred from a pin name.

Review supports source comparison and page selection, observed net-terminal/trace highlighting, add/edit/delete parts and connections, split/merge, unassigned-pin inspection, local undo, and atomic saved drafts with revision checks and saved-history undo. Manual changes clear recognition scores and invalidate stale source overlays. Confirmation changes review state, not confidence. Reopening Saved review restores graph and source coordinates independently of native symbol substitution.

The active runtime profile now preserves the observed recognition graph whether Capture is installed or absent. Library cleanup cannot drop pins in this profile. Suspected power/ground paths produce review warnings and hotspots; ERC no longer guesses a weakest edge to cut. Explicit two-pin symbol conflicts (such as Device:R pin 4) and unlocated inferred connectors now require source review, with all observations retained. Native exporters remain unchanged. The Windows launcher waits for both FastAPI health and frontend assets before opening the workbench.

## Five-line launch guide (tested)

1. PowerShell: `Set-Location D:\DeCad-main\Jrk_DeCad\Schematic2SDN`
2. Run `& .\start-native.ps1`; both services must become ready.
3. Open `http://localhost:3100`, then **Open local workspace**.
4. Select **QmaxUnseenRectifier → Saved review**, or **Import circuit source** for a new image/PDF/XML.
5. Inspect/correct, confirm review, then download **Faculty / TD9-style XML** or an **observed pins** native format.

Runtime: FastAPI `127.0.0.1:8100`, Next.js 16.4.2 / React 19.3.0 on `localhost:3100`, profile `hybrid_max_accuracy`; production RapidOCR/CRNN with ONNX Runtime CUDA 1.22.0 in the existing GPU worker. Rejected OCR adapters remain inactive. `vision/status` reports actual providers and `recognition_native_cleanup:false`. Normal recognition requires no VLM completion.

## Acceptance matrix

| Gate | Result | Evidence / limits |
|---|---|---|
| Gate 0: image → graph → XML → parse | PASS | Fresh CPU synthetic divider; 6/6 assignments, no extras. `evidence/tonight-20261023/xml-gate.json`. Synthetic smoke, excluded from accuracy claims. |
| Gate 1: exact faculty round-trip | PASS | All 129 nodes / 41 declarations; no missing/extra/changed records or metadata. Includes 114 used, 15 unused, four QD0 members, J2_15 used but unassigned, P5V net level 1 versus pin level 5. |
| Edited net reaches UI download | PASS | QD0 → REVIEWED_QD0 changed exactly U1.18/U2.18/U3.1/U5.1 in actual Downloads XML; 129/41 records retained. |
| Save, close, reopen, undo, concurrency | PASS | Actual reopened UI draft; API tests cover disk reload, saved-history undo, stale revision rejection and duplicate assignment rejection. |
| Negative connectivity / uncertainty | PASS, limited | Existing geometry/junction/bus/scope regression tests plus new no-guessed-short-cut test. This does not identify every incorrect automatic connection. |
| Gate 2: cached failure checks | PASS for preservation | Clear 227/245 retained; native 103 valid pins / 9 correct pairs / 14 wrong pairs retained. No accuracy improvement claimed from cached replay. |
| Gate 3: independent real family | PASS workflow; automatic recognition FAIL | Official installed KiCad rectifier raster. Raw: 2/5 parts, 2/10 valid assigned pins, 0/10 literal exact assignments, 0 correct pairs / 0 false pairs. Source review added missing components and explicitly transcribed conductors. |
| Reviewed unseen XML | PASS | 5 components, 10 physical pins, 4 nets; exact graph readback with no extras. Review was manual, not an automatic model gain. |
| Reviewed unseen native exports | PASS | Actual UI KiCad CLI readback and actual Capture reopen each preserved 10/10 assignments; 5 parts, no missing/extra/wrong pins. |
| Gate 4: final fresh eighteen-case GPU gate | PASS | All 18 cases, actual successful worker exits, CUDA providers confirmed, frozen backend source and model hash; no regressions. |
| Final backend regression suite | PASS | 376 passed, 6 skipped in 467.02 seconds; final frozen source. Twelve XML tests include independent ElementTree attribute checks. |
| Frontend tests / production build | PASS | All 18 tests and final Next.js 16.4.2 production build passed. Final live workbench restart restored the corrected graph and source image. |
| Final eighteen-graph native readback | PASS | Fresh KiCad and Capture verification each matched 2208/2208 assignments across 18 graphs, including extras checks. |
| Raw corpus faculty XML | 7 PASS / 11 BLOCKED | Eleven proposals contain components with no observed physical pins. Export refuses to omit those components or invent pin numbers; source review is required. See xml-corpus/report.json. |
| Actual Qmax/TD9 vendor import | NOT VERIFIED | No actual TD9 application import performed. XML schema similarity is not vendor acceptance. |

## Before / after electrical accuracy

| Dataset | Accepted baseline | Current result |
|---|---:|---:|
| S1 | 54/56 | 54/56, fresh |
| S3 | 62/69 | 62/69, fresh |
| S4 | 69/72 | 69/72, fresh |
| S5 | 42/48 | 42/48, fresh |
| Clear total | 227/245 | 227/245, fresh |
| S4 scan300 | 44/72 | 44/72, fresh |
| S4 scan200 | 0/72 | 0/72, fresh; failure remains |
| S4 blur300 | 0/72 | 0/72, fresh; failure remains |
| Ten native designs | 103 valid pins; 9 correct / 14 wrong connected pairs | 103 valid pins; 9 correct / 14 wrong pairs, fresh; unchanged |
| Independent rectifier, raw | No prior tuning/run | 2/5 components; 2/10 valid assigned pins; 0/10 literal exact assignments; 0 TP / 0 FP / 8 FN connected pairs |
| Independent rectifier, manual review | Raw result above | 5/5 parts, 10/10 physical pins, 8 TP / 0 FP / 0 FN pairs; 8/8 printed-name assignments after harmless root-sheet slash normalization |

Reviewed unseen literal-name score is 3/10 because native scoped labels include a leading slash and the unlabeled intermediate conductor has a different autogenerated name. Its topology and values match the independent native graph; literal XML output preserves the reviewer's chosen names. Terminal numbering conventions absent from the raster are explicitly documented in `image_metadata.manual_review` and each physical pin's metadata. No package numbers were fed to the recognizer.

## Full native-reference coverage (separate from clear checkpoints)

These fresh ten-design metrics use complete original native graphs, which may include hidden pins and nonprinted fields. They show why the 227/245 annotated clear-pin result must not be generalized to arbitrary schematics.

| Metric | TP | FP / extras | FN / missing | Precision | Recall |
|---|---:|---:|---:|---:|---:|
| Component references | 60 | 18 | 420 | 76.92% | 12.50% |
| Physical pin coverage | 103 | 126 | 2354 | 44.98% | 4.19% |
| Connected physical-pin pairs | 9 | 14 | 21016 | 39.13% | 0.0428% |

F1 values and per-case records are in `xml-corpus/report.json`. Raw automatic whole-circuit reconstruction is not established by these results. The reviewed rectifier is a distinct, explicitly manual correction result.

Six skipped backend checks require unavailable native ngspice/Qucs-S/pcbnew environments; exact reasons are in `backend-tests-final.log`. They are not passes. TD9 vendor import remains NOT VERIFIED.

## Remaining defects

- The 18 known clear-sample misses and 14 known incorrect native pairs have **not been solved**. Fresh exact records: `evidence/tonight-20261023/final-failures/failures.md`; record-level no-regression comparisons: `final-fresh/diff.json` and `diff.md`.
- Scan200 and blur are severe automatic failures. Cached diagnostics show nonempty CUDA OCR, finite invertible ingestion transforms, 86 / 59 assigned observations versus clear 292. This rules out empty ingestion as the explanation, but does not prove one universal root cause. No speculative threshold or model changes shipped.
- Automatic recognition on the independent analog rectifier missed V1/D1/C1 and misread R1 pin 5. It required substantial manual correction. This is not general automatic accuracy certification.
- Native observed exports use generated exact-pin symbols. They preserve the reviewed electrical graph, not original symbol appearance or faithful substitution in normal library export mode. Unassigned inventory fidelity is proven for XML; the unchanged native observed exporters' comparison scope is assigned pins.
- The saved review draft and the native KiCad workspace are distinct editing surfaces. XML exports use the explicitly saved review. Direct edits in an external CAD editor are not silently merged into that draft; reopen/update the review before using its XML export.
- Multiple PDFs retain scoped page evidence. Cross-page/global equivalence is deliberately not guessed. Multiple separate attachments still display the first attachment's overlay; import separately for source-local review.
- Evidence scores are heuristics, not calibrated probabilities. Catalog pin functions and power names are not wire evidence. Unknown/unlocated terminals remain unresolved.
- XML requires physical node records. A component with no observed or manually specified pins cannot be represented losslessly by standard faculty records; export reports missing components instead of inventing a pin. Review must resolve or explicitly remove such components.

## Evidence and reproducible commands

All tonight artifacts live in `evidence/tonight-20261023/`:

- `faculty-roundtrip.xml`, `xml-gate.json`, `faculty-ui-edited.xml`, `faculty-ui-net-edit.jpg`.
- `unseen-rectifier.png` / PDF and native reference XML; `unseen-raw-prediction.json` saved **before** independent ground-truth loading.
- `unseen-raw-metrics.json`, `unseen-reviewed-metrics.json`, `unseen-reviewed-graph.json`, `unseen-xml-readback.json`.
- `unseen-original-overlay.jpg`, `unseen-reviewed-net.jpg`, `unseen-reopened-review.jpg`, `unseen-native-capture.jpg`.
- Downloaded native archives and `unseen-native-readback.json`; `unseen-runtime.json` records CUDA providers and 57.29 seconds.
- `degraded-ingestion-diagnostic.json`, cached clear/native diagnostic folders, test/build logs.
- Final gate output: `final-fresh/`; resource report: `final-gpu-resources.json`. The gate took 2397.39 seconds; sampled system RAM peaked at 6.95 GiB and GPU memory at 1542 MiB (2-second samples, system totals include other applications).
- Fresh export comparisons: `native-exports/report.json`; raw XML blocks and independent full-native metrics: `xml-corpus/report.json`; restored live state: `final-live-check.json` and `final-live-review.jpg`.

```powershell
$env:PYTHONPATH='backend'
& backend/.venv/Scripts/python.exe tools/eval/tonight_xml_gate.py
& backend/.venv/Scripts/python.exe -m pytest backend/tests -q --disable-warnings
npm test --prefix frontend
# Run in frontend/: npm run build
& backend/.state/claude-20261018/gpu-venv/Scripts/python.exe tools/eval/sprint_gate.py --out evidence/tonight-20261023/another-final-fresh --original-baseline evidence/pipeline-sprint-20261022/phase6-final-fresh/original --native-baseline evidence/pipeline-sprint-20261022/phase6-final-fresh/native
```

The full GPU command is a final acceptance gate, not an instruction to repeat completed work routinely. It creates a new output folder and must run alone; preserve every worker exit and do not treat provisional JSON as success.

## Three-minute technical demonstration

1. **0:00–0:30:** Launch, open the saved rectifier review and its actual source. State the raw result plainly: only two of five parts were recognized; wiring required review.
2. **0:30–1:15:** Show original amber review regions and saved untouched prediction. In corrected Connections select `rect_out`; inspect D1.1/C1.1/R2.1 and the source conductor. Explain manual terminal numbering and stale evidence invalidation.
3. **1:15–1:45:** Rename a net, Save review, close/reopen; demonstrate Undo on a reversible edit. Show that scores never increase on confirmation.
4. **1:45–2:20:** Download faculty XML; show semantic reparse and all ten reviewed assignments. Separately show the faculty fixture's exact 129/41 proof and J2_15 without an invented net.
5. **2:20–3:00:** Show the KiCad and Capture exact-pin archives, actual native readback reports with no extras, remaining 18/14 recognition defects, and TD9 import NOT VERIFIED. Do not present serialization fidelity as source accuracy.
