"""
=====================================================================
 SPORTS SCHEDULE BOT — Versi GitHub Actions (100% GRATIS) — PINTAR
=====================================================================
 - Sumber data : TheSportsDB (gratis, TANPA API key pribadi)
                 + ESPN (gratis, tanpa key) sebagai CADANGAN untuk:
                     * UFC
                     * Liga sepak bola besar (EPL, La Liga, Serie A,
                       Bundesliga, Ligue 1, Liga Champions, Liga Europa)
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
   6) JENDELA TANGGAL AKURAT: TSDB kadang mencatat laga lewat tengah
      malam WIB di tanggal UTC sebelumnya. Bot mengambil data
      kemarin+hari ini+besok, lalu MENYARING ulang berdasarkan tanggal
      WIB asli tiap laga.
   7) BARU — SUMBER GANDA UNTUK LIGA SEPAK BOLA BESAR: Key publik TSDB
      "123" terbukti (dan didokumentasikan resmi oleh TheSportsDB serta
      pihak ketiga) dibatasi/di-rate-limit untuk liga bertrafik tinggi.
      Saat musim liga top Eropa bergulir penuh (Agu-Mei), TSDB kadang
      TIDAK mengembalikan data liga tsb sama sekali (silent drop) —
      sama seperti kasus Piala Dunia sebelumnya. Sekarang kalau TSDB
      kosong untuk liga favorit tertentu, bot otomatis ambil dari ESPN.
   8) BARU — MANUAL_EVENTS: daftar event yang tidak ada di TheSportsDB
      maupun ESPN (mis. promotor combat sport lokal seperti Byon
      Combat). Tinggal tambah/edit list ini untuk memasukkan event
      semacam itu secara manual.
   9) BARU — CABANG BULU TANGKIS & RUGBY ditambahkan (TheSportsDB punya
      kategori sport untuk keduanya). Bulu tangkis diberi filter yang
      sama seperti Sepak Bola (hanya turnamen besar + laga Timnas
      Indonesia) karena volume laga hariannya juga sangat besar
      (banyak babak penyisihan). Rugby ditampilkan semua seperti Basket.
  10) BARU — WATCH_TEAMS (Timnas Indonesia) sekarang berlaku juga di
      Bulu Tangkis, tidak cuma Sepak Bola. CATATAN: untuk nomor
      tunggal/ganda, TheSportsDB kadang mencatat nama PEMAIN, bukan
      "Indonesia" sebagai tim -- jadi deteksi ini paling akurat untuk
      format beregu (Piala Thomas/Uber/Sudirman).
  11) CATATAN TENTANG PON: Setelah dicek, PON (Pekan Olahraga Nasional)
      TIDAK terindeks di TheSportsDB maupun ESPN -- ini event domestik
      Indonesia, di luar cakupan kedua sumber data gratis ini. Kalau
      ada laga PON spesifik yang mau ditampilkan, tambahkan manual ke
      MANUAL_EVENTS di bawah.
  12) BARU — 4 CABANG POPULER TAMBAHAN: Tenis, Cricket, Motorsport
      (F1/MotoGP/dll), Voli. Tenis & Cricket diberi filter ketat
      (RESTRICTED_SPORTS) karena volume laga hariannya sangat besar
      (ratusan match ATP/WTA/liga T20 tersebar di seluruh dunia).
      Motorsport & Voli ditampilkan apa adanya (volume jauh lebih
      kecil/terkendali).
  13) BARU — TINJU (BOXING) DIPISAH DARI MMA: dalam satu section
      "TINJU & MMA", sekarang ada 2 sub-judul terpisah: "Tinju (Boxing)"
      dan "MMA & Combat Sports Lain" (UFC/ONE/Byon/dll), supaya tidak
      bercampur dalam satu daftar panjang.

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

# ESPN — API publik gratis tanpa key, dipakai sebagai CADANGAN
ESPN_UFC_URL = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"
ESPN_SOCCER_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

DELAY = 2          # jeda antar panggilan API (detik) — aman dari rate limit
MAX_PER_LEAGUE = 12  # maksimal pertandingan ditampilkan per liga

# ============================================================
# CABANG OLAHRAGA YANG DIPANTAU
# ============================================================
SPORTS = ["Soccer", "Basketball", "Fighting", "Badminton", "Rugby",
          "Tennis", "Cricket", "Motorsport", "Volleyball"]

SPORT_HEADER = {
    "Soccer": "⚽ *SEPAK BOLA*",
    "Basketball": "🏀 *BASKET*",
    "Fighting": "🥊 *TINJU & MMA*",
    "Badminton": "🏸 *BULU TANGKIS*",
    "Rugby": "🏉 *RUGBY*",
    "Tennis": "🎾 *TENIS*",
    "Cricket": "🏏 *CRICKET*",
    "Motorsport": "🏎️ *MOTORSPORT (F1/MotoGP/dll)*",
    "Volleyball": "🏐 *VOLI*",
}

# Cabang dengan volume laga harian sangat besar (banyak babak penyisihan
# tersebar di banyak liga/turnamen kecil sedunia) -> hanya tampilkan
# turnamen besar + liga favorit + laga tim yang dipantau (WATCH_TEAMS).
# Cabang lain (Basket, Fighting, Rugby, Motorsport, Voli) ditampilkan
# apa adanya karena volume hariannya jauh lebih kecil/terkendali.
RESTRICTED_SPORTS = {"Soccer", "Badminton", "Tennis", "Cricket"}

# ============================================================
# AUTO-DETEKSI TURNAMEN (berdasarkan NAMA liga, bukan ID)
# ============================================================
TOURNAMENT_KEYWORDS = [
    "world cup", "club world cup", "champions league", "europa league",
    "conference league", "nations league", "copa america", "copa libertadores",
    "copa sudamericana", "european championship", "euro 20", "afcon",
    "africa cup", "asian cup", "gold cup", "confederations", "olympic",
    "super cup", "world championship", "grand prix", "finals",
    "sea games", "asian games",  # ajang multi-cabang (Soccer/Basket di sini
                                  # otomatis ikut tertangkap; cabang lain di
                                  # ajang ini di luar cakupan bot -> lihat catatan 9)
]

FAVORITE_KEYWORDS = [
    "premier league", "la liga", "serie a", "bundesliga", "ligue 1",
    "eredivisie", "primeira liga", "liga 1", "mls",          # bola
    "nba", "euroleague",                                     # basket
    "ufc", "one championship", "byon", "pfl", "bellator", "boxing",  # fighting
    "real american freestyle",
    "bwf", "all england", "thomas cup", "uber cup", "sudirman cup",
    "indonesia open", "china open", "denmark open", "malaysia open",
    "india open", "japan open", "world tour finals",          # bulu tangkis
    "six nations", "rugby championship", "super rugby", "top 14",
    "premiership rugby", "united rugby championship",         # rugby
    # "rugby world cup" otomatis ikut TOURNAMENT_KEYWORDS ("world cup")
    "atp", "wta", "wimbledon", "us open", "french open",
    "roland garros", "australian open",                       # tenis
    "ipl", "big bash", "the ashes", "icc", "psl", "t20",       # cricket
    "formula 1", "formula e", "motogp", "nascar", "indycar",   # motorsport
    "fivb", "volleyball nations league", "cev champions league",  # voli
]

WATCH_TEAMS = [
    "indonesia",
]

# ============================================================
# CADANGAN ESPN UNTUK LIGA SEPAK BOLA BESAR
# keyword (dicek terhadap nama liga TSDB, lowercase) -> (label tampil, slug ESPN)
# Dipanggil HANYA kalau TSDB tidak punya data liga ini di jendela tanggal
# ini (hemat API call + tidak duplikat).
# CATATAN: endpoint ESPN ini tidak resmi/tidak didokumentasikan —
# fragile, bisa berubah sewaktu-waktu tanpa pemberitahuan.
# ============================================================
ESPN_SOCCER_FALLBACK = {
    "premier league": ("English Premier League", "eng.1"),
    "la liga": ("Spanish La Liga", "esp.1"),
    "serie a": ("Italian Serie A", "ita.1"),
    "bundesliga": ("German Bundesliga", "ger.1"),
    "ligue 1": ("French Ligue 1", "fra.1"),
    "champions league": ("UEFA Champions League", "uefa.champions"),
    "europa league": ("UEFA Europa League", "uefa.europa"),
}

# ============================================================
# MANUAL EVENTS — event yang TIDAK ADA di TheSportsDB / ESPN
# (mis. promotor combat sport lokal). Tambah/edit di sini kapan pun.
#
# Field:
#   sport     : harus salah satu dari SPORTS di atas
#   league    : nama liga/promotor (dipakai untuk grouping tampilan)
#   title     : judul laga yang ditampilkan
#   date_wib  : tanggal laga dalam WIB, format "YYYY-MM-DD"
#   time_wib  : jam mulai WIB (string). Isi "TBD" kalau belum ada
#               pengumuman resmi — nanti update manual saat sudah ada.
# ============================================================
MANUAL_EVENTS = [
    {
        "sport": "Fighting",
        "league": "Byon Combat",
        "title": "Jeka Saragih vs Ammarul Shafiq — Byon Combat Showbiz 8 "
                  "(Tennis Indoor Senayan, Jakarta)",
        "date_wib": "2026-08-29",
        # Jam resmi belum diumumkan publik per pengecekan terakhir.
        # Update baris ini begitu jadwal siaran/jam resmi keluar.
        "time_wib": "TBD",
    },
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
    home = (ev.get("strHomeTeam") or "").lower()
    away = (ev.get("strAwayTeam") or "").lower()
    return any(t in home or t in away for t in WATCH_TEAMS)


def event_wib_date(ev: dict) -> str | None:
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


def fetch_sport_window(sport: str, query_dates: list[str], keep_dates: set[str]) -> list[dict]:
    """Ambil event satu cabang olahraga dari TSDB untuk QUERY_DATES,
    lalu hanya simpan yang tanggal WIB aslinya ada di KEEP_DATES."""
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
    """CADANGAN khusus UFC dari ESPN."""
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


def fetch_espn_soccer(slug: str, league_label: str, date_from: str, date_to: str,
                       keep_dates: set[str]) -> list[dict]:
    """CADANGAN liga sepak bola besar dari ESPN. Dipanggil ketika TSDB
    tidak mengembalikan data untuk liga ini di jendela tanggal ini —
    biasanya karena key publik '123' dibatasi/di-rate-limit untuk liga
    bertrafik tinggi saat musim reguler sedang berjalan."""
    url = f"{ESPN_SOCCER_BASE}/{slug}/scoreboard?dates={date_from}-{date_to}"
    data = get_json(url)
    out = []

    for ev in (data.get("events") or []):
        date_iso = ev.get("date")
        if not date_iso:
            continue
        try:
            dt_utc = datetime.fromisoformat(date_iso.replace("Z", "")).replace(
                tzinfo=timezone.utc
            )
            ev_date_wib = dt_utc.astimezone(WIB).strftime("%Y-%m-%d")
        except Exception:
            continue

        if ev_date_wib not in keep_dates:
            continue

        comp = (ev.get("competitions") or [{}])[0]
        home = away = ""
        home_score = away_score = None
        for c in comp.get("competitors", []):
            name = (c.get("team") or {}).get("displayName", "")
            if c.get("homeAway") == "home":
                home, home_score = name, c.get("score")
            else:
                away, away_score = name, c.get("score")

        completed = ((comp.get("status") or {}).get("type") or {}).get("completed", False)

        out.append({
            "idEvent": f"espn-{slug}-{ev.get('id')}",
            "strEvent": ev.get("name") or (f"{home} vs {away}" if home and away else "?"),
            "strHomeTeam": home,
            "strAwayTeam": away,
            "strLeague": league_label,
            "strTimestamp": date_iso.replace("Z", ""),
            "intHomeScore": home_score if completed else None,
            "intAwayScore": away_score if completed else None,
        })

    time.sleep(DELAY)
    return out


def augment_soccer_with_espn(events: list[dict], query_dates: list[str],
                              keep_dates: set[str]) -> list[dict]:
    """Kalau TSDB tidak punya data untuk liga favorit tertentu dalam
    jendela ini, ambil dari ESPN sebagai cadangan. Liga yang SUDAH ada
    datanya dari TSDB tidak dipanggil ulang ke ESPN (hemat API call,
    hindari duplikat)."""
    existing_leagues_low = {(ev.get("strLeague") or "").lower() for ev in events}
    date_from = query_dates[0].replace("-", "")
    date_to = query_dates[-1].replace("-", "")

    for keyword, (label, slug) in ESPN_SOCCER_FALLBACK.items():
        if any(keyword in lg for lg in existing_leagues_low):
            continue  # TSDB sudah punya liga ini -> skip cadangan
        espn_events = fetch_espn_soccer(slug, label, date_from, date_to, keep_dates)
        if espn_events:
            print(f"   ℹ️ +{len(espn_events)} laga {label} dari ESPN (cadangan, TSDB kosong)")
            events.extend(espn_events)
    return events


def get_manual_events(sport: str, keep_dates: set[str]) -> list[dict]:
    """Event yang tidak tersedia di API mana pun (mis. Byon Combat).
    Diedit lewat MANUAL_EVENTS di atas."""
    out = []
    for m in MANUAL_EVENTS:
        if m.get("sport") != sport:
            continue
        if m.get("date_wib") not in keep_dates:
            continue
        out.append({
            "idEvent": f"manual-{m['league']}-{m['date_wib']}",
            "strEvent": m["title"],
            "strHomeTeam": "",
            "strAwayTeam": "",
            "strLeague": m["league"],
            "strTimestamp": None,
            "strTime": m.get("time_wib", "TBD"),
            "intHomeScore": None,
            "intAwayScore": None,
        })
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

        # CADANGAN: liga sepak bola besar yang kosong di TSDB -> coba ESPN
        if sport == "Soccer":
            events = augment_soccer_with_espn(events, query_dates, keep_dates)

        # CADANGAN: UFC kosong di TSDB -> coba ESPN
        if sport == "Fighting":
            has_ufc = any("ufc" in (ev.get("strLeague") or "").lower() for ev in events)
            if not has_ufc:
                espn_events = fetch_espn_ufc(keep_dates)
                if espn_events:
                    print(f"   ℹ️ +{len(espn_events)} event UFC dari ESPN (cadangan)")
                events.extend(espn_events)

        # MANUAL: event yang tidak ada di API mana pun (mis. Byon Combat)
        events.extend(get_manual_events(sport, keep_dates))

        if sport in RESTRICTED_SPORTS:
            print(f"   ℹ️ {sport}: {len(events)} event (query={query_dates}, keep={sorted(keep_dates)})")
            for ev in events:
                lg = ev.get("strLeague") or ""
                if any(k in lg.lower() for k in TOURNAMENT_KEYWORDS):
                    print(f"   ℹ️ Turnamen terdeteksi: {ev.get('strEvent')} | liga={lg} | ts={ev.get('strTimestamp')}")

        by_league: dict[str, list[dict]] = {}
        for ev in events:
            lg = ev.get("strLeague") or "Lainnya"
            by_league.setdefault(lg, []).append(ev)

        keep_others = sport not in RESTRICTED_SPORTS

        ranked = []
        for lg, evs in by_league.items():
            rank = classify_league(lg)

            if rank == 2 and sport in RESTRICTED_SPORTS:
                # Liga/turnamen ini bukan favorit -> hanya tampilkan kalau
                # tim yang dipantau (mis. Timnas Indonesia) bermain di sini.
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

        if sport == "Fighting":
            # Pisahkan tampilan: Tinju (Boxing) vs MMA & Combat Sports lain,
            # supaya tidak campur aduk dalam satu daftar panjang.
            boxing_ranked = [r for r in ranked if "boxing" in r[1].lower()]
            mma_ranked = [r for r in ranked if "boxing" not in r[1].lower()]

            if boxing_ranked:
                lines.append("\n🥊 *Tinju (Boxing)*")
                for rank, lg, evs in boxing_ranked:
                    tag = "🏆 " if rank == 0 else "▪️ "
                    lines.append(f"\n{tag}*{lg}*")
                    for ev in evs[:MAX_PER_LEAGUE]:
                        lines.append(format_event(ev))
                        lines.append("")

            if mma_ranked:
                lines.append("\n🤼 *MMA & Combat Sports Lain*")
                for rank, lg, evs in mma_ranked:
                    tag = "🏆 " if rank == 0 else "▪️ "
                    lines.append(f"\n{tag}*{lg}*")
                    for ev in evs[:MAX_PER_LEAGUE]:
                        lines.append(format_event(ev))
                        lines.append("")
        else:
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
