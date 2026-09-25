"""
=====================================================================
 SPORTS SCHEDULE BOT — Versi GitHub Actions (100% GRATIS) — PINTAR
=====================================================================
 - Sumber data : TheSportsDB (gratis, TANPA API key pribadi)
                 + ESPN (gratis, tanpa key) sebagai CADANGAN untuk
                 UFC dan SEPAK BOLA
 - Hosting     : GitHub Actions (gratis, tanpa kartu kredit)
 - Jadwal      : Otomatis tiap hari ±08:00 WIB
                 (diatur di .github/workflows/jadwal.yml — bukan di sini)
 - PC/laptop boleh mati total. Semua jalan di server GitHub.

 PERBAIKAN versi ini (vs versi lama):
   1) AUTO-DETEKSI TURNAMEN berdasarkan NAMA liga (World Cup, Euro,
      Copa America, Champions League, dll. otomatis tertangkap).
   2) HEMAT PANGGILAN API: 1 panggilan per cabang olahraga per tanggal.
   3) Pakai kunci publik "123".
   4) SUMBER GANDA UNTUK FIGHTING/UFC (TheSportsDB + cadangan ESPN).
   5) TIMNAS INDONESIA selalu ditampilkan kalau bermain, di liga apa pun.
   6) JENDELA TANGGAL AKURAT: TSDB kadang mencatat laga lewat
      tengah malam WIB (mis. World Cup jam 03:00 WIB) di tanggal UTC
      sebelumnya. Bot mengambil data kemarin+hari ini+besok,
      lalu MENYARING ulang berdasarkan tanggal WIB asli tiap laga —
      jadi laga seperti ini tidak hilang lagi.
   7) SUMBER GANDA UNTUK SEPAK BOLA (BARU — 25 Sep 2026): TheSportsDB
      kunci publik "123" TERBUKTI sering tidak mengembalikan data
      sepak bola sama sekali untuk suatu tanggal (bukan cuma "kadang
      hilang" seperti dugaan awal — bisa benar-benar KOSONG TOTAL).
      Bot sekarang SELALU memanggil ESPN untuk daftar liga
      favorit + turnamen utama (lihat ESPN_SOCCER_LEAGUES di bawah),
      digabung dengan hasil TheSportsDB, dan otomatis dedupe
      berdasarkan tim tuan rumah + tim tamu + tanggal WIB.

 Script jalan SEKALI per eksekusi (ambil -> kirim -> selesai).
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

# Kunci publik gratis TheSportsDB.
# CATATAN: kunci "123" ini kunci TESTING milik TheSportsDB, bukan kunci
# penuh — sering tidak mengembalikan data liga-liga besar (kadang
# sebagian liga hilang, kadang SATU CABANG OLAHRAGA KOSONG TOTAL untuk
# suatu tanggal). Karena itu Sepak Bola & Fighting punya cadangan ESPN
# yang SELALU dijalankan, bukan cuma saat TSDB kosong.
TSDB_KEY = "123"
TSDB = f"https://www.thesportsdb.com/api/v1/json/{TSDB_KEY}"

# ESPN — API publik gratis tanpa key, dipakai sebagai CADANGAN untuk
# UFC dan Sepak Bola
ESPN_UFC_URL = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"
ESPN_SOCCER_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard"

# Liga & turnamen sepak bola yang SELALU dicek ke ESPN (kode slug ESPN).
# Ini sengaja daftar tetap (bukan auto-deteksi seperti TSDB) karena ESPN
# butuh 1 panggilan API per liga — daftar ini sudah mencakup semua liga
# di FAVORITE_KEYWORDS + turnamen utama di TOURNAMENT_KEYWORDS supaya
# nama liganya otomatis cocok dengan logika classify_league() di bawah.
# Mau tambah liga favorit lain? Tambahkan di sini juga (cari slug-nya
# di https://www.espn.com/soccer/scoreboard/_/league/<slug>).
ESPN_SOCCER_LEAGUES = {
    "Premier League": "eng.1",
    "La Liga": "esp.1",
    "Serie A": "ita.1",
    "Bundesliga": "ger.1",
    "Ligue 1": "fra.1",
    "Eredivisie": "ned.1",
    "Primeira Liga": "por.1",
    "Liga 1 Indonesia": "idn.1",
    "MLS": "usa.1",
    "UEFA Champions League": "uefa.champions",
    "UEFA Europa League": "uefa.europa",
    "UEFA Europa Conference League": "uefa.europa.conf",
    "UEFA Nations League": "uefa.nations",
    "UEFA European Championship": "uefa.euro",
    "FIFA World Cup": "fifa.world",
    "Copa America": "conmebol.america",
    "CONCACAF Gold Cup": "concacaf.gold",
    "Africa Cup of Nations": "caf.nations",
    "AFC Asian Cup": "afc.asiancup",
}

DELAY = 2            # jeda antar panggilan API TheSportsDB (detik) — aman dari rate limit
ESPN_DELAY = 0.4      # jeda antar panggilan ESPN (detik) — ESPN jauh lebih longgar dari TSDB
MAX_PER_LEAGUE = 12   # maksimal pertandingan ditampilkan per liga

# ============================================================
# CABANG OLAHRAGA YANG DIPANTAU
# Tiap cabang = 1 panggilan API per tanggal (irit & lengkap).
# Nama harus sesuai TheSportsDB: Soccer, Basketball, Fighting, dll.
# Mau tambah cabang? Tambahkan di list ini (mis. "Motorsport", "Tennis").
# ============================================================
SPORTS = ["Soccer", "Basketball", "Fighting"]

# Judul section per cabang (untuk tampilan pesan)
SPORT_HEADER = {
    "Soccer": "⚽ *SEPAK BOLA*",
    "Basketball": "🏀 *BASKET*",
    "Fighting": "🥊 *TINJU & MMA*",
}

# ============================================================
# AUTO-DETEKSI TURNAMEN (berdasarkan NAMA liga, bukan ID)
# Liga/turnamen yang namanya mengandung salah satu kata kunci di bawah
# akan SELALU ditampilkan. Turnamen baru otomatis tertangkap.
# ============================================================
TOURNAMENT_KEYWORDS = [
    "world cup", "club world cup", "champions league", "europa league",
    "conference league", "nations league", "copa america", "copa libertadores",
    "copa sudamericana", "european championship", "euro 20", "afcon",
    "africa cup", "asian cup", "gold cup", "confederations", "olympic",
    "super cup", "world championship", "grand prix", "finals",
]

# Liga reguler favorit (tetap tampil walau bukan turnamen)
FAVORITE_KEYWORDS = [
    "premier league", "la liga", "serie a", "bundesliga", "ligue 1",
    "eredivisie", "primeira liga", "liga 1", "mls",          # bola
    "nba", "euroleague",                                     # basket
    "ufc", "one championship", "byon", "pfl", "bellator", "boxing",  # fighting
    "real american freestyle",  # RAF (gulat) — tampil kalau TheSportsDB
                                 # suatu saat mendata promosi ini
]

# Tim yang SELALU ditampilkan kalau bermain, di kompetisi apa pun
# (mis. Timnas Indonesia main di kualifikasi Piala Dunia/Piala AFF, yang
# nama liganya belum tentu mengandung kata "Indonesia")
WATCH_TEAMS = [
    "indonesia",
]


# ============================================================
# UTIL
# ============================================================
def get_json(url: str) -> dict:
    """GET request dengan retry sederhana."""
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
    """0 = turnamen besar, 1 = liga favorit, 2 = lainnya."""
    low = (name or "").lower()
    if any(k in low for k in TOURNAMENT_KEYWORDS):
        return 0
    if any(k in low for k in FAVORITE_KEYWORDS):
        return 1
    return 2


def is_watched_team(ev: dict) -> bool:
    """True kalau salah satu tim di event ini ada di WATCH_TEAMS
    (mis. Timnas Indonesia), apa pun nama liganya."""
    home = (ev.get("strHomeTeam") or "").lower()
    away = (ev.get("strAwayTeam") or "").lower()
    return any(t in home or t in away for t in WATCH_TEAMS)


def event_wib_date(ev: dict) -> str | None:
    """Tanggal WIB asli dari sebuah event (berdasarkan strTimestamp UTC).
    Dipakai untuk menyaring ulang event agar masuk jendela tanggal yang
    benar, terlepas dari bagaimana TheSportsDB mencatat 'dateEvent'-nya."""
    ts = ev.get("strTimestamp")
    if not ts:
        return None
    try:
        utc_dt = datetime.fromisoformat(ts.replace("Z", "")).replace(tzinfo=timezone.utc)
        return utc_dt.astimezone(WIB).strftime("%Y-%m-%d")
    except Exception:
        return None


def format_event(ev: dict) -> str:
    """Ubah 1 event jadi 1 baris teks rapi (waktu WIB)."""
    home = ev.get("strHomeTeam") or ""
    away = ev.get("strAwayTeam") or ""
    title = f"{home} vs {away}" if home and away else (ev.get("strEvent") or "?")

    score_h = ev.get("intHomeScore")
    score_a = ev.get("intAwayScore")
    if score_h not in (None, "") and score_a not in (None, ""):
        return f"✅ {home} {score_h}–{score_a} {away}\n     (Selesai)"

    ts = ev.get("strTimestamp")  # contoh: "2026-06-13T19:00:00"
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


def fetch_sport_window(sport: str, query_dates: list[str], keep_dates: set[str]) -> list[dict]:
    """Ambil event satu cabang olahraga untuk daftar tanggal QUERY (ke TSDB),
    lalu HANYA SIMPAN event yang tanggal WIB aslinya ada di KEEP_DATES.
    Dedupe berdasarkan idEvent.

    Ini menangani kasus laga lewat tengah malam WIB yang oleh TSDB
    tercatat di tanggal UTC (sehari sebelumnya) — supaya tidak hilang
    dari jadwal."""
    seen, out = set(), []
    for d in query_dates:
        data = get_json(f"{TSDB}/eventsday.php?d={d}&s={sport}")
        for ev in (data.get("events") or []):
            eid = ev.get("idEvent")
            if eid and eid in seen:
                continue

            wib_date = event_wib_date(ev)
            if wib_date is not None and wib_date not in keep_dates:
                continue  # di luar jendela WIB yang kita mau -> skip

            if eid:
                seen.add(eid)
            out.append(ev)
        time.sleep(DELAY)
    return out


def fetch_espn_ufc(keep_dates: set[str]) -> list[dict]:
    """CADANGAN khusus UFC dari ESPN (gratis, tanpa key).
    ESPN menyediakan daftar SELURUH event UFC musim ini di field
    'calendar' (1x panggilan untuk semua tanggal). Kita ambil event
    yang tanggalnya (dikonversi ke WIB) ada di 'keep_dates'."""
    out = []
    data = get_json(ESPN_UFC_URL)
    leagues = data.get("leagues") or []
    calendar = (leagues[0].get("calendar") if leagues else []) or []

    for item in calendar:
        start = item.get("startDate")  # contoh: "2026-06-15T03:00Z"
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


def _parse_espn_datetime(date_str: str | None) -> datetime | None:
    """Parse tanggal ESPN (mis. '2026-09-22T16:45Z', kadang tanpa detik)
    jadi datetime UTC aware. Return None kalau gagal parse."""
    if not date_str:
        return None
    s = date_str.replace("Z", "")
    try:
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def fetch_espn_soccer(query_dates: list[str], keep_dates: set[str]) -> list[dict]:
    """CADANGAN Sepak Bola dari ESPN (gratis, tanpa key).

    SELALU dijalankan (bukan hanya saat TheSportsDB kosong total) karena
    TheSportsDB kunci publik "123" terbukti tidak konsisten: kadang cuma
    sebagian liga yang hilang, kadang satu cabang olahraga kosong total
    untuk suatu tanggal. Menyasar daftar liga favorit + turnamen utama
    di ESPN_SOCCER_LEAGUES (1 panggilan API per liga, dengan rentang
    tanggal query_dates dalam SATU kali panggilan per liga)."""
    out = []
    start = min(query_dates).replace("-", "")
    end = max(query_dates).replace("-", "")
    date_range = start if start == end else f"{start}-{end}"

    for league_name, slug in ESPN_SOCCER_LEAGUES.items():
        url = f"{ESPN_SOCCER_URL.format(league=slug)}?dates={date_range}"
        data = get_json(url)
        for ev in (data.get("events") or []):
            dt = _parse_espn_datetime(ev.get("date"))
            if dt is None:
                continue
            wib_date = dt.astimezone(WIB).strftime("%Y-%m-%d")
            if wib_date not in keep_dates:
                continue

            comp = (ev.get("competitions") or [{}])[0]
            competitors = comp.get("competitors") or []
            home = next((c for c in competitors if c.get("homeAway") == "home"), {})
            away = next((c for c in competitors if c.get("homeAway") == "away"), {})
            home_name = (home.get("team") or {}).get("displayName", "")
            away_name = (away.get("team") or {}).get("displayName", "")
            if not home_name or not away_name:
                continue

            status_type = ((comp.get("status") or {}).get("type") or {})
            completed = bool(status_type.get("completed"))
            home_score = home.get("score") if completed else None
            away_score = away.get("score") if completed else None

            out.append({
                "idEvent": f"espn-soccer-{ev.get('id')}",
                "strEvent": ev.get("name") or f"{home_name} vs {away_name}",
                "strHomeTeam": home_name,
                "strAwayTeam": away_name,
                "strLeague": league_name,
                "strTimestamp": dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "intHomeScore": home_score,
                "intAwayScore": away_score,
            })
        time.sleep(ESPN_DELAY)
    return out


def _dedupe_key(ev: dict) -> tuple:
    """Kunci dedupe untuk gabungan event TSDB + ESPN: tim tuan rumah +
    tim tamu + tanggal WIB (lowercase, biar tidak sensitif kapital)."""
    return (
        (ev.get("strHomeTeam") or "").strip().lower(),
        (ev.get("strAwayTeam") or "").strip().lower(),
        event_wib_date(ev),
    )


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

    # Yang kita TAMPILKAN di pesan: hari ini + besok (WIB)
    keep_dates = {today_str, tomorrow_str}
    # Yang kita TANYAKAN ke API (TheSportsDB & ESPN): kemarin+hari ini+besok
    # (jaga-jaga selisih pencatatan tanggal UTC vs WIB)
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
        print(f"   ℹ️ {sport}: {len(events)} event dari TheSportsDB (sebelum cadangan ESPN)")

        # CADANGAN: kalau cabang Fighting dan TheSportsDB belum punya
        # event UFC untuk jendela ini, coba ambil dari ESPN.
        if sport == "Fighting":
            has_ufc = any("ufc" in (ev.get("strLeague") or "").lower() for ev in events)
            if not has_ufc:
                espn_events = fetch_espn_ufc(keep_dates)
                if espn_events:
                    print(f"   ℹ️ +{len(espn_events)} event UFC dari ESPN (cadangan)")
                events.extend(espn_events)

        # CADANGAN: Sepak Bola SELALU digabung dengan ESPN (liga favorit +
        # turnamen utama), karena TheSportsDB kunci "123" terbukti kadang
        # kosong total untuk cabang ini, bukan cuma "kadang hilang".
        if sport == "Soccer":
            espn_events = fetch_espn_soccer(query_dates, keep_dates)
            existing_keys = {_dedupe_key(ev) for ev in events}
            added = 0
            for ev in espn_events:
                key = _dedupe_key(ev)
                if key not in existing_keys:
                    events.append(ev)
                    existing_keys.add(key)
                    added += 1
            print(f"   ℹ️ +{added} event Sepak Bola dari ESPN (liga favorit & turnamen, setelah dedupe)")

        # 🔍 LOG DEBUG khusus turnamen besar Sepak Bola (cek di tab Actions
        # kalau ada laga turnamen yang kelihatannya hilang dari pesan)
        if sport == "Soccer":
            print(f"   ℹ️ Soccer: {len(events)} event total (query={query_dates}, keep={sorted(keep_dates)})")
            for ev in events:
                lg = ev.get("strLeague") or ""
                if any(k in lg.lower() for k in TOURNAMENT_KEYWORDS):
                    print(f"   ℹ️ Turnamen terdeteksi: {ev.get('strEvent')} | liga={lg} | ts={ev.get('strTimestamp')}")

        # Kelompokkan per liga
        by_league: dict[str, list[dict]] = {}
        for ev in events:
            lg = ev.get("strLeague") or "Lainnya"
            by_league.setdefault(lg, []).append(ev)

        # Untuk Soccer: hanya tampilkan turnamen + liga favorit (hindari spam
        # ratusan laga liga kecil sedunia). Cabang lain: tampilkan semua.
        keep_others = sport != "Soccer"

        ranked = []
        for lg, evs in by_league.items():
            rank = classify_league(lg)

            if rank == 2 and sport == "Soccer":
                # Liga/turnamen ini bukan favorit untuk Sepak Bola.
                # Tapi kalau Timnas Indonesia (atau tim di WATCH_TEAMS)
                # bermain di sini, tetap tampilkan laga itu saja.
                watched = [ev for ev in evs if is_watched_team(ev)]
                if watched:
                    ranked.append((1, lg, watched))
                continue

            if rank == 2 and not keep_others:
                continue

            ranked.append((rank, lg, evs))
        ranked.sort(key=lambda x: (x[0], x[1]))  # turnamen dulu, lalu abjad

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
# MAIN — jalan sekali lalu selesai
# ============================================================
if __name__ == "__main__":
    print(f"🏟️ Mengambil jadwal... ({datetime.now(WIB).strftime('%d-%m-%Y %H:%M WIB')})")
    msg = build_message()
    success = send_to_telegram(msg)
    sys.exit(0 if success else 1)
