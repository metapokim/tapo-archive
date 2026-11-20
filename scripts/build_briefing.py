#!/usr/bin/env python3
"""index.html 의 아침 브리핑 영역과 '다가오는 일정' 원본 데이터를 읽어 briefing.json 을 만든다.

아이폰 홈 화면의 Scriptable 위젯이 읽어 가는 정적 JSON 이다.
아침 루틴(my-day-preparation)이 MORNING_BRIEF_START~END 를 갈아끼운 뒤
    python3 scripts/build_briefing.py
를 실행하면 briefing.json 이 같은 내용으로 다시 만들어진다.

2026-11-19: 위젯 라지 크기의 '다가오는 일정'(D-3~D-1) 섹션이 쓰도록
index.html 의 SEED·CALENDAR_EVENTS 에서 예정된 일정을 뽑아 upcoming 배열로 함께 내보낸다.
날짜별 D-day 는 기기(위젯)가 자기 오늘 날짜로 다시 계산하므로, 여기서는
오늘부터 60일 안의 일정을 모두 담아 둔다(자정이 지나도 위젯이 알아서 걸러 낸다).

2026-11-19 저녁: upcoming 의 각 줄에 index.html 카드의 고유 id · 상태(status) · 구분(cat)을
함께 내보낸다. 위젯이 Gist(기기 간 동기화)에서 웹앱의 삭제·완료 표시를 읽어
같은 카드를 '다가오는 일정'에서도 빼기 위해 id 로 짝을 맞춘다.
달력에서 온 일정(CALENDAR_EVENTS)은 index.html 에 카드가 없으므로 id 가 빈 문자열이다.

2026-11-21: .brief 의 data-lead-days(오늘·내일 2일치 리드 문구)를 leadDays 로 내보낸다.
위젯은 자정이 지나 leadDays[오늘] 로 리드 문구를 바꾸고, lead 필드도 그 날 리드로 채운다
(예전에는 어제 리드가 그대로 남았다).

사용: python3 scripts/build_briefing.py [--check]
  --check : 파일을 쓰지 않고 만들어질 JSON 을 화면에만 보여 준다.
"""
import html
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
OUT = ROOT / "briefing.json"

KST = timezone(timedelta(hours=9))
WEEKDAY = "월화수목금토일"

START = "<!-- MORNING_BRIEF_START -->"
END = "<!-- MORNING_BRIEF_END -->"

# index.html 의 '다가오는 일정' 규칙과 같게 — index.html 쪽 상수를 읽어 오고,
# 못 읽으면 아래 기본값을 쓴다 (2026-11-19 index.html 기준).
DONE_DEFAULT = ["참석 완료", "관람 완료", "완독", "읽음", "정리 완료", "시청 완료"]
NOT_WANTED_DEFAULT = (r"KBO|야구|트윈스|잠실야구장|한부모가족 권익증진|영미공법 연구포럼"
                      r"|사회적재난과 보건안전법|미디어 접근권")
SHOW_FROM_DEFAULT = "2026-01-01"
UPCOMING_HIDE_DEFAULT = r"덕소2"

# '다가오는 일정'이 아닌 카테고리 (기사·논문·메모·영상은 날짜가 '올린 날'일 뿐,
# 책도 날짜가 '서재에 넣은 날'일 뿐 — index.html upcomingDD 와 같은 규칙)
UPCOMING_SKIP_CATS = {"news", "grad", "memo", "video", "book"}
UPCOMING_DAYS = 60


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

    # 리드 문구 2일치 — .brief[data-lead-days] (자정이 지나 위젯이 오늘 리드를 고르는 데 쓴다)
    raw_leads = attr(section_tag, "data-lead-days", "") or attr(block, "data-lead-days", "")
    lead_days = {}
    if raw_leads:
        try:
            parsed = json.loads(raw_leads)
            for k, v in parsed.items():
                if re.match(r"^\d{4}-\d{2}-\d{2}$", str(k)):
                    lead_days[str(k)] = strip_tags(str(v))
        except json.JSONDecodeError:
            lead_days = {}

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
        "leadDays": lead_days,
        "lead": lead_days.get(date) or lead,
        "items": items,
        "count": len(items),
    }


# ── '다가오는 일정' ───────────────────────────────────────────


def _js_regex(src: str, name: str, default: str) -> re.Pattern:
    """index.html 의 `var NAME = /…/;` 정규식을 그대로 가져온다."""
    m = re.search(r"var\s+" + name + r"\s*=\s*/(.+?)/[gimsuy]*\s*;", src)
    return re.compile(m.group(1) if m else default)


def _js_string(src: str, name: str, default: str) -> str:
    m = re.search(r"var\s+" + name + r"\s*=\s*['\"]([^'\"]*)['\"]", src)
    return m.group(1) if m else default


def _js_done_set(src: str, default) -> set:
    m = re.search(r"var\s+DONE\s*=\s*\{(.*?)\}\s*;", src, re.S)
    if not m:
        return set(default)
    keys = re.findall(r"['\"]([^'\"]+)['\"]\s*:", m.group(1))
    return set(keys) if keys else set(default)


def _js_removed_ids(src: str) -> set:
    m = re.search(r"var\s+REMOVED_IDS\s*=\s*\{(.*?)\}\s*;", src, re.S)
    if not m:
        return set()
    return set(re.findall(r"([A-Za-z0-9_]+)\s*:\s*1", m.group(1)))


