# Production completion plan

The current package is a release candidate. Follow this sequence; a passing source test suite alone is not shipping approval.

## Data and training

1. Obtain licensed, independently reviewed circuit image/JSON/SPICE pairs. The supplied four examples are insufficient. Start with a narrowly documented supported circuit domain, collect multiple independent topology families, and hold back genuinely independent images. Synthetic divider/RC copies cannot demonstrate IC or handwritten-circuit generalization.
2. Run the audit and split commands in `training/README.md`. Resolve every rejection and review image fidelity. Keep original hashes and annotation provenance. The 100-training-pair minimum is only a preflight floor.
3. Use a separate BF16-compatible CUDA GPU. The 7B profile requires at least 12 GiB free memory; the experimental 3B profile requires a measured smoke step and its own memory guard (see training/HARDWARE.md). Provisioning, SSH credentials and any cloud spending require an actual selected environment. No cloud resource is provisioned by this package. Train with the guide's commands and retain the training report, dependency versions, GPU type, duration and measured peak memory.
4. Serve `checkpoints/circuit-lora/adapter`, connect it through the SSH tunnel, and evaluate untouched test data. Retain all predictions and failures in `vision-evaluation.json`. The provisional release check requires at least 100 test cases, zero extraction failures and 99% exact graph matches. These are proposed engineering gates, not established achieved accuracy or a universal safety standard. Also inspect ERC, simulator equivalence and every failure; decide the supported product scope based on the results.

## Native acceptance on each OS

Use clean macOS, Windows and Linux machines with the four intended applications. Test install/start/stop/restart, project creation, editing and connecting physical pins, undo/redo, import review, source conflict handling, save/reopen, ERC, all exports, desktop open, simulation and waveform import. Inspect actual native application results. Launchers and mocked portability tests cannot replace these runs.

For LTspice, open the exported circuit, run transient simulation, import the actual RAW output and compare node names, time samples and voltages against ngspice. Test Qucs-S native schematic opening as well as its CLI simulation. Retain logs and screenshots. On each OS exercise every visible button, error, empty state and review dialog in the current build.

Measure cold start, normal editing, imports and inference on the lowest supported hardware, with the configured memory caps. Record CPU/RAM/GPU, idle and peak usage, latency, resource exhaustion recovery and saved-project recovery. Set published minimum requirements from observations. Do not advertise support for every machine.

## Record and review

For each pending key in `release-evidence.json`, attach a local artifact path under the product root, reviewer, date, and status. A passed record has this shape:

```json
{"status":"passed","artifact":"evidence/windows-acceptance.md","reviewer":"name","date":"YYYY-MM-DD"}
```

Artifacts must describe the tested build, machine, steps, results and limits; do not mark unavailable tests as passed. Run:

```sh
python tools/check_release.py --output release-status.json
```

A nonzero exit means release blockers remain. Passing means the recorded evidence is ready for release review, not independently certified. Freeze validated dependencies, repeat the required regression/acceptance checks for the final build, review third-party/data/model redistribution rights, and package without credentials, runtime projects or private training records. Keep trained weights separately when redistribution is not authorized.

## Added external data

The separately supplied Schematic2SDN-training-data bundle contains 734 AMS-Net 1.0 schematic/SPICE pairs plus bounding boxes and upstream LICENSE. Hashes and source are in its manifest. All are marked review required. No automatic MOSFET-to-KiCad pin mapping or image fidelity approval is claimed. This improves available development material but does not complete custom training.

The requested DSN is clarified as Specctra PCB autorouter DSN. Native KiCad-based export is implemented; see [SPECCTRA.md](SPECCTRA.md). OrCAD schematic DSN remains a separate unsupported format.
