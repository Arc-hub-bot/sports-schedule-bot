"""
=====================================================================
 SPORTS SCHEDULE BOT — Versi GitHub Actions (100% GRATIS)
=====================================================================
 - Sumber data : TheSportsDB (gratis, TANPA API key)
 - Hosting     : GitHub Actions (gratis, tanpa kartu kredit)
 - Jadwal      : Otomatis tiap hari 08:00 WIB (diatur di
                 .github/workflows/jadwal.yml — bukan di file ini)
 - PC/laptop boleh mati total. Semua jalan di server GitHub.

 Script ini jalan SEKALI per eksekusi (ambil jadwal -> kirim ->
 selesai). Tidak ada loop, tidak ada library `schedule`.
=====================================================================
"""

import os
import sys
import time
from datetime import datetime, date, timezone
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
TSDB = "https://www.thesportsdb.com/api/v1/json/3"  # key "3" = key publik gratis
DELAY = 2  # jeda antar request (detik) agar aman dari rate limit

# ============================================================
# LIGA SEPAK BOLA (ID TheSportsDB — semua gratis)
# Mau tambah liga? Lihat panduan di PANDUAN.md bagian "Tambah Liga"
# ============================================================
SOCCER_LEAGUES = {
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League":        "4328",
    "🇪🇸 La Liga":                "4335",
    "🇩🇪 Bundesliga":             "4331",
    "🇮🇹 Serie A":                "4332",
    "🇫🇷 Ligue 1":                "4334",
    "🏆 UEFA Champions League":   "4480",
    "🏆 UEFA Europa League":      "4481",
}

# Liga yang ID-nya dicari otomatis berdasarkan nama (lebih aman)
SOCCER_LEAGUES_BY_SEARCH = [
    # (label tampilan, negara, kata kunci nama liga)
    ("🇮🇩 Liga 1 Indonesia", "Indonesia", "liga 1"),
]

# ============================================================
# OLAHRAGA LAIN
# ============================================================
OTHER_LEAGUES = {
    "🏀 NBA":     "4387",
    "🥋 UFC/MMA": "4443",
    "🥊 Boxing":  "4445",   # termasuk event boxing lokal jika terdaftar
}

# Ambil SEMUA event "Fighting" hari ini (menangkap Byon Combat,
# ONE Championship, dll yang tidak masuk daftar di atas)
EXTRA_SPORTS = [
    ("🥊 Fighting Lainnya (Byon Combat, ONE, dll)", "Fighting"),
]


# ============================================================
# UTIL
# ============================================================
def get_json(url: str) -> dict:
    """GET request dengan retry sederhana."""
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
            print(f"   ⚠️ HTTP {r.status_code} -> retry {attempt + 1}/3")
        except Exception as e:
            print(f"   ⚠️ {e} -> retry {attempt + 1}/3")
        time.sleep(3)
    return {}


def format_event(ev: dict) -> str:
    """Ubah 1 event TheSportsDB jadi 1 baris teks rapi (waktu WIB)."""
    home = ev.get("strHomeTeam") or ""
    away = ev.get("strAwayTeam") or ""
    title = f"{home} vs {away}" if home and away else (ev.get("strEvent") or "?")

    score_h = ev.get("intHomeScore")
    score_a = ev.get("intAwayScore")
    if score_h not in (None, "") and score_a not in (None, ""):
        return f"  ✅ {home} {score_h}–{score_a} {away} (Selesai)"

    # Konversi waktu UTC -> WIB
    ts = ev.get("strTimestamp")  # contoh: "2026-06-13T19:00:00"
    if ts:
        try:
            utc_dt = datetime.fromisoformat(ts.replace("Z", "")).replace(
                tzinfo=timezone.utc
            )
            wib = utc_dt.astimezone(WIB)
            return f"  🕐 {wib.strftime('%H:%M')} WIB | {title}"
        except Exception:
            pass
    t = ev.get("strTime") or "TBD"
    return f"  🕐 {t} | {title}"


def events_today_by_league(league_id: str) -> list[dict]:
    today = date.today().strftime("%Y-%m-%d")
    data = get_json(f"{TSDB}/eventsday.php?d={today}&l={league_id}")
    return data.get("events") or []


def events_today_by_sport(sport: str) -> list[dict]:
    today = date.today().strftime("%Y-%m-%d")
    data = get_json(f"{TSDB}/eventsday.php?d={today}&s={sport}")
    return data.get("events") or []


def find_league_id(country: str, keyword: str) -> str | None:
    """Cari ID liga otomatis berdasarkan negara + kata kunci nama."""
    data = get_json(f"{TSDB}/search_all_leagues.php?c={country}&s=Soccer")
    for lg in (data.get("countries") or data.get("countrys") or []):
        name = (lg.get("strLeague") or "").lower()
        if keyword.lower() in name:
            return lg.get("idLeague")
    return None


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
    lines = [
        "🏟️ *JADWAL OLAHRAGA HARI INI*",
        f"📅 {hari}, {now.strftime('%d %B %Y')}",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    # ---------- SEPAK BOLA ----------
    lines.append("\n⚽ *SEPAK BOLA*")
    any_soccer = False

    soccer = dict(SOCCER_LEAGUES)
    for label, country, keyword in SOCCER_LEAGUES_BY_SEARCH:
        lid = find_league_id(country, keyword)
        if lid:
            soccer[label] = lid
        time.sleep(DELAY)

    for name, lid in soccer.items():
        evs = events_today_by_league(lid)
        time.sleep(DELAY)
        if evs:
            any_soccer = True
            lines.append(f"\n{name}")
            lines += [format_event(e) for e in evs[:8]]
    if not any_soccer:
        lines.append("  Tidak ada pertandingan hari ini")

    # ---------- NBA / UFC / BOXING ----------
    for name, lid in OTHER_LEAGUES.items():
        lines.append(f"\n{name}")
        evs = events_today_by_league(lid)
        time.sleep(DELAY)
        if evs:
            lines += [format_event(e) for e in evs[:8]]
        else:
            lines.append("  Tidak ada event hari ini")

    # ---------- FIGHTING LAINNYA ----------
    known_fight_ids = set(OTHER_LEAGUES.values())
    for name, sport in EXTRA_SPORTS:
        evs = events_today_by_sport(sport)
        time.sleep(DELAY)
        evs = [e for e in evs if e.get("idLeague") not in known_fight_ids]
        if evs:
            lines.append(f"\n{name}")
            for e in evs[:8]:
                liga = e.get("strLeague") or ""
                lines.append(format_event(e) + (f"  _({liga})_" if liga else ""))

    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    lines.append("_Dikirim otomatis via GitHub Actions_ 🤖")
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
