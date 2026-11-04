"""Extract tables and captions from the Beyond Retrieval paper PDF."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pdfplumber

PDF = Path(r'C:\Users\monik\Downloads\Beyond_Retrieval_Open_Dataset_Experiments (1).pdf')
OUT = Path(__file__).resolve().parents[1] / 'datasets' / 'paper_tables.json'


def main() -> None:
    pages_text = []
    tables = []
    with pdfplumber.open(PDF) as pdf:
        print('pages', len(pdf.pages))
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ''
            pages_text.append({'page': i, 'text': text})
            captions = re.findall(r'(Table\s+\d+[^\n]*)', text)
            extracted = page.extract_tables() or []
            print(f'page {i}: tables={len(extracted)} captions={captions}')
            for ti, tbl in enumerate(extracted):
                tables.append({
                    'page': i,
                    'index': ti,
                    'captions_on_page': captions,
                    'rows': tbl,
                })

    mentions = []
    for p in pages_text:
        for m in re.finditer(r'Table\s+\d+[\s\S]{0,240}', p['text']):
            mentions.append({'page': p['page'], 'snippet': m.group(0).replace('\n', ' ')})

    payload = {
        'source': str(PDF),
        'page_count': len(pages_text),
        'table_mentions': mentions,
        'tables': tables,
        'full_text': '\n\n'.join(
            f'===== PAGE {p["page"]} =====\n{p["text"]}' for p in pages_text
        ),
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    print('wrote', OUT, 'tables', len(tables), 'mentions', len(mentions))


if __name__ == '__main__':
    main()
