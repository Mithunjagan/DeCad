# Five workspace experiences — 15 October 2026

## Open the application

Extract `Schematic2SDN-5-Experiences.zip`. Keep your existing private configuration files when upgrading; `.env` files, Git metadata and runtime environments are excluded from the archive.

Run `start.command` on macOS or `start.ps1` on Windows for the core workspace. Run `start-full.command` or `start-full.ps1` to request both local prompt synthesis and detailed vision services. The existing Docker-memory checks still apply (vision requires at least 7.5 GB allocated to Docker); model downloads require a network connection. The Assistant now reports whether each model is actually available. Desktop application launching requires the desktop bridge and the corresponding installed application.

## Five experiences

Choose WORKSPACE in the top bar. The choice persists locally. Ctrl/Cmd + Shift + 1–5 also switches experiences.

| Experience | Structure and workflow |
| --- | --- |
| Studio IDE | Dark explorer, document tabs, drawing canvas, assistant dock, and bottom Problems / Output / Netlist panel. Inspired by the supplied HTML. |
| Classic EDA | Light engineering desktop inspired by the Keil screenshot: menu strip, tool strip, project tree, component property grid, schematic, and bottom command/diagnostics dock. |
| Canvas | Broad drawing surface, floating vertical tools, pan/zoom controls, and an assistant that opens on demand. |
| Review Desk | Original source and native schematic side by side, source selector, verification checklist, component/net inspection, and explicit approval of imported proposals. |
| Simulation Lab | Schematic and transient oscilloscope together, measured signal readouts, simulator action, and diagnostic/netlist dock. |

These change panels and information architecture as well as appearance. They share the same underlying project, schematic, revision history and native exporters. The offline `Workspace-Experiences.html` is an interface preview using a verified native divider and actual ngspice measurements; it is not the application backend. Its workspace switch, document tabs and zoom controls work locally. Run the full application for generation, import and editing.

## Circuit generation and source handling

- Removed geometric-recognition code that invented 74-series ICs, guessed IC pin counts and created bus connections when detection failed.
- Geometric mode is explicitly restricted to clean labeled R/C/V diagrams. It associates actual values, recognizes wire topology, re-reads small text at higher resolution, and rejects ambiguous crossings or unsupported devices. It no longer substitutes default component values.
- Detailed vision is the default image-import selection. It uses an overview and overlapping detail crops. Failed vision requests report an error rather than returning a substituted geometric circuit.
- Complex natural-language requests produce a complete component/pin/net proposal from the configured model. They are no longer classified into a handful of unrelated templates. Short divider / RC commands retain deterministic offline generation.
- Every upload produces a reviewable proposal. An unwired component list or unreadable value cannot be applied as a complete circuit.
- All supported PDF pages are processed. Repeated references across pages require separate sheets or explicit hierarchical data; page-local net names remain separate until reviewed.
- Imported SPICE diode/transistor model declarations survive the review step and are used for simulator exports. Hierarchical subcircuits require an exact symbol and physical pin mapping rather than being silently flattened.
- Multi-unit symbols now include the other gates and power unit under the same package reference. Editing a value or deleting a package affects all its units.
- New generated circuits use deterministic placement and orthogonal routing that avoids symbol bodies and other nets. Congested connections retain named net labels and a warning.
- Before keeping a generated/imported design, KiCad exports its real netlist and the application compares component values and every proposed physical pin/net assignment. A mismatch rolls back the schematic.
- The canvas fits the circuit content by default, so small designs no longer occupy a tiny corner of an A4 page. Full-sheet view, pan and zoom remain available. Reference/value text rotation is corrected for horizontal symbols.
- Native Specctra DSN export and footprint/pad verification from the preceding update are retained.

Model output is still a proposal. No model recognition accuracy claim was established for arbitrary user circuits. Device choice, analog behavior, model quality, supply connections and source equivalence still require engineering review; graph equivalence alone does not establish functional correctness. Existing saved schematics are not automatically rewritten—re-import or regenerate them to use the new placement and routing.

## Verification

