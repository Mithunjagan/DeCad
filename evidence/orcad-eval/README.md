# OrCAD recognition evaluation

`ground-truth/S*.json` were transcribed by hand from the full-resolution sample scans: part
references and part numbers, plus explicitly labelled pin→net checkpoints (pins whose net name is
printed on their own stub, so the expected net is unambiguous). S3/S5 part lists are partial and
S2 (1600 px) only has part-number counts. `score.py` reports part recall/precision/value accuracy and
exact checkpoint pins. `run_samples.py` runs the app's own end-to-end pipeline.
