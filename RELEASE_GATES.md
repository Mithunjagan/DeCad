# Shipping gates

This package is a working release candidate. It is not approved as a general image-to-circuit product or a fully validated three-OS release.

| Gate | Evidence / remaining work |
|---|---|
| Native KiCad editing, ERC and connectivity | Automated operation tests and actual macOS/Linux-container execution |
| ngspice and Qucs-S simulation | Actual native Qucs-S compilation followed by ngspice; divider 2.5 V and RC final 5 V |
| LTspice interoperability | SPICE bundle and uncompressed transient RAW import implemented; actual LTspice execution unavailable on this machine |
| Desktop bridge | macOS, Windows and Linux discovery/argument tests; actual Windows/Linux desktop execution still required |
| Local language model | Pretrained qwen3:0.6b; 3/3 controlled divider/RC planning cases passed; broader accuracy remains unmeasured |
| General image recognition | General accuracy not passed. CPU OCR/OpenCV recovers clean R/C/V component and pin/net proposals with reviewed apply; independent fixture tests pass, but supplied-pair exact agreement was 0/4. |
| Custom vision training | Not run. Included data: 4 validated image/JSON/SPICE pairs, 2 topology families. No verified adapter/checkpoint |
| Florence-2 / Qwen2.5-VL-7B | Architecture recommendations are not proof of integration or training. Florence-2 is not implemented in this release; the Qwen GPU adapter trainer/server/evaluator support 7B and experimental 3B profiles but GPU execution is unvalidated; larger Ollama vision models are optional and unvalidated |
| Cross-platform shipping | Shell and PowerShell launchers plus CI matrix supplied; actual Windows/Linux install/browser/native-app acceptance still required |

## Required vision evidence

The training tools audit image pairs, compare JSON/SPICE connectivity, enforce topology-disjoint splits, and check image hashes. The GPU trainer refuses this four-sample dataset before loading weights. Its training loop has not been validated on a GPU. A trained adapter still requires held-out component/reference/value/pin/net metrics, manual failure review, and memory/latency measurements before a shipping claim.

The named CGHD, AMSnet and Masala-CHAI corpora are not installed. Catalog sample counts describe external corpora, not supplied training records. New synthetic divider/RC examples do not establish independent generalization to ICs, handwritten symbols, crossovers, or junctions.

## Resource policy

Core memory caps: 1 GiB and 512 MiB. Default optional local-model cap: 2 GiB, two CPUs, one loaded model and one request; no additional swap and unload after each request. CPU circuit recognition is the default image mode. Large vision mode is opt-in on a larger Docker allocation and uses a separate configurable model cap. The launchers do not change Docker Desktop's allocation.

Deterministic buttons (save, undo, ERC, exports, bridge and solver) do not require trained models. Model proposals remain explicit reviewable data; model text is never executed as code.

Latest UI visual acceptance remains open: browser access was rejected by browser security policy. Current test results are recorded in evidence/product-native-tests.log. Host UID/GID shared-file read/write and non-root service startup were checked on this Mac; real Linux desktop bridge acceptance remains required.

The requested DSN is clarified as Specctra PCB autorouter DSN. Native KiCad-based export is implemented; see [SPECCTRA.md](SPECCTRA.md). OrCAD schematic DSN remains a separate unsupported format.
