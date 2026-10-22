"""Export review candidates from licensed native KiCad schematics.

Images and physical-pin targets come from the same file. This establishes
netlist provenance, not visual legibility or training readiness. Hierarchical
projects are skipped until page-specific boundary annotations are supported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.ingestion import Circuit
from app.sexpr import TOKEN, children, parse


def parse_native(text):
    # KiCad permits literal newlines in quoted text. Normalize those controls
    # for the app's JSON-string reader without changing the source document.
    tokens = []
    for match in TOKEN.finditer(text):
        token = match.group(1)
        if token.startswith('"'):
            token = re.sub(r'[\x00-\x1f]', lambda m: json.dumps(m.group())[1:-1], token)
        tokens.append(token)
    return parse(' '.join(tokens))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def circuit_from_xml(path):
    document = ET.parse(path).getroot()
    sheets = document.findall('./design/sheet')
    if len(sheets) != 1:
        raise ValueError('Expected exactly one exported sheet.')
    # The application uses uppercase reference identifiers. Keep this a
    # bijective name mapping, never a merge; component values retain their case.
    refs = [item.attrib['ref'] for item in document.findall('./components/comp')]
    aliases = {ref: ref.upper() for ref in refs}
    if len(refs) != len(set(aliases.values())):
        raise ValueError('Native references collide after uppercase normalization.')
    components = []
    for item in document.findall('./components/comp'):
        source = item.find('libsource')
        if source is None:
            raise ValueError('Component lacks its native symbol identity.')
        components.append({
            'ref': aliases[item.attrib['ref']], 'value': item.findtext('value') or '',
            'library': source.attrib['lib'] + ':' + source.attrib['part'],
            'footprint': item.findtext('footprint') or None,
        })
    nets = [{'name': item.attrib['name'],
             'nodes': [{'ref': aliases.get(node.attrib['ref'], node.attrib['ref']), 'pin': node.attrib['pin']}
                       for node in item.findall('node')]}
            for item in document.findall('./nets/net') if item.findall('node')]
    return Circuit.model_validate({'components': components, 'nets': nets})


def graph_signature(circuit):
    return {
        'components': sorted((c.ref, c.value, c.library, c.footprint)
                             for c in circuit.components),
        'nets': sorted((net.name, sorted((p.ref, p.pin) for p in net.nodes))
                       for net in circuit.nets),
    }


def run_export(cli, arguments):
    result = subprocess.run([str(cli), 'sch', 'export', *arguments],
                            capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise ValueError('KiCad export failed: ' + result.stderr[-1500:])


def prepare(source, output, cli, license_file, source_url):
    import pymupdf as fitz
    source, output = source.resolve(), output.resolve()
    if output.exists():
        raise ValueError('Output already exists; use a fresh candidate directory.')
    if output.is_relative_to(source):
        raise ValueError('Keep generated candidates outside the source library.')
    if not license_file.is_file():
        raise ValueError('An explicit source license file is required.')
    files = sorted(source.rglob('*.kicad_sch'))
    parsed = {path: parse_native(path.read_text(encoding='utf-8-sig')) for path in files}
    child_files = set()
    for path, tree in parsed.items():
        for sheet in children(tree, 'sheet'):
            for prop in children(sheet, 'property'):
                if len(prop) > 2 and prop[1] == 'Sheetfile':
                    child_files.add((path.parent / prop[2]).resolve())
    output.mkdir(parents=True)
    shutil.copyfile(license_file, output / 'SOURCE-LICENSE.txt')
    version = subprocess.check_output([str(cli), 'version'], text=True).strip()
    records, rejected = [], []
    for path, tree in parsed.items():
        relative = path.relative_to(source).as_posix()
        try:
            if children(tree, 'sheet') or path.resolve() in child_files:
                raise ValueError('Hierarchical root/child sheet needs page-specific targets.')
            original_hash = digest(path)
            sample_id = hashlib.sha256((relative + original_hash).encode()).hexdigest()[:20]
            folder = output / sample_id
            folder.mkdir()
            native = folder / 'source.kicad_sch'
            shutil.copyfile(path, native)
            xml = folder / 'netlist.xml'
            run_export(cli, ['netlist', '--format', 'kicadxml', '-o', str(xml), str(native)])
            run_export(cli, ['svg', '--black-and-white', '--exclude-drawing-sheet',
                             '-o', str(folder), str(native)])
            svgs = list(folder.glob('*.svg'))
            if len(svgs) != 1:
                raise ValueError('Expected one page image for one netlist.')
            circuit = circuit_from_xml(xml)
            # The serialized target must retain every exported reference and pin.
            target = circuit.model_dump()
            if graph_signature(Circuit.model_validate(target)) != graph_signature(circuit_from_xml(xml)):
                raise ValueError('Serialized target differs from the native XML graph.')
            image = folder / 'image.png'
            with fitz.open(svgs[0]) as document:
                if len(document) != 1:
                    raise ValueError('Expected a single SVG page.')
                page = document[0]
                scale = min(4500 / max(page.rect.width, page.rect.height),
                            math.sqrt(15_500_000 / (page.rect.width * page.rect.height)))
                pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                pixmap.save(image)
                width, height = pixmap.width, pixmap.height
            if original_hash != digest(path) or original_hash != digest(native):
                raise ValueError('Native source changed during export.')
            # Families remain together when these candidates are later split.
            group = 'seeed-xiao-family' if 'xiao' in relative.lower() else path.parent.name
            record = {
                'sample_id': 'native-' + sample_id, 'source': source_url,
                'source_file': relative, 'source_sha256': original_hash,
                'source_license': 'SOURCE-LICENSE.txt', 'kicad_version': version,
                'source_reference_aliases': {
                    item.attrib['ref']: item.attrib['ref'].upper()
                    for item in ET.parse(xml).getroot().findall('./components/comp')
                    if item.attrib['ref'] != item.attrib['ref'].upper()},
                'group': group, 'image': image.relative_to(output).as_posix(),
                'image_sha256': digest(image), 'image_dimensions': [width, height],
                'native_netlist': xml.relative_to(output).as_posix(),
                'native_netlist_sha256': digest(xml), 'circuit': target,
                'netlist_equivalence_verified': True, 'image_source_review': 'required',
                'image_origin': 'native_export_of_real_design', 'synthetic': False, 'ai_generated': False,
                'review_reason': 'Check text legibility, hidden fields/pins and image-to-target scope. '
                                 'Native export does not establish visual recognizability.',
            }
            (folder / 'candidate.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
            records.append(record)
        except (ValueError, OSError, ET.ParseError, subprocess.SubprocessError) as exc:
            rejected.append({'source_file': relative, 'reason': str(exc)})
    (output / 'candidates.jsonl').write_text(
        ''.join(json.dumps(record) + '\n' for record in records), encoding='utf-8')
    report = {
        'source': source_url, 'source_files': len(files), 'candidate_pairs': len(records),
        'components': sum(len(r['circuit']['components']) for r in records),
        'physical_pins': sum(len(n['nodes']) for r in records for n in r['circuit']['nets']),
        'groups': len({r['group'] for r in records}), 'rejected': rejected,
        'custom_training_ready': False, 'model_training_started': False,
        'note': 'Review candidates only. No training splits or verified visual-review flags were created.',
    }
    (output / 'audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (output / 'README.txt').write_text(
        'Source: ' + source_url + '\nLicense: see SOURCE-LICENSE.txt. Preserve attribution.\n'
        'These are native-export review candidates, not an approved training dataset.\n'
        'Review each image against its candidate.json and XML physical pin connections.\n'
        'Keep board-family variants together in later train/validation/test splits.\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--kicad-cli', type=Path, required=True)
    parser.add_argument('--license-file', type=Path, required=True)
    parser.add_argument('--source-url', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output, args.kicad_cli,
                             args.license_file, args.source_url), indent=2))
