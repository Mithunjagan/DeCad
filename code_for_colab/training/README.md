# How to train and connect a circuit vision model

Training is a one-time development task on a separate CUDA GPU. End users run inference; they do not train a model for each button. Save, undo, ERC, export and simulation remain deterministic operations.

## 1. Prepare real paired data

For every image, supply the exact references, values, library symbols and physical pin-to-net connections. Use `example_data/example.json` and its paired `image.png` as the file-format example. The image path is relative to the dataset root; images must remain inside that root. Include a matching `spice_netlist` so the audit can check numerical values, ground assignments and net partitions. App-generated folders are accepted directly: the audit also recognizes sibling `circuit.png` and `circuit.cir` files.

Review the image against its annotation in a circuit editor. Only after that review, set `image_source_review` to `verified` in the sample JSON. An agreement between JSON and SPICE does not establish that either matches the image.

Collect multiple independent circuit families: resistive networks, RC/RL/RLC filters, diodes/transistors, supported op-amps, and the IC families the product intends to handle. Add variations in values, labels, topology, camera angle, lighting and drawing style. Copies or augmentations of the same drawing must share a `group` so they cannot leak across splits. External datasets need license review and conversion to this schema; they are not installed automatically. CGHD supplies handwritten diagrams and annotations, not an automatically verified SPICE netlist for every image: https://zenodo.org/records/10056817

The included four samples cover two families. They are an example, not a production training corpus. The trainer's minimum of 100 training pairs and separate validation/test groups is a preflight safeguard, not a claim that 100 samples achieve production accuracy.

## 2. Audit and split (can run without a GPU)

From the extracted product root, using the backend Python environment:

```sh
python training/dataset_tools.py audit --input /path/to/paired-data
python training/dataset_tools.py prepare --input /path/to/paired-data --output /path/to/prepared-data
```

Inspect `audit.json` and rejected entries. The tool checks duplicate image hashes, path safety, JSON schema, ground/pin/net equivalence, and topology groups. It creates `train.jsonl`, `validation.jsonl`, `test.jsonl` and copied images. Do not move the same circuit family into multiple splits to increase apparent accuracy.

## 3. Train on a separate GPU

Use a CUDA-compatible Linux environment, a GPU supporting BF16, and the matching PyTorch build. This supplied profile checks for at least 12 GiB **free** GPU memory before loading weights. Actual peak use must be measured; this floor is not a guarantee that every GPU with 12 GiB will fit every input. The training loop has not been exercised on a GPU in this verification session.

```sh
python -m venv .venv-training
. .venv-training/bin/activate
python -m pip install -r training/requirements-gpu.txt
python training/finetune.py --dataset /path/to/prepared-data --output checkpoints/circuit-lora --model Qwen/Qwen2.5-VL-7B-Instruct
```

The profile uses four-bit base weights, LoRA, one image per microbatch, bounded image tokens and gradient accumulation. It writes the adapter, processor and training report. It does not mark the model approved for release. The official foundation model is https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct.

## 4. Validate the trained model

Run the untouched test split and manually compare predictions to source images. Measure component type/reference/value accuracy, exact physical pin-to-net connectivity, ground identification, graph exact match, failure rate, latency and peak memory. Use native KiCad ERC and simulator results as additional checks. ERC alone cannot prove correct recognition. Retain failed examples and refuse unsupported circuits instead of inventing missing wires.

After serving the adapter in step 5, run the prepared evaluator from a backend Python environment:

```sh
IMAGE_MODE=vision VISION_MODEL=schematic2sdn-qwen-vl VISION_OLLAMA_URL=http://localhost:11435 python training/evaluate.py --dataset /path/to/prepared-data --output vision-evaluation.json --limit 100
```

It enforces reviewed, hashed test images and disjoint circuit groups, measures component/reference/value/library precision and recall, checks exact pin/net/ground partitions, and records failures and latency. It does not automatically approve a release.

A checkpoint must pass this evaluation before a trained or production-ready claim. This package currently contains no trained adapter and no successful general-vision benchmark.

## 5. Serve the adapter separately

`serve.py` provides the Ollama-compatible `/api/tags` and `/api/chat` interface expected by the app. It loads only the specified Qwen base and local PEFT adapter, accepts one bounded image, serializes GPU requests, and releases model objects after a request. GPU execution and peak-memory behavior still require testing on the chosen GPU.

On the GPU machine, from the product root:

```sh
export S2SDN_ADAPTER=/absolute/path/to/checkpoints/circuit-lora/adapter
export S2SDN_MODEL_TAG=schematic2sdn-qwen-vl
python -m uvicorn serve:app --app-dir training --host 127.0.0.1 --port 11435
```

Bind to loopback. For a remote GPU, use an SSH tunnel on your Mac:

```sh
ssh -N -L 127.0.0.1:11435:127.0.0.1:11435 user@gpu-host
```

In a root `.env` file beside `docker-compose.yml`, on Docker Desktop for this Mac:

```dotenv
VISION_OLLAMA_URL=http://host.docker.internal:11435
VISION_MODEL=schematic2sdn-qwen-vl
IMAGE_MODE=vision
```

Then run the launcher again. Chat remains on its small local Ollama model. Verify the adapter appears in Applications & models and that an actual image import returns a reviewable proposal before deployment. The remote host address, SSH access, labeled data and GPU are resources you must provide; the app does not provision or bill for them. Linux host networking/tunnel setup and Windows deployment require their own acceptance tests.

## Present evidence

- Four supplied pairs pass JSON/SPICE consistency; image annotation review is still required.
- Three controlled pretrained-language-model planning cases pass native ERC and simulation.
- The custom trainer rejects the supplied data before downloading weights.
- Adapter API configuration/rejection/routing is tested with test doubles.
- No custom training or actual adapter GPU inference is claimed.
