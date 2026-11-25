#!/usr/bin/env python3
"""index.html 의 SEED 에서 '기사·뉴스레터' 카드를 뽑아 news.json 을 만든다.

아이폰 홈 화면의 Scriptable 위젯 'TAPO 읽기'(downloads/tapo_reading_widget.js)가
읽어 가는 정적 JSON 이다. 위젯은 이 파일 하나로
    · 판례(kind: "판례") 100선 중 '읽기 전' 하나를 골라 '오늘의 판례'로,
    · 가장 최근 영문 칼럼(kind: "Eng") 1편을 '오늘의 Eng 칼럼'으로,
    · 가장 최근 기사(kind: "기사") 2~3건을 '주요 기사'로
띄운다. GIST_ID·GIST_TOKEN 을 채우면 웹앱 Gist(tapo-archive-sync.json)의
status·deleted 를 함께 읽어, 이미 '읽음'으로 바꾼 판례는 다시 뽑지 않는다.

아침 루틴(my-day-preparation)이 새 기사·영문 칼럼을 SEED 에 넣은 뒤
    python3 scripts/build_news.py
를 실행하면 news.json 이 같은 내용으로 다시 만들어진다.

2026-11-25 — 아카이브(SEED)는 공부·기록용으로 두고, 초초이슈·화제 속보는
`hot_issues.json`(배열)에만 적는다. 이 파일이 있으면 그 항목들을 '기사'로
합쳐(날짜 최신순, ARTICLES_MAX 안에서) news.json 에만 싣는다 — 웹 탭에는
안 보이고 아이폰 'TAPO 읽기' 위젯에만 뜬다.

사용: python3 scripts/build_news.py [--check]
  --check : 파일을 쓰지 않고 만들어질 JSON 을 화면에만 보여 준다.
"""
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
OUT = ROOT / "news.json"
HOT = ROOT / "hot_issues.json"   # 웹 아카이브에 넣지 않는 화제·속보 (위젯 전용)

KST = timezone(timedelta(hours=9))

CAT = "news"            # 기사·뉴스레터 탭
KIND_CASE = "판례"
KIND_ENG = "Eng"
KIND_ARTICLE = "기사"
ARTICLES_MAX = 5        # 위젯은 이 중 앞 2~3건을 보여 준다
ENG_MAX = 3             # 위젯은 맨 앞 1건을 보여 준다


def strip_tags(s) -> str:
    s = str(s if s is not None else "")
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    # 요약은 줄바꿈(• 요지 …)을 살리되 줄 앞뒤 공백만 정리한다
    return "\n".join(line.strip() for line in s.split("\n")).strip()


def parse_seed(src: str) -> list:
    """`var SEED = [ … ];` 를 JSON 으로 읽는다 (base64 이미지가 들어 있어도 그대로)."""
    i = src.find("var SEED = ")
    if i < 0:
        return []
    start = src.find("[", i)
    try:
        data, _ = json.JSONDecoder().raw_decode(src[start:])
    except json.JSONDecodeError as e:
        print(f"SEED 를 읽지 못했습니다: {e}", file=sys.stderr)
        return []
    return data if isinstance(data, list) else []


def row(it: dict) -> dict:
    """위젯이 쓰는 필드만 남긴다 — 제목·언론사·날짜·주제태그·요약·원문·상태."""
    return {
        "id": str(it.get("id") or ""),
        "title": strip_tags(it.get("title")),
        "publisher": strip_tags(it.get("publisher")),
        "date": str(it.get("date") or ""),
        "sub": strip_tags(it.get("sub")),
        "summary": strip_tags(it.get("summary") or it.get("body")),
        "url": str(it.get("url") or ""),
        "status": strip_tags(it.get("status")),
    }


def load_hot() -> list:
    """hot_issues.json — 아직 SEED 에 넣지 않는 화제·속보를 읽는다 (없거나 깨졌으면 빈 목록).

    형식: [{"id", "title", "publisher", "date", "sub", "summary", "url", "status"}]
    """
    if not HOT.exists():
        return []
    try:
        data = json.loads(HOT.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"hot_issues.json 을 읽지 못했습니다: {e}", file=sys.stderr)
        return []
    if not isinstance(data, list):
        return []
    return [it for it in data if isinstance(it, dict) and str(it.get("id") or "").strip() and str(it.get("title") or "").strip()]


def sort_recent(items: list) -> list:
    """날짜가 늦은 것이 앞. 같은 날짜는 SEED 에 넣은 차례 그대로 (sorted 는 안정 정렬)."""
    def key(it):
        d = str(it.get("date") or "")
        return d if re.match(r"^\d{4}-\d{2}-\d{2}$", d) else "0000-00-00"
    return sorted(items, key=key, reverse=True)


def main() -> int:
    src = INDEX.read_text(encoding="utf-8")
    seed = [it for it in parse_seed(src) if isinstance(it, dict)]

    news = [it for it in seed if it.get("cat") == CAT]
    cases = [row(it) for it in news if it.get("kind") == KIND_CASE]
    eng = [row(it) for it in news if it.get("kind") == KIND_ENG]
    articles = [row(it) for it in news if it.get("kind") == KIND_ARTICLE]
    hot = [row(it) for it in load_hot()]   # 화제·속보 — 위젯에만

    eng = sort_recent(eng)[:ENG_MAX]
    # 2026-11-25 — SEED 기사 + hot_issues.json 을 합친다(같은 id 는 SEED 쪽 하나만).
    merged, seen = [], set()
    for a in articles + hot:
        if a["id"] and a["id"] in seen:
            continue
        seen.add(a["id"])
        merged.append(a)
    articles = sort_recent(merged)[:ARTICLES_MAX]

    now = datetime.now(KST)
    data = {
        "v": 1,
        "date": now.strftime("%Y-%m-%d"),
        "updatedAt": now.isoformat(timespec="seconds"),
        "counts": {
            "cases": len(cases),
            "casesUnread": sum(1 for c in cases if c["status"] == "읽기 전"),
            "eng": len(eng),
            "articles": len(articles),
        },
        "cases": cases,
        "eng": eng,
        "articles": articles,
    }
    out = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if "--check" in sys.argv:
        sys.stdout.write(out)
        return 0
    OUT.write_text(out, encoding="utf-8")
    print(f"news.json · 판례 {len(cases)}건(읽기 전 {data['counts']['casesUnread']})"
          f" · Eng {len(eng)}건 · 기사 {len(articles)}건")
    if eng:
        print(f"  Eng    {eng[0]['date']} {eng[0]['title'][:60]}")
    for a in articles[:3]:
        print(f"  기사   {a['date']} {a['publisher']} · {a['title'][:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
