# Specctra PCB DSN export

Specctra `.dsn` is implemented through KiCad's native `pcbnew.ExportSpecctraDSN` API. It is an autorouter input, distinct from OrCAD Capture's schematic DSN.

In the Nets download menu choose **PCB autorouter Specctra DSN**. Enter a PCB plan with board width/height, track width/clearance and a placement for every component. Each placement requires an exact installed `Library:Footprint`, x/y in millimetres and optional rotation in degrees. Empty/unknown footprints and missing physical pads are rejected. A voltage-source schematic symbol generally needs a physical connector footprint selected by the user; the software does not guess it.

The export creates a two-copper-layer rectangular board, assigns each source pin/net to actual footprint pads, saves/reopens the PCB and compares the pin/net mapping. It uses native KiCad DSN export, then independently compares the DSN network entries. Download contains:

- `board.dsn`: real Specctra autorouter input
- `board.kicad_pcb` and `board.kicad_pro`: editable board and default routing rules
- source circuit, board plan, verification report and SHA256 manifest

A plan example is in `examples/specctra-plan.json`; adapt references/footprints to your actual circuit. POST the JSON plan to `/projects/{project}/export/specctra` with the normal authenticated application session for API use. Backend worker uses the system KiCad Python (`KICAD_PYTHON` can select the matching interpreter). The Docker image installs official KiCad footprint libraries explicitly.

Export needs no AI model/GPU, paid OrCAD installation or Java. Freerouting is installed separately if routing is wanted; it reads DSN and writes SES. Reimport SES into the same board using KiCad, then inspect routing and run DRC. No Freerouting binary/model/dataset is downloaded on normal application startup.

This export is not fabrication approval. Placement/courtyard overlap, board constraints, routing completion, DRC, electrical/source recognition and target hardware still need review. Arbitrary outlines, multilayer stackups and automatic placement optimisation are outside this first exporter. Windows/Linux end-to-end and latest GUI interaction remain acceptance gates.

Primary documentation:
https://docs.kicad.org/doxygen-python-10.0/namespacepcbnew.html
https://github.com/freerouting/freerouting

## Observed native acceptance

KiCad 10.0.7 on this Mac saved/reopened a divider PCB and exported real DSN. The authenticated API download also passed with independent DSN pin/net comparison. Missing pad, unsafe footprint path and custom track width checks passed. Freerouting 2.0.1 under Java 21 loaded and routed a three-component fixture with a 512 MiB heap/two CPU cap; KiCad imported its SES and produced seven track segments. Files and reports are supplied in examples and evidence. Freerouting 2.5.0 requires a newer Java runtime than the installed Java 21; it was not used for acceptance. These examples do not establish broad routing or manufacturing approval.

Example bounded headless routing command (separate optional installation):

```sh
java -Djava.awt.headless=true -Xmx512m -XX:ActiveProcessorCount=2 -jar /path/to/freerouting-2.0.1.jar -de board.dsn -do board.ses -mp 5 -mt 1 -da --gui.enabled=false --user_data_path=/path/to/private/router-state
```
