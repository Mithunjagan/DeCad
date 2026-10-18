# Third-party software

The application downloads its dependencies from official package registries and upstream sources during the container build. Upstream license terms apply; this document does not replace those licenses.

- KiCad: GNU GPL v3 or later. Debian packages include license/copyright files in /usr/share/doc/kicad*. KiCad symbol libraries have their own license and schematic-use exception. https://www.kicad.org/about/licenses/
- Qucs-S 26.1.1: GNU GPL v2 or later. The Docker image contains the unmodified corresponding upstream source archive at /usr/share/qucs-s/source.tar.gz, including license text and build files. Build commands are in docker/kicad/Dockerfile. https://github.com/ra3xdh/qucs_s/releases/tag/26.1.1
- KiCanvas (KiCad schematic viewer in the centre canvas): MIT license, Copyright (c) Alethea Katherine Flowers. Bundled unmodified as frontend/public/kicanvas/kicanvas.js from https://kicanvas.org/kicanvas/kicanvas.js (downloaded 2026-10-18). Its toolbar icons and UI font load from Google Fonts. https://github.com/theacodes/kicanvas
- ngspice: BSD-style license. Debian copyright/license text is under /usr/share/doc/ngspice. https://ngspice.sourceforge.io/
- LTspice: installed separately by the user under the vendor's license. No LTspice executable or installer is bundled. https://www.analog.com/en/resources/design-tools-and-calculators/ltspice-simulator.html
- Ollama and optional model weights: separate upstream licenses. Models are fetched on demand, not included in this source ZIP. Check the chosen model's license before redistribution. https://github.com/ollama/ollama
- Python and JavaScript dependencies: package metadata and upstream licenses apply. Exact direct dependency versions are recorded in backend/requirements.txt and frontend/package-lock.json.

External training corpora are not redistributed. Supplied synthetic examples are identified as such in the dataset audit; visual source review is required before training.
