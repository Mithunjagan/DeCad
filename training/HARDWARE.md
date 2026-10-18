# RTX 3050: 8 GB VRAM / 16 GB RAM

The experimental `3b-8gb` profile is implemented for Qwen2.5-VL-3B: four-bit NF4, LoRA rank 4, batch one, frozen vision parameters, gradient checkpointing, 256 image tokens and at most 1,536 total tokens. It requires 6.5 GiB free GPU memory before loading. This is a conservative preflight threshold, not a measured fit guarantee. No GPU training was executed on the development Mac.

Use a separate CUDA machine and a reviewed, audited dataset (at least 100 training pairs and independent validation/test groups). From the product root:

```sh
python training/finetune.py --profile 3b-8gb --dataset /path/to/reviewed-data --output checkpoints/circuit-lora --smoke-test
python training/finetune.py --profile 3b-8gb --dataset /path/to/reviewed-data --output checkpoints/circuit-lora --epochs 3
```

The smoke run performs one optimizer step on the longest annotation, records elapsed time, peak reserved GPU memory and remaining headroom, and does not save an adapter. The full 3B run requires that report to match the dataset, GPU and profile settings with at least 768 MiB measured headroom. A successful smoke step does not guarantee every later sample fits. Overlong targets are rejected instead of truncated; OOM during training stops the run and writes a failure report. Existing adapter output is never overwritten.

16 GB system RAM may be tight during loading and preprocessing. Stop other GPU-heavy applications while training. Models stay on the GPU rather than spilling layers into CPU RAM. The profile can fail cleanly on an RTX 3050; actual suitability must be measured on that machine. Larger or denser circuits may require the default `7b` profile, which retains its 12 GiB free-memory guard.

The adapter server accepts either registered 3B or 7B base model, chooses matching token/memory limits, and advertises configured weights only when both adapter configuration and nonempty safetensors files exist. Actual weight loading remains part of inference validation. Run held-out graph and solver evaluation before promoting any trained weights.

End users do not need CUDA, training data, or a GPU. The default workbench uses the CPU recognition path. A separately hosted model can supply optional vision inference without loading a model on the user's computer.

Primary references: [Qwen2.5-VL-3B model card](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct), [PEFT quantized adapter training](https://huggingface.co/docs/peft/developer_guides/quantization). These describe model and training techniques; they do not establish this application's RTX 3050 memory fit or circuit accuracy.
