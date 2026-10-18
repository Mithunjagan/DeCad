# Unified component libraries

The **Libraries & footprints** tab now includes a shared KiCad/OrCAD component
browser. The database is per workspace at `.libraries/unified/components.sqlite3`.
Installed source directories are read only; indexes, normalized records and
authorized downloads stay in the workspace. Nothing is indexed at application startup.

## Use

For automatic acquisition, open a project, enter **Timer:NE555P** (or a part
number) in the search field, choose an unused reference, and press **Find component
and add to project**. The app searches the unified store, installed KiCad and
accessible OrCAD libraries, then configured authorized providers and the official
public KiCad fallback when permitted external lookup is enabled. It validates the
symbol/footprint pair, caches it, places the symbol, and creates a project-local
`DeCadUnified.pretty` library and `fp-lib-table`. The project also keeps source
provenance and applicable licenses. Unresolved assets leave the design unchanged.

For manual library management:

1. Expand **Library locations, asset import and source permissions**. Select a
   detected location or enter an absolute directory path.
2. Record the source license and permitted use. Unknown permissions allow only
   metadata indexing. Geometry import and redistribution are separate permissions.
   The application records your declaration; it does not grant asset rights.
3. Save the location and scan it. Scans recurse through supported files in bounded
   batches; **Continue scan** resumes a large library. Removing an index does not
   delete source files. Uploading an asset also requires recorded import permission.
4. Search by symbol/footprint name, MPN or description. Select a symbol and a
   footprint, inspect their limits, then **Validate and cache pair**.
5. A verified pair can be placed in the current schematic at an automatically
   spaced grid position. Subsequent additions advance the reference. Select a
   reference without conflicts. Multi-unit libraries export, but placing all units
   through this browser is not implemented yet.
6. Choose Internal, KiCad, OrCAD or Allegro export. Unsupported target/source
   combinations return an error. Redistribution permission is required to download
   an asset export.

Checks cover pin/pad number equality, finite coordinates and positive pad sizes.
They do not establish manufacturer tolerances, assembly clearances or electrical
equivalence. Review package dimensions and the datasheet before manufacture.
Source hashes and policy changes invalidate reuse of cached records.

## Current format coverage

| Format | Implemented | Export and version evidence |
|---|---|---|
| `.kicad_sym` | In-file and modular-file inheritance, units, pins, properties, geometry, original symbol tree | Formats 20231120 and 20251024 checked with installed KiCad 10 CLI |
| `.kicad_mod` | Pads, dimensions, layers, footprint graphics, model references, original tree | Formats 20240108 and 20260206; real 8-pad footprint reopened with KiCad's native API |
| `.olb` | Native package index; on-demand electrical pins, numbers, properties and line/box graphics | Capture API **26.1.0 d001**; package-only native OLB export independently reopened and compared; complete supported symbols also export to KiCad |
| `.dsn` | Existing Capture design import/extraction workflow; unified index catalogs the design | Existing native DSN writer reopens and checks connectivity; not a universal design converter; Specctra DSN is a different format |
| `.opj` | Text project references | No binary conversion claimed |
| `.dra`, `.psm` | File discovery, identity and source provenance | Geometry extraction/export unavailable |
| `.pad` | Padstack discovery, identity and source provenance | Pad geometry extraction/export unavailable |
| `.brd` | Board database discovery and source provenance | Geometry extraction/export unavailable |
| `.step`, `.stp`, `.wrl` | Independent model references; footprint model references retained | No solid/mesh conversion or dimension validation |

The application functions without Capture. Its absence, unsupported native product
version, unavailable license, malformed files and partial vector extraction are
reported explicitly. The unified native adapter is verified for Capture 26.1 only;
binary layouts are never inferred from filename extensions. KiCad-to-OLB and
Allegro binary writing are not implemented.

The internal record includes MPN, schematic graphics, electrical pins, package,
footprint graphics, physical pads, 3D references, datasheets, source format/version,
original path, license permissions and validation. A validated linked pair retains
both source provenances. Geometry uses millimetres.

## External provider protocol

No commercial provider is enabled by default. Configure an authorized HTTPS endpoint under
**Authorized providers**, or `POST /components/providers`. Credentials are read
from the named backend environment variable and are not returned by the API.

