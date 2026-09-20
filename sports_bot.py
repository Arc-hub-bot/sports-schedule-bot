"""
=====================================================================
 SPORTS SCHEDULE BOT — Versi GitHub Actions (100% GRATIS)
=====================================================================
 - Sumber data : TheSportsDB (key publik "123") + ESPN (tanpa key)
 - ESPN dipakai sebagai CADANGAN untuk UFC dan SEPAK BOLA
 - Hosting     : GitHub Actions, dipicu cron-job.org (lihat jadwal.yml)

 PERBAIKAN versi ini:
   7) CADANGAN ESPN UNTUK SEPAK BOLA: kalau TheSportsDB tidak
      mengembalikan satu pun laga liga besar/turnamen/timnas, bot
      otomatis ambil dari ESPN (EPL, La Liga, Serie A, Bundesliga,
      Ligue 1, UCL, UEL, UECL, Liga 1 Indonesia).
   8) get_json() sekarang mencatat kegagalan dengan jelas di log
      (tidak lagi diam-diam menjadi "Tidak ada pertandingan").
=====================================================================
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

# ============================================================
# KONFIGURASI — dari GitHub Secrets
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

# ESPN sepak bola: 1 panggilan per liga (rentang tanggal)
ESPN_SOCCER_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={d}"
)
# Nama liga sengaja mengandung kata kunci di FAVORITE/TOURNAMENT_KEYWORDS
ESPN_SOCCER_LEAGUES = {
    "eng.1": "English Premier League",
    "esp.1": "Spanish La Liga",
    "ita.1": "Italian Serie A",
    "ger.1": "German Bundesliga",
    "fra.1": "French Ligue 1",
    "uefa.champions": "UEFA Champions League",
    "uefa.europa": "UEFA Europa League",
    "uefa.europa.conf": "UEFA Conference League",
    "idn.1": "Indonesian Liga 1",
}

DELAY = 2            # jeda antar panggilan TSDB (detik)
ESPN_DELAY = 0.5     # jeda antar panggilan ESPN (detik)
MAX_PER_LEAGUE = 12  # maksimal pertandingan ditampilkan per liga

# ============================================================
# CABANG OLAHRAGA YANG DIPANTAU
# (Volleyball ditambahkan karena pernah muncul di pesan bot sebelumnya.
#  Tidak mau? Hapus "Volleyball" dari list SPORTS di bawah.)
# ============================================================
SPORTS = ["Soccer", "Basketball", "Fighting", "Volleyball"]

SPORT_HEADER = {
    "Soccer": "⚽ *SEPAK BOLA*",
    "Basketball": "🏀 *BASKET*",
    "Fighting": "🥊 *TINJU & MMA*",
    "Volleyball": "🏐 *VOLI*",
}

# ============================================================
# AUTO-DETEKSI TURNAMEN (berdasarkan NAMA liga)
# ============================================================
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


# ============================================================
# UTIL
# ============================================================
def get_json(url: str) -> dict:
    """GET request dengan retry sederhana + log kegagalan yang jelas."""
    for attempt in range(2):
        try:
            r = requests.get(url, timeout=25)
            if r.status_code == 200:
                return r.json() or {}
            print(f"   ⚠️ HTTP {r.status_code} untuk {url} -> retry {attempt + 1}/2")
        except Exception as e:
            print(f"   ⚠️ {e} untuk {url} -> retry {attempt + 1}/2")
        time.sleep(3)
    print(f"   ❌ GAGAL total mengambil: {url}")
    return {}


def classify_league(name: str) -> int:
    """0 = turnamen besar, 1 = liga favorit, 2 = lainnya."""
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


def event_wib_date(ev: dict) -> str | None:
    """Tanggal WIB asli event (dari strTimestamp UTC)."""
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
            utc_dt = datetime.fromisoformat(ts.replace("Z", "")).replace(
                tzinfo=timezone.utc
            )
            wib = utc_dt.astimezone(WIB)
            return f"🕐 {wib.strftime('%a %d/%m')} • {wib.strftime('%H:%M')} WIB\n     {title}"
        except Exception:
            pass
    t = ev.get("strTime") or "TBD"
    return f"🕐 {t} WIB\n     {title}"


def _tokens(name: str) -> set[str]:
    stop = {"fc", "afc", "cf", "sc", "ac", "as", "the"}
    return {w for w in "".join(c if c.isalnum() else " " for c in (name or "").lower()).split() if w not in stop}


def _dup_of_any(ev: dict, others: list[dict]) -> bool:
    """True kalau 'ev' adalah laga yang sama dengan salah satu event di 'others'."""
    d = event_wib_date(ev)
    h, a = _tokens(ev.get("strHomeTeam")), _tokens(ev.get("strAwayTeam"))
    if not h or not a:
        return False
    for o in others:
        if event_wib_date(o) != d:
            continue
        if h & _tokens(o.get("strHomeTeam")) and a & _tokens(o.get("strAwayTeam")):
            return True
    return False


def fetch_sport_window(sport: str, query_dates: list[str], keep_dates: set[str]) -> list[dict]:
    """Ambil event TSDB untuk tanggal QUERY, simpan hanya yang tanggal
    WIB-nya ada di KEEP_DATES. Dedupe berdasarkan idEvent."""
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


def fetch_espn_ufc(keep_dates: set[str]) -> list[dict]:
    """CADANGAN UFC dari ESPN (kalender seluruh musim, 1x panggilan)."""
    out = []
    data = get_json(ESPN_UFC_URL)
    leagues = data.get("leagues") or []
    calendar = (leagues[0].get("calendar") if leagues else []) or []

    for item in calendar:
        start = item.get("startDate")
        if not start:
            continue
        try:
            dt_utc = datetime.fromisoformat(start.replace("Z", "")).replace(
                tzinfo=timezone.utc
            )
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


def fetch_espn_soccer(query_dates: list[str], keep_dates: set[str]) -> list[dict]:
    """SUMBER SEPAK BOLA dari ESPN. 1 panggilan per liga PER TANGGAL
    (?dates=YYYYMMDD), lalu disaring ulang berdasarkan tanggal WIB asli.
    Catatan: tanpa parameter dates, ESPN mengembalikan hari acak/terdekat,
    jadi parameter dates WAJIB."""
    out, seen = [], set()
    for slug, lname in ESPN_SOCCER_LEAGUES.items():
        for d in query_dates:
            data = get_json(ESPN_SOCCER_URL.format(slug=slug, d=d.replace("-", "")))
            for e in (data.get("events") or []):
                eid = f"espn-{e.get('id')}"
                ts = (e.get("date") or "").replace("Z", "")
                if eid in seen or event_wib_date({"strTimestamp": ts}) not in keep_dates:
                    continue
                seen.add(eid)

                comp = (e.get("competitions") or [{}])[0]
                teams = {c.get("homeAway"): c for c in (comp.get("competitors") or [])}
                status_type = (e.get("status") or {}).get("type") or {}
                done = status_type.get("completed")
                home_c = teams.get("home") or {}
                away_c = teams.get("away") or {}

                out.append({
                    "idEvent": eid,
                    "strEvent": e.get("name") or "",
                    "strHomeTeam": (home_c.get("team") or {}).get("displayName", ""),
                    "strAwayTeam": (away_c.get("team") or {}).get("displayName", ""),
                    "strLeague": lname,
                    "strTimestamp": ts,
                    "intHomeScore": home_c.get("score") if done else None,
                    "intAwayScore": away_c.get("score") if done else None,
                })
            time.sleep(ESPN_DELAY)
    return out


# ============================================================
# BANGUN PESAN
# ============================================================
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

        # CADANGAN UFC
        if sport == "Fighting":
            has_ufc = any("ufc" in (ev.get("strLeague") or "").lower() for ev in events)
            if not has_ufc:
                espn_events = fetch_espn_ufc(keep_dates)
                if espn_events:
                    print(f"   ℹ️ +{len(espn_events)} event UFC dari ESPN (cadangan)")
                events.extend(espn_events)

        # SEPAK BOLA: ESPN dipakai untuk liga-liga besar (lebih andal),
        # TSDB tetap dipakai untuk turnamen/liga lain & Timnas Indonesia.
        if sport == "Soccer":
            print(f"   ℹ️ Soccer: {len(events)} event dari TSDB (query={query_dates}, keep={sorted(keep_dates)})")
            espn_ev = fetch_espn_soccer(query_dates, keep_dates)
            print(f"   ℹ️ Soccer: {len(espn_ev)} laga dari ESPN")
            # buang duplikat: laga TSDB yang sama dengan laga ESPN (tanggal WIB
            # sama + kedua tim punya kata nama yang sama) tidak dipakai lagi
            events = [ev for ev in events if not _dup_of_any(ev, espn_ev)] + espn_ev

            for ev in events:
                lg = ev.get("strLeague") or ""
                if any(k in lg.lower() for k in TOURNAMENT_KEYWORDS):
                    print(f"   ℹ️ Turnamen terdeteksi: {ev.get('strEvent')} | liga={lg} | ts={ev.get('strTimestamp')}")

        # Kelompokkan per liga
        by_league: dict[str, list[dict]] = {}
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


# ============================================================
# KIRIM KE TELEGRAM (auto-split jika > 4096 karakter)
# ============================================================
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


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print(f"🏟️ Mengambil jadwal... ({datetime.now(WIB).strftime('%d-%m-%Y %H:%M WIB')})")
    msg = build_message()
    success = send_to_telegram(msg)
    sys.exit(0 if success else 1)
