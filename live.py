# -*- coding: utf-8 -*-
"""WC2026 live goal reporter — long-poll mode.

The workflow starts this script every 30 min (match hours); the script then
loops internally, polling football-data.org every ~60s for up to LOOP_MINUTES,
announcing kickoff / goals / half-time to Telegram as they happen.
State (live_state.json) is committed after every change to prevent duplicates.
Exits early when no match is live and none kicks off soon.
"""
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
FD_TOKEN = os.environ["FOOTBALL_DATA_TOKEN"]
LOOP_MINUTES = int(os.environ.get("LOOP_MINUTES", "28"))
POLL_SECONDS = 60
THAI_TZ = timezone(timedelta(hours=7))
BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "live_state.json")

TEAM_TH = {
    "Mexico": "เม็กซิโก", "South Africa": "แอฟริกาใต้", "Korea Republic": "เกาหลีใต้",
    "South Korea": "เกาหลีใต้", "Czechia": "เช็ก", "Czech Republic": "เช็ก",
    "Canada": "แคนาดา", "Bosnia and Herzegovina": "บอสเนียฯ", "United States": "สหรัฐอเมริกา",
    "USA": "สหรัฐอเมริกา", "Paraguay": "ปารากวัย", "Qatar": "กาตาร์",
    "Switzerland": "สวิตเซอร์แลนด์", "Brazil": "บราซิล", "Morocco": "โมร็อกโก",
    "Haiti": "เฮติ", "Scotland": "สกอตแลนด์", "Australia": "ออสเตรเลีย",
    "Türkiye": "ตุรกี", "Turkey": "ตุรกี", "Germany": "เยอรมนี",
    "Curaçao": "กือราเซา", "Curacao": "กือราเซา", "Netherlands": "เนเธอร์แลนด์",
    "Japan": "ญี่ปุ่น", "Côte d'Ivoire": "ไอวอรีโคสต์", "Ivory Coast": "ไอวอรีโคสต์",
    "Ecuador": "เอกวาดอร์", "Sweden": "สวีเดน", "Tunisia": "ตูนิเซีย",
    "Spain": "สเปน", "Cape Verde": "เคปเวิร์ด", "Belgium": "เบลเยียม",
    "Egypt": "อียิปต์", "Saudi Arabia": "ซาอุดีอาระเบีย", "Uruguay": "อุรุกวัย",
    "Iran": "อิหร่าน", "New Zealand": "นิวซีแลนด์", "France": "ฝรั่งเศส",
    "Senegal": "เซเนกัล", "Iraq": "อิรัก", "Norway": "นอร์เวย์",
    "Argentina": "อาร์เจนตินา", "Algeria": "แอลจีเรีย", "Austria": "ออสเตรีย",
    "Jordan": "จอร์แดน", "Portugal": "โปรตุเกส", "DR Congo": "ดีอาร์คองโก",
    "Congo DR": "ดีอาร์คองโก", "England": "อังกฤษ", "Croatia": "โครเอเชีย",
    "Ghana": "กานา", "Panama": "ปานามา", "Uzbekistan": "อุซเบกิสถาน",
    "Colombia": "โคลอมเบีย",
}


def th(name):
    return TEAM_TH.get(name, name)


def send(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    with urllib.request.urlopen(url, data=data, timeout=30) as resp:
        print("telegram:", resp.read().decode()[:100], flush=True)


def fetch_matches():
    today = datetime.now(THAI_TZ).date()
    d1 = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    d2 = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    req = urllib.request.Request(
        f"https://api.football-data.org/v4/competitions/WC/matches?dateFrom={d1}&dateTo={d2}",
        headers={"X-Auth-Token": FD_TOKEN},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read()).get("matches", [])


def commit_state():
    try:
        subprocess.run(["git", "add", STATE], cwd=BASE, check=True)
        subprocess.run(
            ["git", "-c", "user.name=wc26-live", "-c", "user.email=actions@github.com",
             "commit", "-m", "Update live state"], cwd=BASE, check=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=BASE, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=BASE, check=True)
    except subprocess.CalledProcessError as e:
        print("git error (non-fatal):", e, flush=True)


def process_once(state):
    """Return (changed, any_live, minutes_to_next_kickoff)."""
    changed = False
    any_live = False
    next_ko = None
    now_utc = datetime.utcnow()

    for m in fetch_matches():
        mid = str(m["id"])
        status = m.get("status", "")
        home, away = th(m["homeTeam"]["name"]), th(m["awayTeam"]["name"])
        ft = m.get("score", {}).get("fullTime", {})
        h = ft.get("home") or 0
        a = ft.get("away") or 0

        if status in ("TIMED", "SCHEDULED"):
            ko = datetime.strptime(m["utcDate"], "%Y-%m-%dT%H:%M:%SZ")
            mins = (ko - now_utc).total_seconds() / 60
            if mins > -5 and (next_ko is None or mins < next_ko):
                next_ko = mins
        elif status in ("IN_PLAY", "PAUSED"):
            any_live = True
            prev = state.get(mid)
            if prev is None:
                send(f"🔛 เกมเริ่มแล้ว! {home} พบ {away}")
                state[mid] = {"h": h, "a": a, "status": status}
                changed = True
                continue
            if (h, a) != (prev["h"], prev["a"]):
                scorer = home if h > prev["h"] else away
                send(f"⚽ GOAL! {scorer} ได้ประตู\n{home} {h} - {a} {away}")
                prev.update(h=h, a=a)
                changed = True
            if status == "PAUSED" and prev.get("status") != "PAUSED":
                send(f"⏸️ หมดครึ่งแรก: {home} {h} - {a} {away}")
                changed = True
            if status == "IN_PLAY" and prev.get("status") == "PAUSED":
                send(f"▶️ เริ่มครึ่งหลัง: {home} {h} - {a} {away}")
                changed = True
            if prev.get("status") != status:
                prev["status"] = status
                changed = True
        elif status == "FINISHED" and mid in state:
            del state[mid]  # FT ประกาศโดย wc26-bot
            changed = True

    return changed, any_live, next_ko


def main():
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    deadline = time.time() + LOOP_MINUTES * 60
    while time.time() < deadline:
        try:
            changed, any_live, next_ko = process_once(state)
            if changed:
                json.dump(state, open(STATE, "w"))
                commit_state()
            if not any_live and (next_ko is None or next_ko > 40):
                print("no live match and none starting soon -> exit", flush=True)
                break
        except Exception as e:
            print("poll error (will retry):", e, flush=True)
        time.sleep(POLL_SECONDS)
    print("loop done", flush=True)


if __name__ == "__main__":
    sys.exit(main())
