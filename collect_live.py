import json, re
from datetime import datetime, timezone
from pathlib import Path
import requests

URL = "https://eu-swarm-lp.betconstruct.com/"
HEADERS = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}

def call(payload, sid=None):
    h = dict(HEADERS)
    if sid:
        h["swarm-session"] = sid
    r = requests.post(URL, json=payload, headers=h, timeout=12)
    r.raise_for_status()
    return r.json()

def as_int(v):
    try:
        s = str(v).strip()
        return int(s) if re.fullmatch(r"-?\\d+", s) else None
    except Exception:
        return None

def main():
    fetched = datetime.now(timezone.utc).isoformat()
    session = call({"command":"request_session","params":{"site_id":0,"language":"eng"}})
    sid = (session.get("data") or {}).get("sid")
    if not sid:
        raise RuntimeError("Swarm session unavailable")
    fields = ["id","team1_name","team2_name","start_ts","is_live","sport_id","competition_id","competition_name","info","stats","score1","score2","status","timer","game_time"]
    response = call({"command":"get","params":{"source":"betting","what":{"game":fields},"where":{"game":{"is_live":1}}}}, sid)
    if response.get("code") != 0:
        raise RuntimeError("Swarm live query failed: " + str(response.get("code")))
    data = response.get("data") or {}
    nested = data.get("data") or data
    raw = nested.get("game", {}) if isinstance(nested, dict) else {}
    rows = list(raw.values()) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
    matches = []
    for g in rows:
        if not isinstance(g, dict):
            continue
        home, away = str(g.get("team1_name") or ""), str(g.get("team2_name") or "")
        if "virtual" not in (home + " " + away).lower():
            continue
        info = g.get("info") if isinstance(g.get("info"), dict) else {}
        stats = g.get("stats") if isinstance(g.get("stats"), dict) else {}
        sh, sa = as_int(info.get("score1", g.get("score1"))), as_int(info.get("score2", g.get("score2")))
        clock = str(info.get("current_game_time") or g.get("game_time") or g.get("timer") or "").strip()
        state = str(info.get("current_game_state") or g.get("status") or "").strip().lower()
        period = ("first_half" if state in ("set1","set_1","period1","period_1") or any(x in state for x in ("first","1st","half1","period1")) else
                  "second_half" if state in ("set2","set_2","period2","period_2") or any(x in state for x in ("second","2nd","half2","period2")) else None)
        m = re.fullmatch(r"(\\d{1,2})(?::(\\d{2}))?", clock)
        elapsed = int(m.group(1)) + int(m.group(2) or 0)/60 if m else None
        minute = None
        if elapsed is not None and period == "first_half":
            if (":" in clock and 0 <= elapsed <= 17) or (m and not m.group(2) and 0 <= elapsed <= 15):
                minute = round(elapsed * 3)
        elif elapsed is not None and period == "second_half":
            if (":" in clock and 0 <= elapsed <= 17):
                minute = round((15 + elapsed) * 3)
            elif m and not m.group(2) and 0 <= elapsed <= 45:
                minute = round(45 + elapsed)
        goals = stats.get("goal") if isinstance(stats.get("goal"), dict) else {}
        gh, ga = as_int(goals.get("team1_value")), as_int(goals.get("team2_value"))
        agree = (gh is None or gh == sh) and (ga is None or ga == sa)
        verified = sh is not None and sa is not None and minute is not None and period is not None and agree and str(g.get("is_live")) == "1"
        matches.append({"game_id":str(g.get("id") or ""),"home_team":home,"away_team":away,"start_ts":g.get("start_ts"),"is_live":g.get("is_live"),"competition_id":g.get("competition_id"),"competition":g.get("competition_name"),"home_score":sh,"away_score":sa,"minute":minute,"period":period,"live_state_verified":verified,"score_stats_agree":agree,"display_clock":clock,"current_game_state":state,"raw_score_fields":{"info":info,"stats":stats},"source":"BetConstruct Swarm live betting catalogue game.info"})
    Path("data").mkdir(exist_ok=True)
    Path("data/betual_live_games.json").write_text(json.dumps({"updated_at":fetched,"source_fetched_at":fetched,"count":len(matches),"matches":matches},ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"source_fetched_at":fetched,"count":len(matches),"verified":sum(1 for x in matches if x["live_state_verified"])}))

if __name__ == "__main__":
    main()