- Next.js 16.4 production build passed with the final frontend source.
- Frontend review-model suite: 5 passed.
- Broad targeted backend run: 51 passed, 3 skipped (unavailable external simulator checks). This covered real image/PDF recognition, prompt/upload workflows, integrations, native DSN mapping and extraction inputs.
- Final circuit-fidelity regression run: 10 passed. This includes full-graph proposals, short detection, visible routing, multi-unit power pins, all PDF pages, no fabricated blank-image circuit, active-device rejection in geometric mode, and preserved SPICE models.
- Vision and prompt-model responses are mocked in the relevant regression tests; those tests verify pipeline behavior, not model recognition accuracy.
- Browser checks completed for all five experiences after recovering the preview connection: component selection and property inspection, source image comparison, Canvas assistant open/close, and actual ngspice transient acquisition (VIN 5 V, VOUT 2.5 V). Screenshots are in evidence/experiences.

The full application retains the existing native-KiCad editor handoff for detailed editing. The preview canvas is a native SVG viewer. Placement, search, and physical-pin connection tools now have working dialogs that apply and validate native changes through the backend.


## Workbench v3 update

- Classic EDA is a separate desktop component with its own title strip, command ribbon, navigator tabs, MDI document tabs, editable object properties and build/command console. It does not render the IDE chat layout.
- Canvas has a floating tool rail and optional command panel; Review Desk is a two-document comparison station with a verification column; Simulation Lab prioritizes circuit and acquired signals. These workspaces use their own navigation instead of the IDE document-tab strip and explorer.
- Open With maps KiCad, LTspice, SPICE and recognized Qucs files to their compatible applications. Ambiguous `.sch` and `.dsn` files are not guessed. Original-file launching preserves the selected file and safe sibling data; a manual application override explicitly exports the CURRENT project when the selected file is incompatible. Import and review first to export the selected file's circuit.
- The desktop bridge selects KiCad's PCB or schematic editor by document type. Missing applications and bridge failures produce explicit errors. Four application integrations are supported; applications must be installed separately.
- Native KiCad schematic uploads can be extracted into reviewable circuit proposals. Image recognition and arbitrary prompt synthesis require the configured local models; the test environment did not have those model services running. Mocked model tests establish pipeline behavior only.
- A downloadable Verification Evidence report includes native inventory, ERC results and comparison against the last approved proposal. Added components, changed values or pin/net differences invalidate that comparison. Source accuracy is not measured and electrical functionality is not proven by this report.
- Reconnecting a physical pin now detaches its previous native wire, rebuilds explicit connectivity, and checks the exported KiCad graph before accepting the change.
- Removed invented supplier part numbers, pricing and stock from the BOM. Unknown supplier data is marked as not specified/not queried.
- Grid visibility, component highlighting, search, placement and connection controls have actual actions. Source editing retains conflict checks and undo/redo remains native revision history.

### Local browser validation

Confirmed Classic value edit (R1 10k → 4.7k), extension association and override warning, verification report, five distinct workspace layouts, uploaded `.cir` → ngspice suggestion and successful original-file bridge execution. Simulation Lab acquired 1008 actual ngspice samples: VIN 5.000 V / VOUT 3.401 V. KiCad and ngspice are installed on this machine; LTspice and Qucs-S are unavailable and their native launches were not tested.

Run `start-full.command` (macOS/Linux) or `start-full.ps1` (Windows) from the extracted project to start the complete configured application. The HTML deliverable is a screenshot comparison gallery, not a standalone replacement for the backend.

100% correctness for arbitrary circuits, source images or natural language is not guaranteed. Unsupported models, ambiguous symbols and unreadable details require correction or an explicit supported circuit description. Review, native graph validation, ERC and simulation serve different purposes and do not replace engineering acceptance.

### Final v3 verification

Production build passed. Frontend review-model tests: 5 passed. Final targeted backend run: 68 passed, 2 skipped (unavailable external tools). This run covered file dispatch, fidelity, operations, application integrations and bridge portability. Browser placement and physical-pin connection dialogs both applied native changes successfully; unconnected pins were reported through ERC.
