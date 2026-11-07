import json,re
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
PAGES=["https://www.vbet.com/uk/sports/pre-match/results","https://m.vbet.am/en/sports/pre-match/results","https://pagebuilderm.vbet.am/en/sports/pre-match/results","https://www.vbet.com/en/sports/pre-match/results"]
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

# Correct Swarm catalogue discovery: sport.type=1 means Virtual. The old
# get_result_games(sport_type=1) call alone was not a reliable virtual filter.
def collect_virtual_swarm_results():
    from datetime import datetime, timedelta, timezone
    diag={"status":"not_started","sports":[],"queries":[],"errors":[]}
    try:
        sess=swarm_call({"command":"request_session","params":{"site_id":SWARM_SITE_ID,"language":"eng"}})
        sid=(sess.get("data") or {}).get("sid")
        if not sid: raise RuntimeError("Swarm SID alınamadı")
        def get(params):
            return swarm_call({"command":"get","params":params},sid)
        sport_resp=get({"source":"betting","what":{"sport":["id","name","alias","type"]},"where":{"sport":{"type":1}}})
        sport_data=(sport_resp.get("data") or {}).get("data") or sport_resp.get("data") or {}
        sports=sport_data.get("sport") or {}
        if isinstance(sports,list): sports={str(x.get("id")):x for x in sports}
        for k,v in sports.items():
            if isinstance(v,dict):
                v.setdefault("id",k)
                if str(v.get("type"))=="1": diag["sports"].append(v)
        now=datetime.now(timezone.utc)
        params={"from_date":int((now-timedelta(days=45)).timestamp()),
                "to_date":int((now+timedelta(hours=1)).timestamp())}
        collected=[]
        for sp in diag["sports"]:
            sport_id=int(sp.get("id"))
            for label,extra in [("sport_id",{"sport_id":sport_id}),("sport_id_type",{"sport_id":sport_id,"sport_type":1})]:
                try:
                    res=swarm_call({"command":"get_result_games","params":dict(params,**extra)},sid)
                    data=res.get("data") or {}
                    games=((data.get("games") or {}).get("game") or [])
                    if isinstance(games,dict): games=list(games.values())
                    diag["queries"].append({"sport_id":sport_id,"variant":label,"code":res.get("code"),"count":len(games)})
                    for g in games:
                        comp=str(g.get("competition_name") or "")
                        name=str(g.get("game_name") or "")
                        if "virtual" not in (comp+" "+name+" "+str(sp.get("name",""))).lower(): continue
                        ft=score_pair(g.get("scores")); ht=score_pair(g.get("scores1"))
                        if not ft or not ht: continue
                        if " - " not in name: continue
                        home,away=name.split(" - ",1)
                        collected.append({"home_team":home.strip(),"away_team":away.strip(),
                          "ft_home":ft[0],"ft_away":ft[1],"ht_home":ht[0],"ht_away":ht[1],
                          "date":g.get("date"),"game_id":str(g.get("game_id") or ""),
                          "sport_id":str(sport_id),"competition":comp,
                          "source":"BetConstruct Swarm get_result_games filtered by sport.type=1"})
                    if games: break
                except Exception as e: diag["errors"].append("sport "+str(sport_id)+" "+label+": "+str(e)[:250])
        path=Path("data/matches.json")
        previous=json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else {}
        old=previous.get("matches",[])
        merged={}
        for x in old+collected:
            key=str(x.get("game_id") or (x.get("competition"),x.get("date"),x.get("home_team"),x.get("away_team")))
            merged[key]=x
        all_matches=sorted(merged.values(),key=lambda x:str(x.get("date") or ""))
        Path("data").mkdir(exist_ok=True)
        Path("data/matches.json").write_text(json.dumps({"updated_at":datetime.now(timezone.utc).isoformat(),
          "match_count":len(all_matches),"sources":[{"url":SWARM_LP,"method":"get_result_games","filter":"sport.type=1"}],
          "matches":all_matches},ensure_ascii=False,indent=2),encoding="utf-8")
        diag["parsed_count"]=len(collected); diag["sample"]=collected[:5]
        diag["status"]="success" if collected else "no_verified_matches"
    except Exception as e:
        diag["status"]="failed";diag["errors"].append(str(e)[:700])
    Path("data/virtual_swarm_probe.json").write_text(json.dumps(diag,ensure_ascii=False,indent=2),encoding="utf-8")
    print("VIRTUAL_SWARM="+json.dumps({k:v for k,v in diag.items() if k!="sample"},ensure_ascii=False))
    return diag

collect_virtual_swarm_results()

# Discover Virtual Sports separately from country/league competitions.
# Diagnostic only: unverified events are never merged into matches.json.
def discover_virtual_catalog():
    probe={"endpoint":SWARM_LP,"status":"not_tested","queries":[],"errors":[]}
    try:
        session=swarm_call({"command":"request_session","params":{"site_id":SWARM_SITE_ID,"language":"eng"}})
        sid=(session.get("data") or {}).get("sid")
        if not sid: raise RuntimeError("No Swarm SID")
        queries=[
          ("all_sports",{"source":"betting","what":{"sport":["id","name","alias","type"]}}),
          ("all_competitions",{"source":"betting","what":{"competition":["id","name","sport_id","_parent_id"]}}),
          ("all_games",{"source":"betting","what":{"game":["id","team1_name","team2_name","start_ts","is_live","sport_id","competition_id"]}}),
          ("virtual_alias_viv",{"source":"betting","what":{"sport":["id","name","alias","type"]},"where":{"sport":{"alias":"VIV"}}}),
          ("virtual_named",{"source":"betting","what":{"competition":["id","name","sport_id","_parent_id"]},"where":{"competition":{"name":{"@like":"%Virtual%"}}}})
        ]
        for label,params in queries:
            try:
                response=swarm_call({"command":"get","params":params},sid)
                probe["queries"].append({"label":label,"code":response.get("code"),"data":response.get("data")})
            except Exception as exc: probe["errors"].append(label+": "+str(exc)[:500])
        probe["status"]="success" if probe["queries"] else "failed"
    except Exception as exc:
        probe["status"]="failed"; probe["errors"].append(str(exc)[:1000])
    Path("data/virtual_discovery.json").write_text(json.dumps(probe,ensure_ascii=False,indent=2),encoding="utf-8")
    summary=[{"label":q["label"],"code":q["code"],"keys":list(q["data"].keys()) if isinstance(q.get("data"),dict) else []} for q in probe["queries"]]
    print("VIRTUAL_DISCOVERY="+json.dumps({"status":probe["status"],"queries":summary,"errors":probe["errors"]},ensure_ascii=False))
    return probe

