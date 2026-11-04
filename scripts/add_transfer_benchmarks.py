"""Stage DiscoveryBench, DiscoveryWorld, and ScienceAgentBench for transfer evals.

These are external scientific-discovery benchmarks (not AIT/OTRF/OpTC telemetry).
ScienceAgentBench full eval artifacts remain password-gated on SharePoint; this
script stores the Hugging Face annotation sheet (agent inputs) plus the GitHub code.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'datasets' / 'raw'
INGESTED = ROOT / 'datasets' / 'ingested'
CATALOG = ROOT / 'datasets' / 'transfer_benchmarks.json'
INVENTORY = ROOT / 'datasets' / 'inventory.json'

BENCHMARKS = [
    {
        'id': 'discoverybench',
        'name': 'DiscoveryBench',
        'purpose': (
            'Test whether hypothesis graphs and validated scripts improve discovery '
            'from supplied datasets.'
        ),
        'url': 'https://github.com/allenai/discoverybench',
        'hf': 'allenai/discoverybench',
        'license': 'see-upstream',
        'zip_url': 'https://github.com/allenai/discoverybench/archive/refs/heads/main.zip',
        'default_branch': 'main',
    },
    {
        'id': 'discoveryworld',
        'name': 'DiscoveryWorld',
        'purpose': (
            'Test whether those methods improve selection of informative experiments.'
        ),
        'url': 'https://github.com/allenai/discoveryworld',
        'hf': None,
        'license': 'Apache-2.0',
        'zip_url': 'https://github.com/allenai/discoveryworld/archive/refs/heads/main.zip',
        'default_branch': 'main',
        'notes': (
            'Environment is code-defined (120 tasks). Large baseline/human trajectory '
            'releases live on Google Drive linked from the upstream data/ docs.'
        ),
    },
    {
        'id': 'scienceagentbench',
        'name': 'ScienceAgentBench',
        'purpose': 'Test transfer to practical scientific coding tasks.',
        'url': 'https://github.com/OSU-NLP-Group/ScienceAgentBench',
        'hf': 'osunlp/ScienceAgentBench',
        'license': 'CC-BY-4.0 tasks / MIT code (see upstream)',
        'zip_url': 'https://github.com/OSU-NLP-Group/ScienceAgentBench/archive/refs/heads/main.zip',
        'default_branch': 'main',
        'notes': (
            'HF sheet provides agent inputs. Full gold/eval programs require '
            'benchmark_verified.zip from SharePoint (password: scienceagentbench); '
            'do not redistribute unzipped eval files.'
        ),
        'full_artifacts_url': (
            'https://buckeyemailosu-my.sharepoint.com/:u:/g/personal/chen_8336_osu_edu/'
            'IQB870QrmuqwS5Ck33cHpJfkAVt3LsMeariREIwP3AT7byA?e=3ckueC'
        ),
    },
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return {'path': str(dest), 'status': 'cached', 'bytes': dest.stat().st_size,
                'sha256': sha256_file(dest), 'url': url}
    tmp = dest.with_suffix(dest.suffix + '.part')
    print(f'DOWNLOAD {url}\n  -> {dest}', flush=True)
    req = urllib.request.Request(url, headers={'User-Agent': 'beyond-retrieval-ingest/0.2'})
    with urllib.request.urlopen(req, timeout=600) as resp, tmp.open('wb') as out:
        total = resp.length
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
                pct = f'{100 * done / total:.1f}%' if total else '?'
                print(f'  {done / 1e6:.1f} MB ({pct})', flush=True)
                last = now
    tmp.replace(dest)
    meta = {'path': str(dest), 'status': 'downloaded', 'bytes': dest.stat().st_size,
            'sha256': sha256_file(dest), 'url': url}
    print(f'  done {meta["bytes"] / 1e6:.1f} MB sha256={meta["sha256"][:12]}…', flush=True)
    return meta


def extract_zip(archive: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    marker = dest / '.extracted'
    if marker.exists():
        kids = [p for p in dest.iterdir() if p.is_dir() and not p.name.startswith('.')]
        return kids[0] if kids else dest
    print(f'EXTRACT {archive.name} -> {dest}', flush=True)
    try:
        subprocess.run(['tar', '-xf', str(archive), '-C', str(dest)], check=True)
    except Exception:
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
    marker.write_text(archive.name + '\n')
    kids = [p for p in dest.iterdir() if p.is_dir() and not p.name.startswith('.')]
    return kids[0] if kids else dest


def export_hf(dataset_id: str, out_dir: Path) -> dict:
    """Download public Hugging Face dataset files via the Hub REST API."""
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f'HF EXPORT {dataset_id} -> {out_dir}', flush=True)
    api = f'https://huggingface.co/api/datasets/{dataset_id}'
    try:
        with urllib.request.urlopen(
            urllib.request.Request(api, headers={'User-Agent': 'beyond-retrieval-ingest/0.2'}),
            timeout=60,
        ) as resp:
            meta = json.load(resp)
    except Exception as e:
        return {'status': 'failed', 'error': f'api: {e}'}
    files_meta = []
    for sib in meta.get('siblings', []):
        name = sib.get('rfilename')
        if not name or name in {'.gitattributes'} or name.endswith('.md'):
            continue
        url = f'https://huggingface.co/datasets/{dataset_id}/resolve/main/{name}'
        dest = out_dir / name.replace('/', '__')
        try:
            files_meta.append(download(url, dest))
        except Exception as e:
            files_meta.append({'path': name, 'status': 'failed', 'error': str(e)})
    ok = [f for f in files_meta if f.get('status') in {'downloaded', 'cached'}]
    return {
        'status': 'ok' if ok else 'failed',
        'dataset': dataset_id,
        'method': 'huggingface_resolve',
        'sha': meta.get('sha'),
        'files': files_meta,
    }


def count_tree(path: Path) -> dict:
    files = [p for p in path.rglob('*') if p.is_file()]
    return {
        'files': len(files),
        'bytes': sum(p.stat().st_size for p in files),
    }


def stage_one(spec: dict) -> dict:
    bid = spec['id']
    raw_dir = RAW / bid
    ingested_dir = INGESTED / bid
    raw_dir.mkdir(parents=True, exist_ok=True)
    ingested_dir.mkdir(parents=True, exist_ok=True)

    archive = raw_dir / f'{bid}-{spec["default_branch"]}.zip'
    archive_meta = download(spec['zip_url'], archive)
    extracted = extract_zip(archive, raw_dir / 'repo')

    # Copy task/data-looking trees into ingested for a stable local view.
    copied = []
    for name in ('discoverybench', 'answer_key', 'data', 'benchmark', 'datasets', 'tasks'):
        src = extracted / name
        if src.exists():
            dst = ingested_dir / name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            copied.append(name)

    entry = {
        'id': bid,
        'name': spec['name'],
        'purpose': spec['purpose'],
        'url': spec['url'],
        'license': spec['license'],
        'archive': archive_meta,
        'extracted_root': str(extracted),
        'copied_subtrees': copied,
        'repo_stats': count_tree(extracted),
        'notes': spec.get('notes'),
        'full_artifacts_url': spec.get('full_artifacts_url'),
        'hf': None,
    }
    if spec.get('hf'):
        entry['hf'] = export_hf(spec['hf'], ingested_dir / 'huggingface')
    entry['ingested_stats'] = count_tree(ingested_dir)
    return entry


def main() -> None:
    catalog = {
        'description': (
            'External transfer benchmarks for beyond-retrieval methods '
            '(hypothesis graphs, validated scripts, scientific coding transfer).'
        ),
        'benchmarks': [],
    }
    for spec in BENCHMARKS:
        catalog['benchmarks'].append(stage_one(spec))
    CATALOG.write_text(json.dumps(catalog, indent=2) + '\n', encoding='utf-8')

    if INVENTORY.exists():
        inv = json.loads(INVENTORY.read_text(encoding='utf-8'))
    else:
        inv = {}
    inv['transfer_benchmarks'] = catalog
    INVENTORY.write_text(json.dumps(inv, indent=2) + '\n', encoding='utf-8')

    for b in catalog['benchmarks']:
        hf = b.get('hf') or {}
        rows = sum(s.get('rows', 0) for s in (hf.get('splits') or {}).values())
        print(
            f"{b['id']}: repo_files={b['repo_stats']['files']} "
            f"ingested_files={b['ingested_stats']['files']} hf_rows={rows}",
            flush=True,
        )
    print(f'Catalog: {CATALOG}', flush=True)


if __name__ == '__main__':
    main()
