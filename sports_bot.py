"""
=====================================================================
 SPORTS SCHEDULE BOT — Versi GitHub Actions (100% GRATIS) — PINTAR
=====================================================================
 - Sumber data : TheSportsDB (gratis, TANPA API key pribadi)
                 + ESPN (gratis, tanpa key) sebagai CADANGAN khusus UFC
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
   6) JENDELA TANGGAL AKURAT (BARU): TSDB kadang mencatat laga lewat
      tengah malam WIB (mis. World Cup jam 03:00 WIB) di tanggal UTC
      sebelumnya. Bot sekarang mengambil data kemarin+hari ini+besok,
      lalu MENYARING ulang berdasarkan tanggal WIB asli tiap laga —
      jadi laga seperti ini tidak hilang lagi.
 
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
TSDB_KEY = "123"
TSDB = f"https://www.thesportsdb.com/api/v1/json/{TSDB_KEY}"
 
# ESPN — API publik gratis tanpa key, dipakai sebagai CADANGAN untuk UFC
ESPN_UFC_URL = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"
 
DELAY = 2          # jeda antar panggilan API (detik) — aman dari rate limit
MAX_PER_LEAGUE = 12  # maksimal pertandingan ditampilkan per liga
 
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
    # Yang kita TANYAKAN ke TheSportsDB: kemarin+hari ini+besok
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
 
        # CADANGAN: kalau cabang Fighting dan TheSportsDB belum punya
        # event UFC untuk jendela ini, coba ambil dari ESPN.
        if sport == "Fighting":
            has_ufc = any("ufc" in (ev.get("strLeague") or "").lower() for ev in events)
            if not has_ufc:
                espn_events = fetch_espn_ufc(keep_dates)
                if espn_events:
                    print(f"   ℹ️ +{len(espn_events)} event UFC dari ESPN (cadangan)")
                events.extend(espn_events)
 
        # 🔍 LOG DEBUG khusus turnamen besar Sepak Bola (cek di tab Actions
        # kalau ada laga turnamen yang kelihatannya hilang dari pesan)
        if sport == "Soccer":
            print(f"   ℹ️ Soccer: {len(events)} event (query={query_dates}, keep={sorted(keep_dates)})")
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
