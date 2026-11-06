import json,re
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
PAGES=["https://www.vbet.com/uk/sports/pre-match/results","https://m.vbet.am/en/sports/pre-match/results","https://pagebuilderm.vbet.am/en/sports/pre-match/results"]
H={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"}
s=requests.Session();s.headers.update(H)
report={"pages":[],"assets":[],"swarm_hosts":[],"api_candidates":[]}
queue=[];seen=set()
for page in PAGES:
 try:
  r=s.get(page,timeout=30);r.raise_for_status(); soup=BeautifulSoup(r.text,"html.parser")
  assets=[urljoin(page,x.get("href")) for x in soup.select('link[rel="modulepreload"][href]')]
  assets += [urljoin(page,x.get("src")) for x in soup.select('script[src]')]
  report["pages"].append({"url":page,"status":r.status_code,"assets":len(set(assets))})
  queue.extend(assets)
 except Exception as e:report["pages"].append({"url":page,"error":str(e)[:160]})
terms=["eu-swarm-newm","eu-swarm-ws","swarm","socketurl","longpollingurl","betual","results","result","events","eventdispatcher","sportsbook","apiurl","baseurl","getevents","geteventlist","geteventview","geteventdetails","competition","tournament","subscribe","subscription","sendmessage","request","finished","score","period","statistics","virtual"]
while queue and len(seen)<260:
 u=queue.pop(0)
 if u in seen:continue
 seen.add(u)
 try:
  r=s.get(u,timeout=20)
  if r.status_code!=200 or len(r.content)>5_000_000:continue
  body=r.text
  hits={}
  for term in terms:
   pos=[m.start() for m in re.finditer(re.escape(term),body,re.I)][:8]
   if pos:hits[term]=[body[max(0,i-220):i+500] for i in pos[:4]]
  if hits:report["assets"].append({"url":u,"bytes":len(r.content),"hits":hits})
  if any(k in u.lower() for k in ["swarm","sportsbookdata","eventviewfilters","eventdispatcher","sportsbook."]) or any(k in hits for k in ["betual","results","finished","score","virtual","getevents","geteventlist","geteventview","competition","tournament"]):
   Path("data/js_inspection").mkdir(parents=True,exist_ok=True)
   safe=re.sub(r"[^a-zA-Z0-9_.-]","_",u.rsplit("/",1)[-1])
   Path("data/js_inspection/"+safe+".js").write_text(body,encoding="utf-8")
  # Follow relative JS imports and preload chunks recursively.
  for path in re.findall(r'(?:from|import\s*\()\s*["\']([^"\']+\.js)["\']',body):
   queue.append(urljoin(u,path))
  for path in re.findall(r'["\']([^"\']+\.js)["\']',body):
   if path.startswith(("/assets/","./")):queue.append(urljoin(u,path))
  for v in re.findall(r'https?://[^\s<>"]+',body):
   v=v.rstrip(");,")
   if any(k in v.lower() for k in ["swarm","api","betconstruct"]) and v not in report["swarm_hosts"]:report["swarm_hosts"].append(v)
  for v in re.findall(r'["\'](/[^"\']{2,160})["\']',body):
   if any(k in v.lower() for k in ["event","result","sport","match","competition"]) and v not in report["api_candidates"]:report["api_candidates"].append(v)
 except Exception as e:report["assets"].append({"url":u,"error":str(e)[:120]})
Path("data/api_research.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"pages":len(report["pages"]),"assets_scanned":len(seen),"interesting_assets":len(report["assets"]),"swarm_hosts":report["swarm_hosts"][:30],"api_candidates":report["api_candidates"][:80]},ensure_ascii=False,indent=2))


# BetConstruct Swarm results API probe. Virtual category is sport_type=1
# (the same category enum used by the sportsbook frontend).
from datetime import datetime, timedelta, timezone
SWARM_LP = "https://eu-swarm-lp.betconstruct.com/"
SWARM_SITE_ID = 0  # VBET public frontend config: app.site_id=0
def swarm_call(payload, sid=None):
    headers = dict(H)
    headers["Content-Type"] = "application/json"
    if sid:
        headers["swarm-session"] = sid
    response = s.post(SWARM_LP, json=payload, headers=headers, timeout=35)
    response.raise_for_status()
    return response.json()

def score_pair(value):
    if not value:
        return None
    m = re.search(r"(\d+)\s*:\s*(\d+)", str(value))
    return (int(m.group(1)), int(m.group(2))) if m else None

def collect_swarm_results():
    probe = {"endpoint": SWARM_LP, "site_id": SWARM_SITE_ID, "sport_type": 1,
             "status": "not_started", "result_count": 0, "errors": []}
    try:
        session = swarm_call({"command":"request_session",
                              "params":{"site_id":SWARM_SITE_ID,"language":"eng"}})
        probe["session_response"] = session
        sid = (session.get("data") or {}).get("sid")
        if not sid:
            raise RuntimeError("Swarm oturumu açılamadı; SID dönmedi.")
        now = datetime.now(timezone.utc)
        params = {
            "from_date": int((now - timedelta(days=30)).timestamp()),
            "to_date": int(now.timestamp()),
            "sport_type": 1
        }
        response = swarm_call({"command":"get_result_games","params":params}, sid)
        probe["results_response_code"] = response.get("code")
        if response.get("code") != 0:
            raise RuntimeError("get_result_games hata yanıtı: " + str(response)[:700])
        data = response.get("data") or {}
        games = ((data.get("games") or {}).get("game") or [])
        if isinstance(games, dict):
            games = list(games.values())
        parsed = []
        for g in games:
            name = str(g.get("game_name") or "")
            if " - " not in name:
                continue
            home, away = name.split(" - ", 1)
            ft = score_pair(g.get("scores"))
            ht = score_pair(g.get("scores1"))
            if not ft:
                continue
            parsed.append({
                "home_team": home.strip(), "away_team": away.strip(),
                "ft_home": ft[0], "ft_away": ft[1],
                "ht_home": ht[0] if ht else None,
                "ht_away": ht[1] if ht else None,
                "date": g.get("date"), "game_id": str(g.get("game_id") or ""),
                "sport_id": str(g.get("sport_id") or ""),
                "competition": g.get("competition_name") or "",
                "source": "BetConstruct Swarm get_result_games sport_type=1"
            })
        probe["status"] = "success"
        probe["result_count"] = len(parsed)
        probe["sample"] = parsed[:3]
        path = Path("data/matches.json")
        previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        old = previous.get("matches", [])
        merged = {str(x.get("game_id") or (x.get("date"),x.get("home_team"),x.get("away_team"))): x
                  for x in old}
        for x in parsed:
            merged[x["game_id"] or (x["date"],x["home_team"],x["away_team"])] = x
        all_matches = list(merged.values())
        all_matches.sort(key=lambda x: str(x.get("date") or ""))
        Path("data").mkdir(exist_ok=True)
        path.write_text(json.dumps({
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "match_count": len(all_matches),
            "sources": [{"url": SWARM_LP, "method":"get_result_games",
                         "sport_type":1, "window_days":30}],
            "matches": all_matches
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        probe["status"] = "failed"
        probe["errors"].append(str(exc)[:1000])
    Path("data/source_probe.json").write_text(json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SWARM_RESULTS_PROBE=" + json.dumps({k:v for k,v in probe.items() if k not in ("session_response","sample")}, ensure_ascii=False))
    return probe

collect_swarm_results()


# Mackolik public match-list API probe (kept separate until schema is verified).
def probe_mackolik():
    from datetime import datetime, timedelta
    probe = {"endpoint":"https://goapi.mackolik.com/livedata", "status":"not_tested",
             "dates_tested":[], "match_count":0, "errors":[], "sample":[]}
    found = []
    for offset in (0, -1, 1):
        day = datetime.now() + timedelta(days=offset)
        date_text = day.strftime("%d/%m/%Y")
        probe["dates_tested"].append(date_text)
        try:
            url = "https://goapi.mackolik.com/livedata"
            response = s.get(url, params={"date":date_text}, timeout=25)
            item = {"date":date_text, "http_status":response.status_code,
                    "content_type":response.headers.get("content-type","")}
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("m", []) if isinstance(payload, dict) else []
            item["row_count"] = len(rows) if isinstance(rows, list) else 0
            item["sample_row"] = rows[0] if isinstance(rows, list) and rows else None
            probe.setdefault("responses", []).append(item)
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, list) or len(row) < 9:
                        continue
                    home, away = str(row[2] or "").strip(), str(row[4] or "").strip()
                    if not home or not away:
                        continue
                    found.append({"date":row[0], "league":row[4] if len(row)>4 else "",
                                  "home_team":home, "away_team":away,
                                  "ht_raw":row[7], "ft_raw":row[8],
                                  "source":"Mackolik livedata"})
        except Exception as exc:
            probe["errors"].append(date_text + ": " + str(exc)[:300])
    probe["match_count"] = len(found)
    probe["sample"] = found[:8]
    probe["status"] = "success" if probe.get("responses") else "failed"
    Path("data/mackolik_probe.json").write_text(
        json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
    print("MACKOLIK_PROBE=" + json.dumps(
        {k:v for k,v in probe.items() if k not in ("sample",)}, ensure_ascii=False))
    return probe

probe_mackolik()