discover_virtual_catalog()


# Public Betual virtual results page. Unlike the previous Swarm probe, this
# reads the same public results listing that visibly labels competitions
# "(Virtual Matches)" and includes FT plus HT scorelines.
def collect_public_virtual_results():
    from datetime import datetime, timezone
    urls = [
        "https://www.vbet.com/uk/sports/pre-match/results",
        "https://m.vbet.am/en/sports/pre-match/results",
    ]
    diag = {"status":"not_started","pages":[],"parsed_count":0,"errors":[]}
    found = []
    team_re = re.compile(r"([A-ZÀ-ž0-9][A-Za-zÀ-ž0-9.'’()& -]{1,65}? Virtual)")
    score_re = re.compile(r"(?<![0-9])(\d{1,2})\s*:\s*(\d{1,2})\s*\(\s*(\d{1,2})\s*:\s*(\d{1,2})\s*\)")
    for url in urls:
        try:
            resp = s.get(url, timeout=35)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            page_text = soup.get_text("\\n", strip=True)
            # Walk text in document order so each score inherits the latest Betual virtual-league heading.
            current_comp = ""
            all_strings = soup.find_all(string=True)
            for node in all_strings:
                raw_text = str(node).strip()
                heading = re.search(r"(Betual[^\\n]{0,90}?Virtual Matches)", raw_text, re.I)
                if heading:
                    current_comp = heading.group(1).strip()
                score = score_re.search(raw_text)
                if not score:
                    continue
                ancestor = node.parent
                best = None
                for _ in range(7):
                    if ancestor is None:
                        break
                    txt = ancestor.get_text(" ", strip=True)
                    teams = team_re.findall(txt)
                    uniq = []
                    for t in teams:
                        t = re.sub(r"\\s+", " ", t).strip()
                        if t not in uniq:
                            uniq.append(t)
                    if len(uniq) >= 2:
                        best = (txt, uniq[-2], uniq[-1])
                        break
                    ancestor = ancestor.parent
                if not best:
                    continue
                txt, home, away = best
                # Require virtual-team labels and an explicit virtual competition
                # on the same page; exclude ordinary football.
                competition = current_comp
                if "Virtual Matches" not in competition:
                    continue
                ft_h, ft_a, ht_h, ht_a = map(int, score.groups())
                item = {
                    "home_team":home,"away_team":away,
                    "ft_home":ft_h,"ft_away":ft_a,
                    "ht_home":ht_h,"ht_away":ht_a,
                    "date":None,"game_id":"",
                    "competition":competition,
                    "source":"VBET public results page (Betual Virtual Matches)",
                    "source_url":url
                }
                key=(competition,home,away,ft_h,ft_a,ht_h,ht_a)
                if not any((x["competition"],x["home_team"],x["away_team"],x["ft_home"],x["ft_away"],x["ht_home"],x["ht_away"])==key for x in found):
                    found.append(item)
            diag["pages"].append({"url":url,"status":resp.status_code,"html_bytes":len(resp.content),"virtual_markers":page_text.count("Virtual Matches")})
        except Exception as exc:
            diag["errors"].append(url+": "+str(exc)[:400])
    # Merge only verified Betual virtual matches; never erase an existing archive.
    path=Path("data/matches.json")
    previous=json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else {}
    old=previous.get("matches",[])
    merged={}
    for x in old+found:
        key=str(x.get("game_id") or (x.get("competition"),x.get("date"),x.get("home_team"),x.get("away_team"),x.get("ft_home"),x.get("ft_away"),x.get("ht_home"),x.get("ht_away")))
        merged[key]=x
    all_matches=list(merged.values())
    all_matches.sort(key=lambda x:str(x.get("date") or ""))
    Path("data").mkdir(exist_ok=True)
    Path("data/matches.json").write_text(json.dumps({
        "updated_at":datetime.now(timezone.utc).isoformat(),
        "match_count":len(all_matches),
        "sources":[{"url":u,"method":"public_results_html","filter":"competition contains Virtual Matches"} for u in urls],
        "matches":all_matches
    },ensure_ascii=False,indent=2),encoding="utf-8")
    diag["status"]="success" if found else "no_verified_matches"
    diag["parsed_count"]=len(found)
    diag["sample"]=found[:5]
    Path("data/public_results_probe.json").write_text(json.dumps(diag,ensure_ascii=False,indent=2),encoding="utf-8")
    print("PUBLIC_VIRTUAL_RESULTS="+json.dumps({"status":diag["status"],"parsed_count":len(found),"pages":diag["pages"],"errors":diag["errors"]},ensure_ascii=False))
    return diag

collect_public_virtual_results()
