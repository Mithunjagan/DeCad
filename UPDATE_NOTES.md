# Product update

The Desktop installation has been updated. Open http://localhost:3100 and refresh to load the new interface. Existing GitHub credentials, projects and runtime data are preserved.

Image/PDF imports open an editable component and pin/net review form. Use the source preview, correct values and connections, check the review box and apply. Choose Labels only when you intend to specify wiring yourself. CPU circuit mode supports clean R/C/V diagrams; a configured vision server remains optional.

Download → Specctra opens a PCB planning form. Search installed footprints, inspect their physical pad numbers, set board size/placement/routing dimensions, and export the editable PCB plus autorouter DSN. The board remains unrouted until processed in KiCad/Freerouting.

For an RTX 3050 with 8 GB VRAM and 16 GB RAM, see training/HARDWARE.md. The experimental 3B profile is implemented but requires a measured GPU smoke step and reviewed data. Default application use loads no language/vision model.

This remains a release candidate. See VERIFICATION.md and release-status.json for actual evidence and unresolved release requirements.
