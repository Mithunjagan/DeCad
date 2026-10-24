#!/usr/bin/env python3
"""Convert raw AMSnet 1.0 schematic/SPICE dataset pairs into canonical Schematic2SDN training format."""
from __future__ import annotations
import argparse
import glob
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.ingestion import parse_spice

def convert_amsnet(raw_dir: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dirs = sorted(glob.glob(str(raw_dir / 'AMSnet1.0' / '*')))
    print(f"[*] Found {len(raw_dirs)} directories in {raw_dir / 'AMSnet1.0'}")

    converted = 0
    skipped = 0

    for d in raw_dirs:
        folder = Path(d)
        sample_id = folder.name
        cir_file = folder / f"{sample_id}.cir"
        img_file = folder / f"{sample_id}.jpg"
        bbox_file = folder / f"{sample_id}_bbox.json"

        if not (cir_file.exists() and img_file.exists()):
            skipped += 1
            continue

        try:
            cir_text = cir_file.read_text(encoding='utf-8', errors='ignore')
            circuit, _ = parse_spice(cir_text)

            # Load bboxes if available
            bboxes = {}
            if bbox_file.exists():
                try:
                    bboxes = json.loads(bbox_file.read_text(encoding='utf-8', errors='ignore'))
                except Exception:
                    pass

            target_dir = output_dir / sample_id
            target_dir.mkdir(parents=True, exist_ok=True)

            # Copy image as circuit.jpg / image.png
            import shutil
            target_img = target_dir / "circuit.jpg"
            shutil.copyfile(img_file, target_img)

            # Write standard paired circuit.json
            sample_data = {
                "sample_id": f"AMS_{sample_id}",
                "source_dataset": "AMSnet-1.0",
                "image_rel_path": "circuit.jpg",
                "has_exact_connectivity": True,
                "components": [c.model_dump() for c in circuit.components],
                "nets": [n.model_dump() for n in circuit.nets],
                "spice_netlist": cir_text,
                "bboxes": bboxes,
                "image_source_review": "required",
                "image_source_review_reason": "Conversion checks SPICE parsing only; independently review the image against component values and physical pin connectivity."
            }

            (target_dir / "circuit.json").write_text(json.dumps(sample_data, indent=2))
            converted += 1
        except Exception as e:
            skipped += 1

    print(f"[+] Converted {converted} samples successfully! (Skipped: {skipped})")

def main():
    parser = argparse.ArgumentParser(description="Convert AMSnet 1.0 dataset to Schematic2SDN format")
    parser.add_argument('--input', type=Path, default=Path('/Users/raghavkrishna/Downloads/Schematic2SDN-training-data'))
    parser.add_argument('--output', type=Path, default=ROOT / 'training' / 'converted_amsnet')
    args = parser.parse_args()

    convert_amsnet(args.input, args.output)

if __name__ == '__main__':
    main()