def parse_seed(src: str) -> list:
    """`var SEED = [ … ];` 를 JSON 으로 읽는다 (base64 이미지가 들어 있어도 그대로)."""
    i = src.find("var SEED = ")
    if i < 0:
        return []
    start = i + len("var SEED = ")
    try:
        data, _ = json.JSONDecoder().raw_decode(src, start)
    except json.JSONDecodeError as e:
        print(f"SEED 를 읽지 못했습니다: {e}", file=sys.stderr)
        return []
    return data if isinstance(data, list) else []


def parse_calendar_events(src: str) -> list:
    """`var CALENDAR_EVENTS = [{ date: '…', title: '…', … }];` (작은따옴표 객체 리터럴)."""
    m = re.search(r"var\s+CALENDAR_EVENTS\s*=\s*\[(.*?)\];", src, re.S)
    if not m:
        return []
    out = []
    for blk in re.findall(r"\{([^{}]*)\}", m.group(1)):
        ev = {}
        for k, q, v in re.findall(r"(\w+)\s*:\s*(['\"])(.*?)\2", blk, re.S):
            ev[k] = html.unescape(v)
        if ev.get("date") and ev.get("title"):
            out.append(ev)
    return out


def _norm_title(v: str) -> str:
    return re.sub(r"[\s\[\](){}〈〉<>·.,'\"~\-]", "", str(v or "")).lower()


def build_upcoming(src: str, today: date) -> list:
    """index.html 의 '다가오는 일정'과 같은 규칙으로 예정된 일정을 뽑는다.

    - SEED 카드: 날짜가 있고, 기사·대학원·메모·영상이 아니고, 끝난 상태가 아니며,
      오늘부터 60일 안. '덕소2'는 브리핑 상단에만.
    - CALENDAR_EVENTS: 같은 규칙 + 아카이브에 같은 날 같은 이름이 있으면 건너뛴다.
    - 정렬: 날짜 오름차순, 같은 날은 아카이브 카드가 먼저.
    """
    removed = _js_removed_ids(src)
    not_wanted = _js_regex(src, "NOT_WANTED", NOT_WANTED_DEFAULT)
    show_from = _js_string(src, "SHOW_FROM", SHOW_FROM_DEFAULT)
    hide = _js_regex(src, "UPCOMING_HIDE", UPCOMING_HIDE_DEFAULT)
    done = _js_done_set(src, DONE_DEFAULT)

    seed = [it for it in parse_seed(src) if isinstance(it, dict)]

    # index.html 의 isNotWanted — 지운 카드·원치 않는 주제·너무 지난 공연
    items = []
    for it in seed:
        title = str(it.get("title") or "")
        if str(it.get("id") or "") in removed:
            continue
        if not_wanted.search(title + " " + str(it.get("genre") or "")):
            continue
        if it.get("cat") == "show" and it.get("date") and str(it.get("date")) < show_from:
            continue
        items.append(it)

    def day_diff(s) -> int | None:
        try:
            d = datetime.strptime(str(s), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
        return (d - today).days

    rows = []

    def add(date_s, title, time_s="", place="", from_cal=False):
        dd = day_diff(date_s)
        if dd is None or dd < 0 or dd > UPCOMING_DAYS:
            return None
        flat = re.sub(r"\s+", "", str(title or ""))
        if hide.search(flat):                     # 덕소2 는 브리핑 상단에만
            return None
        return {"date": str(date_s), "title": str(title).strip(),
                "time": str(time_s or "").strip(), "place": str(place or "").strip(),
                "_cal": from_cal}

    for it in items:
        if not it.get("date"):
            continue
        if str(it.get("cat") or "") in UPCOMING_SKIP_CATS:
            continue
        if str(it.get("status") or "") in done:
            continue
        r = add(it.get("date"), it.get("title"), it.get("time"), it.get("place"))
        if r:
            r["id"] = str(it.get("id") or "")
            r["status"] = str(it.get("status") or "")
            r["cat"] = str(it.get("cat") or "")
            rows.append(r)

    archived = {(str(it.get("date") or ""), _norm_title(it.get("title"))) for it in items}

    def in_archive(ev) -> bool:
        b = _norm_title(ev.get("title"))
        if not b:
            return False
        for d, a in archived:
            if d != str(ev.get("date")) or not a:
                continue
            if a == b or b in a or a in b:
                return True
        return False

    for ev in parse_calendar_events(src):
        if in_archive(ev):
            continue
        r = add(ev.get("date"), ev.get("title"), ev.get("time"), ev.get("place"), True)
        if r:
            r["id"] = ""                                      # 달력에서 온 일정 — 카드 id 없음
            r["status"] = ""
            r["cat"] = ""
            r["cal"] = True
            rows.append(r)

    rows.sort(key=lambda r: (r["date"], 1 if r["_cal"] else 0))
    for r in rows:
        r.pop("_cal", None)
    return rows


def main() -> int:
    src = INDEX.read_text(encoding="utf-8")
    data = parse_brief(src)
    data["upcoming"] = build_upcoming(src, datetime.now(KST).date())
    out = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if "--check" in sys.argv:
        sys.stdout.write(out)
        return 0
    OUT.write_text(out, encoding="utf-8")
    print(f"briefing.json · {data['when']} · 할 일 {data['count']}개 · 날씨 {len(data['weatherDays'])}일치"
          f" · 다가오는 일정 {len(data['upcoming'])}건")
    for r in data["upcoming"][:6]:
        print(f"  {r['date']} {r['time']:<13} {r['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
