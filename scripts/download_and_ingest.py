"""Download official AIT/OTRF/OpTC releases and ingest telemetry via normalize().

OpTC eCAR/bro payloads (~1TB on Google Drive) are inventoried but not fetched.
Labels/ground-truth paths are never passed to normalize().
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'datasets' / 'raw'
INGESTED = ROOT / 'datasets' / 'ingested'
INVENTORY = ROOT / 'datasets' / 'inventory.json'

sys.path.insert(0, str(ROOT / 'src'))
from beyond_retrieval.data import normalize, save_events  # noqa: E402

AIT_RECORD = 'https://zenodo.org/api/records/19483937'
AIT_ENVS = [
    'fox', 'harrison', 'russellmitchell', 'santos',
    'shaw', 'wardbeck', 'wheeler', 'wilson',
]
AIT_VERSION = 'v2.1'
AIT_LICENSE = 'CC-BY-NC-SA-4.0'
AIT_URL = 'https://doi.org/10.5281/zenodo.19483937'

OTRF_RAW_BASE = 'https://raw.githubusercontent.com/OTRF/Security-Datasets/master/datasets'
OTRF_VERSION = 'master'
OTRF_LICENSE = 'GPL-3.0'
OTRF_URL = 'https://github.com/OTRF/Security-Datasets'

OPTC_FILES = [
    'README.md',
    'ecar.md',
    'errata.md',
    'OpTCRedTeamGroundTruth.pdf',
]
OPTC_VERSION = 'master'
OPTC_LICENSE = 'public-domain-US-gov'
OPTC_REPO = 'https://github.com/FiveDirections/OpTC-data'
OPTC_DATA_DRIVE = 'https://drive.google.com/drive/folders/1n3kkS3KR31KUegn42yk3-e6JkZvf0Caa'

# Auth/security-oriented AIT gather logs; skip labels and oversized hosts.
AIT_NAME_ALLOW = {
    'auth.log', 'secure', 'audit.log', 'syslog', 'messages',
    'access.log', 'error.log', 'mail.log', 'exim_mainlog', 'vpn.log',
}
AIT_MAX_BYTES = 80 * 1024 * 1024  # per-file ingest cap
OTRF_MAX_BYTES = 80 * 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, expected_size: int | None = None) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        if expected_size is None or dest.stat().st_size == expected_size:
            return {'path': str(dest), 'status': 'cached', 'bytes': dest.stat().st_size,
                    'sha256': sha256_file(dest)}
    tmp = dest.with_suffix(dest.suffix + '.part')
    print(f'DOWNLOAD {url}\n  -> {dest}', flush=True)
    req = urllib.request.Request(url, headers={'User-Agent': 'beyond-retrieval-ingest/0.2'})
    with urllib.request.urlopen(req, timeout=600) as resp, tmp.open('wb') as out:
        total = resp.length or expected_size
        done = 0
        last = time.time()
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            now = time.time()
            if now - last >= 5:
                pct = f'{100*done/total:.1f}%' if total else '?'
                print(f'  {done/1e6:.1f} MB ({pct})', flush=True)
                last = now
    tmp.replace(dest)
    meta = {'path': str(dest), 'status': 'downloaded', 'bytes': dest.stat().st_size,
            'sha256': sha256_file(dest), 'url': url}
    print(f'  done {meta["bytes"]/1e6:.1f} MB sha256={meta["sha256"][:12]}…', flush=True)
    return meta


def extract_zip(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    marker = dest / '.extracted'
    if marker.exists():
        return
    print(f'EXTRACT {archive.name} -> {dest}', flush=True)
    # Prefer tar/libarchive for large archives on Windows.
    try:
        subprocess.run(['tar', '-xf', str(archive), '-C', str(dest)], check=True)
    except Exception:
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
    marker.write_text(archive.name + '\n')


def ait_files_from_zenodo() -> list[dict]:
    with urllib.request.urlopen(AIT_RECORD, timeout=60) as resp:
        record = json.load(resp)
    wanted = {f'{env}_no-pcaps.zip' for env in AIT_ENVS}
    files = [f for f in record['files'] if f['key'] in wanted]
    missing = wanted - {f['key'] for f in files}
    if missing:
        raise SystemExit(f'Missing AIT files on Zenodo: {sorted(missing)}')
    return files


def download_ait(report: dict) -> None:
    report['ait'] = {'version': AIT_VERSION, 'license': AIT_LICENSE, 'url': AIT_URL, 'archives': [], 'sources': []}
    for f in ait_files_from_zenodo():
        key = f['key']
        env = key.replace('_no-pcaps.zip', '')
        url = f['links']['self']
        dest = RAW / 'ait' / key
        meta = download(url, dest, expected_size=f['size'])
        meta.update({'environment': env, 'zenodo_md5': f.get('checksum'), 'key': key})
        report['ait']['archives'].append(meta)
        out_dir = RAW / 'ait' / env
        extract_zip(dest, out_dir)


def discover_otrf_zips() -> list[str]:
    """List atomic host + compound host JSON zips (skip pcap/zeek sidecars)."""
    paths = []
    for tree_sha, prefix in [
        ('2614d45ae5ca8061bbea6319a953afdfadadbf85', 'atomic'),
        ('54c38ef0c591d06e473cde783945d29afbf871d7', 'compound'),
    ]:
        url = f'https://api.github.com/repos/OTRF/Security-Datasets/git/trees/{tree_sha}?recursive=1'
        req = urllib.request.Request(url, headers={'User-Agent': 'beyond-retrieval-ingest/0.2',
                                                   'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            tree = json.load(resp)['tree']
        for t in tree:
            p = t['path']
            if not p.endswith('.zip'):
                continue
            low = p.lower()
            if any(x in low for x in ('pcap', 'zeek', '/network/')):
                continue
            if prefix == 'atomic' and '/host/' not in p.replace('\\', '/'):
                continue
            paths.append(f'{prefix}/{p}')
    return sorted(set(paths))


def download_otrf(report: dict) -> None:
    report['otrf'] = {'version': OTRF_VERSION, 'license': OTRF_LICENSE, 'url': OTRF_URL,
                      'archives': [], 'sources': []}
    zips = discover_otrf_zips()
    print(f'OTRF candidate zips: {len(zips)}', flush=True)
    for rel in zips:
        url = f'{OTRF_RAW_BASE}/{rel}'
        dest = RAW / 'otrf' / rel
        try:
            meta = download(url, dest)
        except urllib.error.HTTPError as e:
            report['otrf']['archives'].append({'path': rel, 'status': 'failed', 'error': str(e)})
            print(f'  FAIL {rel}: {e}', flush=True)
            continue
        meta['rel'] = rel
        report['otrf']['archives'].append(meta)
        extract_dir = dest.with_suffix('')
        extract_zip(dest, extract_dir)


def download_optc(report: dict) -> None:
    report['optc'] = {
        'version': OPTC_VERSION, 'license': OPTC_LICENSE, 'url': OPTC_REPO,
        'data_url': OPTC_DATA_DRIVE,
        'status': 'docs_only',
        'reason': 'Full eCAR/bro release is ~1TB on Google Drive; not auto-downloaded.',
        'docs': [], 'sources': [],
    }
    for name in OPTC_FILES:
        url = f'https://raw.githubusercontent.com/FiveDirections/OpTC-data/master/{name}'
        dest = RAW / 'optc' / name
        try:
            meta = download(url, dest)
            meta['name'] = name
            report['optc']['docs'].append(meta)
        except urllib.error.HTTPError as e:
            report['optc']['docs'].append({'name': name, 'status': 'failed', 'error': str(e)})


def safe_source_id(*parts: str) -> str:
    text = '__'.join(parts)
    cleaned = ''.join(c if c.isalnum() or c in '-_.' else '_' for c in text)
    return cleaned[:180]


def ingest_ait(report: dict) -> None:
    sources = []
    for env in AIT_ENVS:
        root = RAW / 'ait' / env
        if not root.exists():
            continue
        for path in root.rglob('*'):
            if not path.is_file():
                continue
            parts = {p.lower() for p in path.parts}
            if 'labels' in parts or 'ground_truth' in parts or 'groundtruth' in parts:
                continue
            if 'gather' not in parts:
                continue
            name = path.name.lower()
            allowed = name in AIT_NAME_ALLOW or any(
                name == key or name.startswith(key + '.') for key in AIT_NAME_ALLOW
            )
            if not allowed:
                continue
            size = path.stat().st_size
            rel = str(path.relative_to(root)).replace('\\', '/')
            host = 'unknown'
            if 'gather' in path.parts:
                i = path.parts.index('gather')
                if i + 1 < len(path.parts):
                    host = path.parts[i + 1]
            source = safe_source_id(env, host, path.name)
            out = INGESTED / 'ait' / env / f'{source}.jsonl'
            entry = {
                'id': source, 'dataset': 'ait', 'environment': env, 'version': AIT_VERSION,
                'license': AIT_LICENSE, 'url': AIT_URL, 'path': str(path),
                'relative': rel, 'bytes': size, 'sha256': sha256_file(path),
            }
            if size == 0:
                entry['ingest'] = 'skipped_empty'
            elif size > AIT_MAX_BYTES:
                entry['ingest'] = 'skipped_too_large'
            else:
                print(f'INGEST ait/{env} {rel} ({size/1e6:.2f} MB)', flush=True)
                rows = normalize(path, 'ait', env, source)
                save_events(out, rows)
                entry.update({
                    'ingest': 'ok', 'events': len(rows), 'output': str(out),
                    'evidence_sha256_note': 'origin.sha256 is raw file digest embedded per row',
                })
            sources.append(entry)
    report['ait']['sources'] = sources


def ingest_otrf(report: dict) -> None:
    sources = []
    root = RAW / 'otrf'
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {'.json', '.jsonl'}:
            continue
        if path.name.startswith('.'):
            continue
        parts_l = [p.lower() for p in path.parts]
        if any(x in parts_l for x in ('labels', 'ground_truth', 'groundtruth', 'answers')):
            continue
        size = path.stat().st_size
        rel = str(path.relative_to(root)).replace('\\', '/')
        # environment = technique folder stem / campaign name
        env = path.parent.name
        source = safe_source_id('otrf', *Path(rel).with_suffix('').parts[-4:])
        out = INGESTED / 'otrf' / f'{source}.jsonl'
        entry = {
            'id': source, 'dataset': 'otrf', 'environment': env, 'version': OTRF_VERSION,
            'license': OTRF_LICENSE, 'url': OTRF_URL, 'path': str(path),
            'relative': rel, 'bytes': size, 'sha256': sha256_file(path),
        }
        if size == 0:
            entry['ingest'] = 'skipped_empty'
        elif size > OTRF_MAX_BYTES:
            entry['ingest'] = 'skipped_too_large'
        else:
            print(f'INGEST otrf {rel} ({size/1e6:.2f} MB)', flush=True)
            # OTRF host captures are JSON arrays or JSONL depending on export.
            blob = path.read_bytes().lstrip()
            json_array = blob.startswith(b'[')
            rows = normalize(path, 'otrf', env, source, json_array=json_array)
            save_events(out, rows)
            entry.update({'ingest': 'ok', 'events': len(rows), 'output': str(out),
                          'json_array': json_array})
        sources.append(entry)
    report['otrf']['sources'] = sources


def summarize(report: dict) -> None:
    for name in ('ait', 'otrf', 'optc'):
        block = report.get(name, {})
        src = block.get('sources', [])
        ok = [s for s in src if s.get('ingest') == 'ok']
        events = sum(s.get('events', 0) for s in ok)
        print(f'{name}: archives/docs={len(block.get("archives", block.get("docs", [])))} '
              f'ingested_files={len(ok)} events={events} status={block.get("status", "ok")}',
              flush=True)


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    INGESTED.mkdir(parents=True, exist_ok=True)
    report = {'generated_by': 'scripts/download_and_ingest.py'}
    download_ait(report)
    download_otrf(report)
    download_optc(report)
    ingest_ait(report)
    ingest_otrf(report)
    INVENTORY.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    summarize(report)
    print(f'Inventory: {INVENTORY}', flush=True)


if __name__ == '__main__':
    main()