The endpoint implements `GET <base>/search?q=<part number>`:

```json
{"items":[{"assets":[{"url":"assets/part.kicad_sym","sha256":"optional expected SHA-256"}]}]}
```

Assets must use the same HTTPS origin and a supported extension. Redirects are not
followed. Downloads are limited to 50 MB per asset, hashed, and passed through the
normal importer. Downloading never establishes pin/pad correctness; verification
and placement remain separate steps. There are no preconfigured commercial
provider integrations or claims of live supplier verification.

The automatic add route is `POST /projects/{pid}/components/acquire` with
`{"query":"Timer:NE555P","ref":"U1","external":true}`. It uses targeted library
reads, avoiding a full index rebuild for one part. It never substitutes a nearby
part number. If no verified pair is available, the result explains whether a
footprint, license permission or supported provider is missing.

The public fallback downloads from official KiCad repositories pinned to **10.0.5**,
including inherited symbol definitions and the matched footprint. It verifies and
retains the upstream license. Standalone CC-BY-SA library downloads include license
and attribution in a ZIP. See [KiCad's license explanation](https://www.kicad.org/libraries/license/index.html).
Unknown parts absent from the exact library catalog need a configured provider;
this feature does not scrape arbitrary websites or claim universal component coverage.

The separate manual scan UI uses bounded batches; continue scans of large
locations from the browser. 3D references are retained; downloading every referenced
mechanical model and validating its solid dimensions are not yet implemented.

## Native interfaces and parser research

Capture's documented Tcl interface is the preferred installed-tool path.
[Cadence's Capture Tcl overview](https://resources.academic.cadence.com/schematic-capture/orcad-capture-tcl-tk-3)
and local `tools/capture/tclscripts` API examples informed the adapter. Native
export uses scratch copies because Capture's writer may create library locks.

[OpenOrCadParser](https://github.com/Werni2A/OpenOrCadParser) is MIT-licensed and
archived as of 2026-05-31. It focuses on Capture DSN/OLB and backups; its README
describes an abandoned XML exporter and preliminary KiCad importer work. It is
not bundled or treated as a verified writer.

[OpenAllegroParser](https://github.com/Werni2A/OpenAllegroParser) is also
MIT-licensed and archived as of 2026-05-31. Its README documents partial padstack
work against 17.4-2019 S019, including parameter-search limitations. Listing BRD,
DRA and PSM as project goals does not establish working format coverage.

[Cadence's padstack SKILL application note](https://community.cadence.com/cfs-file/__key/communityserver-discussions-components-files/137/MakePadstackInAllegroSkill.pdf)
describes layer geometry, drill data and native padstack APIs. No SKILL code is
installed into the user's Cadence setup, and no Allegro geometry adapter is
claimed verified. A future adapter must be enabled for a tested product version
and available license; official exports should be preferred over guessing binaries.

Research checked 2026-10-18. Asset licenses are independent of parser licenses.

## Reproduce the bounded acceptance check

From the project root with the existing native environment:

```powershell
$env:KICAD_CLI='D:\KICAD\bin\kicad-cli.exe'
$env:KICAD_SYMBOL_DIR='D:\KICAD\share\kicad\symbols'
backend\.venv\Scripts\python.exe tools\eval\check_component_import.py
backend\.venv\Scripts\python.exe tools\eval\check_components_api.py
backend\.venv\Scripts\python.exe tools\eval\check_acquire_component.py
backend\.venv\Scripts\python.exe tools\eval\check_acquire_component.py --public
node tools\eval\check_component_ui.cjs --place
```

The first uses original CC0 fixtures from both ecosystems and checks source-tree
hashes, shared search, pin/pad mapping, cache reuse, real KiCad schematic placement,
KiCad CLI SVG export, and native OLB export with independent readback. The second
uses the running local API and removes its temporary smoke project through the
normal recoverable-delete route. Evidence is under
`backend/.state/codex-20261018/component-acceptance/` and `component-api/`.
This bounded fixture check does not establish broad vendor-library compatibility.
The local and real public-network NE555P checks both verify 8 pins, 8 physical
pads, native footprint readback, schematic placement and subsequent cache reuse.
Evidence: `backend/.state/codex-20261018/acquire-local/` and `acquire-public/`.
