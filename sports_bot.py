"""
=====================================================================
 SPORTS SCHEDULE BOT — Versi GitHub Actions (100% GRATIS) — PINTAR
=====================================================================
 - Sumber data : TheSportsDB (gratis, TANPA API key pribadi)
                 + ESPN (gratis, tanpa key) sebagai CADANGAN khusus UFC
                 + ESPN (gratis, tanpa key) sebagai CADANGAN khusus World Cup
 - Hosting     : GitHub Actions (gratis, tanpa kartu kredit)
 - Jadwal      : Otomatis tiap hari ±08:00 WIB
                 (diatur di .github/workflows/jadwal.yml — bukan di sini)
 - PC/laptop boleh mati total. Semua jalan di server GitHub.
=====================================================================
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

# ============================================================
# KONFIGURASI — dari GitHub Secrets (di-set di repo Settings)
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ ERROR: TELEGRAM_TOKEN / TELEGRAM_CHAT_ID belum di-set.")
    print("   Set di GitHub repo -> Settings -> Secrets and variables")
    print("   -> Actions -> New repository secret")
    sys.exit(1)

WIB = ZoneInfo("Asia/Jakarta")

TSDB_KEY = "123"
TSDB = f"https://www.thesportsdb.com/api/v1/json/{TSDB_KEY}"

ESPN_UFC_URL = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"
ESPN_WORLDCUP_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"

DELAY = 2
MAX_PER_LEAGUE = 12

SPORTS = ["Soccer", "Basketball", "Fighting"]

SPORT_HEADER = {
    "Soccer": "⚽ *SEPAK BOLA*",
    "Basketball": "🏀 *BASKET*",
    "Fighting": "🥊 *TINJU & MMA*",
}

TOURNAMENT_KEYWORDS = [
    "world cup", "club world cup", "champions league", "europa league",
    "conference league", "nations league", "copa america", "copa libertadores",
    "copa sudamericana", "european championship", "euro 20", "afcon",
    "africa cup", "asian cup", "gold cup", "confederations", "olympic",
    "super cup", "world championship", "grand prix", "finals",
]

FAVORITE_KEYWORDS = [
    "premier league", "la liga", "serie a", "bundesliga", "ligue 1",
    "eredivisie", "primeira liga", "liga 1", "mls",
    "nba", "euroleague",
    "ufc", "one championship", "byon", "pfl", "bellator", "boxing",
    "real american freestyle",
]

WATCH_TEAMS = [
    "indonesia",
]


def get_json(url: str) -> dict:
    for attempt in range(2):
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                return r.json() or {}
            print(f"   ⚠️ HTTP {r.status_code} -> retry {attempt + 1}/2")
        except Exception as e:
            print(f"   ⚠️ {e} -> retry {attempt + 1}/2")
        time.sleep(3)
    return {}


def classify_league(name: str) -> int:
    low = (name or "").lower()
    if any(k in low for k in TOURNAMENT_KEYWORDS):
        return 0
    if any(k in low for k in FAVORITE_KEYWORDS):
        return 1
    return 2


def is_watched_team(ev: dict) -> bool:
    home = (ev.get("strHomeTeam") or "").lower()
    away = (ev.get("strAwayTeam") or "").lower()
    return any(t in home or t in away for t in WATCH_TEAMS)


def event_wib_date(ev: dict):
    ts = ev.get("strTimestamp")
    if not ts:
        return None
    try:
        utc_dt = datetime.fromisoformat(ts.replace("Z", "")).replace(tzinfo=timezone.utc)
        return utc_dt.astimezone(WIB).strftime("%Y-%m-%d")
    except Exception:
        return None


def format_event(ev: dict) -> str:
    home = ev.get("strHomeTeam") or ""
    away = ev.get("strAwayTeam") or ""
    title = f"{home} vs {away}" if home and away else (ev.get("strEvent") or "?")

    score_h = ev.get("intHomeScore")
    score_a = ev.get("intAwayScore")
    if score_h not in (None, "") and score_a not in (None, ""):
        return f"✅ {home} {score_h}–{score_a} {away}\n     (Selesai)"

    ts = ev.get("strTimestamp")
    if ts:
        try:
            utc_dt = datetime.fromisoformat(ts.replace("Z", "")).replace(tzinfo=timezone.utc)
            wib = utc_dt.astimezone(WIB)
            return f"🕐 {wib.strftime('%a %d/%m')} • {wib.strftime('%H:%M')} WIB\n     {title}"
        except Exception:
            pass
    t = ev.get("strTime") or "TBD"
    return f"🕐 {t} WIB\n     {title}"


def fetch_sport_window(sport: str, query_dates, keep_dates):
    seen, out = set(), []
    for d in query_dates:
        data = get_json(f"{TSDB}/eventsday.php?d={d}&s={sport}")
        for ev in (data.get("events") or []):
            eid = ev.get("idEvent")
            if eid and eid in seen:
                continue
            wib_date = event_wib_date(ev)
            if wib_date is not None and wib_date not in keep_dates:
                continue
            if eid:
                seen.add(eid)
            out.append(ev)
        time.sleep(DELAY)
    return out


def fetch_espn_ufc(keep_dates):
    out = []
    data = get_json(ESPN_UFC_URL)
    leagues = data.get("leagues") or []
    calendar = (leagues[0].get("calendar") if leagues else []) or []

    for item in calendar:
        start = item.get("startDate")
        if not start:
            continue
        try:
            dt_utc = datetime.fromisoformat(start.replace("Z", "")).replace(tzinfo=timezone.utc)
            ev_date_wib = dt_utc.astimezone(WIB).strftime("%Y-%m-%d")
        except Exception:
            continue
        if ev_date_wib not in keep_dates:
            continue
        out.append({
            "idEvent": f"espn-ufc-{item.get('label')}",
            "strEvent": item.get("label") or "UFC Event",
            "strHomeTeam": "",
            "strAwayTeam": "",
            "strLeague": "UFC",
            "strTimestamp": start.replace("Z", ""),
            "intHomeScore": None,
            "intAwayScore": None,
        })
    time.sleep(DELAY)
    return out


def fetch_espn_worldcup(query_dates, keep_dates):
    out = []
    dates_compact = sorted(d.replace("-", "") for d in query_dates)
    date_range = f"{dates_compact[0]}-{dates_compact[-1]}"

    data = get_json(f"{ESPN_WORLDCUP_URL}?dates={date_range}&limit=100")
    events = data.get("events") or []

    for ev in events:
        start = ev.get("date")
        if not start:
            continue
        try:
            dt_utc = datetime.fromisoformat(start.replace("Z", "")).replace(tzinfo=timezone.utc)
            ev_date_wib = dt_utc.astimezone(WIB).strftime("%Y-%m-%d")
        except Exception:
            continue
        if ev_date_wib not in keep_dates:
            continue

        comp = (ev.get("competitions") or [{}])[0]
        competitors = comp.get("competitors") or []
        home = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away = next((c for c in competitors if c.get("homeAway") == "away"), {})

        home_name = (home.get("team") or {}).get("displayName", "")
        away_name = (away.get("team") or {}).get("displayName", "")
        home_score = home.get("score")
        away_score = away.get("score")

        status = (comp.get("status") or {}).get("type") or {}
        is_final = status.get("completed", False)

        out.append({
            "idEvent": f"espn-wc-{ev.get('id')}",
            "strEvent": f"{home_name} vs {away_name}",
            "strHomeTeam": home_name,
            "strAwayTeam": away_name,
            "strLeague": "FIFA World Cup",
            "strTimestamp": start.replace("Z", ""),
            "intHomeScore": home_score if is_final else None,
            "intAwayScore": away_score if is_final else None,
        })

    time.sleep(DELAY)
    return out


def build_message() -> str:
    now = datetime.now(WIB)
    hari = {
        "Monday": "Senin", "Tuesday": "Selasa", "Wednesday": "Rabu",
        "Thursday": "Kamis", "Friday": "Jumat", "Saturday": "Sabtu",
        "Sunday": "Minggu",
    }[now.strftime("%A")]

    today_str = now.strftime("%Y-%m-%d")
    tomorrow_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    keep_dates = {today_str, tomorrow_str}
    query_dates = [yesterday_str, today_str, tomorrow_str]

    lines = [
        "🏟️ *JADWAL OLAHRAGA HARI INI*",
        f"📅 {hari}, {now.strftime('%d %B %Y')}",
        "═══════════════════════",
    ]

    for sport in SPORTS:
        lines.append("")
        lines.append(f"{SPORT_HEADER.get(sport, sport)}")
        lines.append("───────────────────────")
        events = fetch_sport_window(sport, query_dates, keep_dates)

        if sport == "Fighting":
            has_ufc = any("ufc" in (ev.get("strLeague") or "").lower() for ev in events)
            if not has_ufc:
                espn_events = fetch_espn_ufc(keep_dates)
                if espn_events:
                    print(f"   ℹ️ +{len(espn_events)} event UFC dari ESPN (cadangan)")
                events.extend(espn_events)

        if sport == "Soccer":
            has_worldcup = any("world cup" in (ev.get("strLeague") or "").lower() for ev in events)
            if not has_worldcup:
                wc_events = fetch_espn_worldcup(query_dates, keep_dates)
                if wc_events:
                    print(f"   ℹ️ +{len(wc_events)} event World Cup dari ESPN (cadangan)")
                events.extend(wc_events)

        if sport == "Soccer":
            print(f"   ℹ️ Soccer: {len(events)} event (query={query_dates}, keep={sorted(keep_dates)})")
            for ev in events:
                lg = ev.get("strLeague") or ""
                if any(k in lg.lower() for k in TOURNAMENT_KEYWORDS):
                    print(f"   ℹ️ Turnamen terdeteksi: {ev.get('strEvent')} | liga={lg} | ts={ev.get('strTimestamp')}")

        by_league = {}
        for ev in events:
            lg = ev.get("strLeague") or "Lainnya"
            by_league.setdefault(lg, []).append(ev)

        keep_others = sport != "Soccer"

        ranked = []
        for lg, evs in by_league.items():
            rank = classify_league(lg)

            if rank == 2 and sport == "Soccer":
                watched = [ev for ev in evs if is_watched_team(ev)]
                if watched:
                    ranked.append((1, lg, watched))
                continue

            if rank == 2 and not keep_others:
                continue

            ranked.append((rank, lg, evs))
        ranked.sort(key=lambda x: (x[0], x[1]))

        if not ranked:
            lines.append("Tidak ada pertandingan")
            continue

        for rank, lg, evs in ranked:
            tag = "🏆 " if rank == 0 else "▪️ "
            lines.append(f"\n{tag}*{lg}*")
            for ev in evs[:MAX_PER_LEAGUE]:
                lines.append(format_event(ev))
                lines.append("")

    lines.append("═══════════════════════")
    lines.append("_Sumber: TheSportsDB + ESPN • Dikirim otomatis via GitHub Actions_ 🤖")
    return "\n".join(lines)


def send_to_telegram(text: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    ok = True
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > 3900:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    chunks.append(cur)

    for chunk in chunks:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        try:
            r = requests.post(url, json=payload, timeout=20)
            if r.status_code == 200:
                print("✅ Pesan terkirim ke Telegram")
            else:
                print(f"❌ Telegram error {r.status_code}: {r.text}")
                ok = False
        except Exception as e:
            print(f"❌ Gagal kirim: {e}")
            ok = False
        time.sleep(1)
    return ok


if __name__ == "__main__":
    print(f"🏟️ Mengambil jadwal... ({datetime.now(WIB).strftime('%d-%m-%Y %H:%M WIB')})")
    msg = build_message()
    success = send_to_telegram(msg)
    sys.exit(0 if success else 1)
