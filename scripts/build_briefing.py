#!/usr/bin/env python3
"""index.html 의 아침 브리핑 영역을 읽어 briefing.json 을 만든다.

아이폰 홈 화면의 Scriptable 위젯이 읽어 가는 정적 JSON 이다.
아침 루틴(my-day-preparation)이 MORNING_BRIEF_START~END 를 갈아끼운 뒤
    python3 scripts/build_briefing.py
를 실행하면 briefing.json 이 같은 내용으로 다시 만들어진다.

사용: python3 scripts/build_briefing.py [--check]
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
OUT = ROOT / "briefing.json"

KST = timezone(timedelta(hours=9))
WEEKDAY = "월화수목금토일"

START = "<!-- MORNING_BRIEF_START -->"
END = "<!-- MORNING_BRIEF_END -->"


def strip_tags(s: str) -> str:
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def attr(html_text: str, name: str, default: str = "") -> str:
    m = re.search(name + r"\s*=\s*(['\"])(.*?)\1", html_text, re.S)
    return html.unescape(m.group(2)) if m else default


def inner_text(fragment: str) -> str:
    return strip_tags(fragment)


def parse_brief(src: str) -> dict:
    i = src.find(START)
    j = src.find(END)
    if i < 0 or j < 0 or j < i:
        raise SystemExit("MORNING_BRIEF 마커를 찾지 못했습니다.")
    block = src[i + len(START):j]

    m = re.search(r"<section[^>]*class=\"brief\"[^>]*>", block, re.S)
    if not m:
        raise SystemExit(".brief 섹션을 찾지 못했습니다.")
    section_tag = m.group(0)

    # 날짜 — <time class="brief-when" datetime="YYYY-MM-DD">11월 18일 수요일</time>
    tm = re.search(r"<time[^>]*class=\"brief-when\"[^>]*>(.*?)</time>", block, re.S)
    dt = re.search(r"<time[^>]*datetime=\"(\d{4}-\d{2}-\d{2})\"", block, re.S)
    date = dt.group(1) if dt else ""
    when_full = inner_text(tm.group(1)) if tm else ""
    if not date:
        raise SystemExit("brief-when 의 datetime 이 없습니다.")
    d = datetime.strptime(date, "%Y-%m-%d")
    when = f"{d.month}월 {d.day}일 {WEEKDAY[d.weekday()]}"

    # 날씨 2일치
    raw_days = attr(section_tag, "data-weather-days", "") or attr(block, "data-weather-days", "")
    weather_days = {}
    if raw_days:
        try:
            parsed = json.loads(raw_days)
            for k, v in parsed.items():
                if re.match(r"^\d{4}-\d{2}-\d{2}$", str(k)):
                    weather_days[str(k)] = strip_tags(str(v))
        except json.JSONDecodeError:
            weather_days = {}

    # 오늘 날씨 문구 — data-weather-days 의 오늘(없으면 가장 이른 날) 것을 쓴다
    weather_text = weather_days.get(date, "")
    if not weather_text and weather_days:
        weather_text = weather_days[sorted(weather_days)[0]]

    # 강조어 — 오늘 문구의 <b> 안에 있던 말들
    highlights = []
    if raw_days:
        try:
            parsed = json.loads(raw_days)
            today_raw = str(parsed.get(date, ""))
            for h in re.findall(r"<b>(.*?)</b>", today_raw, re.S):
                h = strip_tags(h)
                if h and h not in highlights:
                    highlights.append(h)
        except json.JSONDecodeError:
            pass

    # 조언 한 줄
    lead = ""
    lm = re.search(r"<p[^>]*class=\"brief-lead\"[^>]*>(.*?)</p>", block, re.S)
    if lm:
        lead = inner_text(lm.group(1))

    # 할 일 목록 — 목록(.brief-list) 안의 <li> 만. 직접 추가한 할 일(.brief-mine)은 웹에서만.
    items = []
    listm = re.search(r"<ul[^>]*class=\"brief-list\"[^>]*>(.*?)</ul>", block, re.S)
    if listm:
        for li in re.findall(r"<li[^>]*>(.*?)</li>", listm.group(1), re.S):
            timem = re.search(r"<span[^>]*class=\"brief-time\"[^>]*>(.*?)</span>", li, re.S)
            bodym = re.search(r"<span[^>]*class=\"brief-body\"[^>]*>(.*?)</span>", li, re.S)
            time_text = inner_text(timem.group(1)) if timem else ""
            body_text = inner_text(bodym.group(1)) if bodym else inner_text(li)
            if not body_text:
                continue
            items.append({"time": "" if time_text in ("할 일", "TODO") else time_text,
                          "body": body_text})

    return {
        "v": 1,
        "date": date,
        "when": when,
        "whenFull": when_full,
        "updatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "weatherText": weather_text,
        "weatherHighlights": highlights[:4],
        "weatherDays": weather_days,
        "lead": lead,
        "items": items,
        "count": len(items),
    }


def main() -> int:
    src = INDEX.read_text(encoding="utf-8")
    data = parse_brief(src)
    out = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if "--check" in sys.argv:
        sys.stdout.write(out)
        return 0
    OUT.write_text(out, encoding="utf-8")
    print(f"briefing.json · {data['when']} · 할 일 {data['count']}개 · 날씨 {len(data['weatherDays'])}일치")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
