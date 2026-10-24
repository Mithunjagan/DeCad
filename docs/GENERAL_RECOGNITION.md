# General schematic recognition

The input is the source of circuit content. Recognition does not select a canned circuit family
or look up the expected contents of a known sample. The API's current pinned production profile
is `hybrid_max_accuracy`: it owns `IMAGE_MODE`, the strict CUDA device, and the accepted checkpoint.
An `auto` request under this profile is promoted to the pinned hybrid pipeline. Setting
`IMAGE_MODE=vision` in an environment file does not override the production profile.

The profile's bounded regional vision endpoints are defined in `backend/pipeline_profiles.json`.
The full-page general-reader settings below apply when the explicit `vision` mode is requested;
the generic automatic-reader fallback also exists for standalone use outside the enabled profile.
Explicit `digital`, `circuit`, `ocr`, and `vision` selections remain available. See
[the setup guide](SETUP.md) before configuring runtimes and [recorded results](RESULTS.md) for scope.

The local geometry recognizer's supported symbols remain clean R/C/V diagrams; it is not a
universal symbol detector. General analog, digital and mixed-device recognition depends on the
configured vision model's capabilities. A prompt or valid JSON is not proof of image accuracy.

## Configuring a general reader

For an explicit `vision` request, set `VISION_MODEL` and, if separate from the chat service,
`VISION_OLLAMA_URL` in `backend/.env`. The named model must already be served by that endpoint.
Use `VISION_API_PROTOCOL=openai` for an OpenAI-compatible vision endpoint. Do not point a native
Windows backend at Docker's `host.docker.internal` address unless it resolves in that runtime.
The cloud chat configuration is not used for image recognition.

Automatic mode checks model availability before inference. It keeps a working local result if
the optional vision service fails and adds an explicit warning. Hardware/configuration failures
in a requested CUDA worker remain errors. A verified worker's inability to recognize a drawing
is a separate recognition failure, so the general reader can then try the input.

No recognizer graphs are blindly combined. Conflicting component values, physical connections or
source net labels require review. An extension can be selected only when it includes every local
component and observed pin and preserves the observed net partition. This agreement check does
not establish that either recognizer recovered everything or read the source correctly.

## Detail views and documents

Model input uses one full-page overview and, for large images, up to four overlapping detail
views. Their normalized full-page bounds accompany the request. The model is instructed to
deduplicate overlap and return one physical circuit graph. Settings:

| Setting | Default | Purpose |
|---|---|---|
| `VISION_IMAGE_SIZE` | 2048 | Maximum pixel dimension per image view |
| `VISION_DETAIL_IMAGES` | 4 | Maximum detail views; 0 disables them |
| `VISION_CONTEXT_TOKENS` | 8192 | Ollama vision context; chat stays unchanged |
| `VISION_MAX_TOKENS` | 4096 | Vision output budget for either protocol |

Increase image/context/output budgets only within the model and machine's available capacity.
Output truncated by either model protocol is rejected rather than interpreted as a partial graph.
These bounds are resource controls, not an accuracy guarantee.

All PDF/TIFF pages are processed sequentially, with a limit of 10 pages per import. PDF rendering
is bounded to approximately 25 million pixels per page. Pure-white pages are reported as skipped.
A nonblank page that fails recognition causes an explicit document error, not a page-1-only result.
Page-local net labels remain separate. Duplicate `R1` references, for example, become `R_P1_1` and
`R_P2_1`, with source mappings in warnings. Review those mappings before joining multi-unit devices
or cross-sheet/global nets. This flattened proposal does not automatically recover hierarchy.

## Evaluating new inputs

Create a manifest next to the source images/netlists and their manually checked reference JSON:

```json
{
  "cases": [
    {
      "id": "transistor-amplifier-photo",
      "source": "photo.jpg",
      "reference": "amplifier-reference.json",
      "reference_complete": true
    },
    {
      "id": "mixed-signal-multipage",
      "source": "mixed.pdf",
      "reference": "mixed-reference.json",
      "reference_complete": true
    }
  ]
}
```

References use the app's `Circuit` JSON schema and must use the page-scoped identities described
above where applicable. Mark completeness only after the full circuit has been transcribed and
checked. Partial checkpoints are useful diagnostics but cannot establish full-sheet accuracy.
Keep unrelated real designs, scan conditions, drawing styles and device types in a held-out corpus.
Generated diagrams and netlist-import tests do not establish recognition accuracy on real scans.

Run the installed OCR Python with
`tools/eval/run_corpus.py manifest.json --out results --mode hybrid_max_accuracy --target 0.99`
for the production profile, or choose `--mode vision` explicitly for a configured general reader.
The command writes each recognized proposal and `report.json`. It exits nonzero if any input
fails, has incomplete truth, lacks enough measured data, has a false connection, or misses the
precision/recall target. Per-input scores include:

- Component references, exact value strings, and physical pin presence.
- Connections between physical pins, independent of automatically assigned net names.
- Missing connections and false connections, reported separately.
- Source net labels; automatic names such as `N001` and `NET_3` are excluded from label scoring.
- Exact whole-graph matches, requiring values, pin identity, topology and source labels to match.

Undefined denominators are reported as `null`, not an invented 100%. A target pass is not the
same as an exact whole-sheet match. The evaluator measures the recognized graph; it does not
launch or certify native CAD export, ERC, simulation or source equivalence on its own.

Cadence's PSTXNET `NC` section represents unconnected pins, not one shared electrical net.
When importing/scoring PSTXNET in future, treat those entries according to that format rather
than counting every `NC` entry as joined. Missing source connections still count as errors.

## Staged digital-recognizer regression checks

`tools/eval/recognition_gate.py` runs serial fresh OCR on the supplied digital regression
images and degraded PDFs. It saves source and recognizer-code hashes, raw OCR tokens, pin-strip
observations, recognized graphs and selected ground-truth scores. Use a configured OCR
Python, for example:

```powershell
$env:S2SDN_OCR_DEVICE = 'cuda'
& $ocrPython tools/eval/recognition_gate.py S1 S2 S3 S4 S5 S4-scan300 S4-scan200 S4-blur300 --out before
# Apply one checkpointed change, then:
& $ocrPython tools/eval/recognition_gate.py S1 S2 S3 S4 S5 S4-scan300 S4-scan200 S4-blur300 --out after --baseline before
```

The comparison rejects lost parts, values, or selected pin labels, including a swap between
two correct/incorrect pins that leaves totals unchanged. It also rejects increased spurious
parts where reference annotations exist and decreased counts for count-only annotations.
Replay is diagnostic and cannot pass acceptance. These checks use partial annotations;
they do not establish whole-sheet accuracy or accuracy on arbitrary unseen inputs. Use
`run_corpus.py` with independently checked complete references for that measurement.

`tools/eval/library_gate.py before --out before-library` applies the production library
cleanup using cached library data. It forbids native lookups and fails if required data are
missing. This isolates a library-cleanup change from OCR changes, but does not validate a
saved DSN. Native round-trip validation remains a separate required check for export claims.

Low-resolution IC recovery now preserves separately outlined, unclaimed bodies hidden by
enclosing wire rectangles. Broken outline recovery requires at least three independently
observed copies with matching part value, text orientation, dimensions and label offset,
plus four supported edges at the candidate's own location. Unreadable references remain
review placeholders; part numbers are not assigned solely from repeated layout.
Damaged logic headers can use the existing second reader only when two crops confidently
agree with a value already printed on the sheet and two other bodies match the symbol's
dimensions, orientation and header position. Readable part numbers are preserved.
