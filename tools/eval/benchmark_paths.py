"""Resolve actual predictions in the legacy and process-isolated gate layouts."""
def prediction_path(root,identity):
    for path in (root/identity/'recognized.json',root/identity/identity/'recognized.json'):
        if path.is_file():return path
    raise FileNotFoundError(f'No prediction for {identity} under {root}')
