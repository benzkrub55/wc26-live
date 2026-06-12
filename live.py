# -*- coding: utf-8 -*-
"""WC2026 live goal reporter (runs every ~5 min during match hours).

Polls football-data.org for in-play matches and announces:
  * kickoff (first time a match is seen in play)
  * every score change (goal), with which side scored
  * half-time
Full-time announcements are handled by wc26-bot/results.py, not here.
State lives in live_state.json (committed by the workflow).
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
FD_TOKEN = os.environ["FOOTBALL_DATA_TOKEN"]
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
        print("telegram:", resp.read().decode()[:100])


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


def main():
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    changed = False

    for m in fetch_matches():
        mid = str(m["id"])
        status = m.get("status", "")
        home, away = th(m["homeTeam"]["name"]), th(m["awayTeam"]["name"])
        ft = m.get("score", {}).get("fullTime", {})
        h = ft.get("home") or 0
        a = ft.get("away") or 0

        if status in ("IN_PLAY", "PAUSED"):
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
            if prev.get("status") != status:
                prev["status"] = status
                changed = True
        elif status == "FINISHED" and mid in state:
            del state[mid]  # FT ประกาศโดย wc26-bot อยู่แล้ว
            changed = True

    if changed:
        json.dump(state, open(STATE, "w"))
    print(f"state changed: {changed}, tracking {len(state)} match(es)")


if __name__ == "__main__":
    sys.exit(main())
