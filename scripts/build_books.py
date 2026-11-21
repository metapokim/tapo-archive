#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TAPO's archive — index.html 의 SEED 에서 책 목록만 뽑아 books.json 으로 저장한다.

아이폰 Scriptable '오늘 뭐 읽지?' 위젯이 1.2MB index.html 대신 이 작은 파일을 받아
미독 책을 뽑는다. (위젯은 Gist 의 ov·items·deleted 를 얹어 지금 상태를 맞춘다.)

    python3 scripts/build_books.py

SEED 의 책을 고치거나 새 책을 넣은 뒤 한 번 돌려 주면 위젯 쪽 기본 목록도 최신이 된다.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INDEX = os.path.join(ROOT, 'index.html')
OUT = os.path.join(ROOT, 'books.json')

FIELDS = ('id', 'title', 'author', 'publisher', 'image', 'status', 'own')


def extract_seed(html):
    m = re.search(r'var\s+SEED\s*=\s*\[', html)
    if not m:
        raise SystemExit('index.html 에서 var SEED = [ 를 찾지 못했습니다')
    start = html.index('[', m.start())
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(html)):
        ch = html[i]
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                return json.loads(html[start:i + 1])
    raise SystemExit('SEED 배열의 끝을 찾지 못했습니다')


def main():
    with open(INDEX, encoding='utf-8') as f:
        html = f.read()
    seed = extract_seed(html)
    books = []
    for it in seed:
        if it.get('cat') != 'book':
            continue
        row = {}
        for k in FIELDS:
            v = it.get(k)
            if v is None or v == '':
                continue
            row[k] = v
        if row.get('id') and row.get('title'):
            books.append(row)
    payload = {
        'app': 'tapo-archive-books',
        'v': 1,
        'generated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'count': len(books),
        'books': books,
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    unread = sum(1 for b in books if b.get('status') == '미독' and b.get('own') != '대여')
    print('%s · 책 %d권 (미독 %d권) · %.0fKB' % (OUT, len(books), unread, os.path.getsize(OUT) / 1024))


if __name__ == '__main__':
    main()
