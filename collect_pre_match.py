import json, re
from datetime import datetime, timezone
from pathlib import Path
import requests

URL="https://eu-swarm-lp.betconstruct.com/"
HEADERS={"User-Agent":"Mozilla/5.0","Content-Type":"application/json"}
out={"updated_at":datetime.now(timezone.utc).isoformat(),"source":"BetConstruct Swarm betting catalogue","status":"not_tested","fixtures":[],"errors":[],"diagnostics":{}}
try:
    s=requests.Session()
    s.headers.update(HEADERS)
    sess=s.post(URL,json={"command":"request_session","params":{"site_id":0,"language":"eng"}},timeout=25)
    sess.raise_for_status()
    sid=(sess.json().get("data") or {}).get("sid")
    if not sid: raise RuntimeError("Swarm session did not return SID")
    r=s.post(URL,headers={"swarm-session":sid},json={"command":"get","params":{
        "source":"betting",
        "what":{"game":["id","team1_name","team2_name","start_ts","is_live","sport_id","competition_id","competition_name"]},
        "where":{"game":{"is_live":0}}
    }},timeout=30)
    r.raise_for_status()
    payload=r.json()
    if payload.get("code")!=0: raise RuntimeError("Swarm catalogue code: "+str(payload.get("code")))
    data=payload.get("data") or {}
    data=data.get("data") or data
    raw=data.get("game",{}) if isinstance(data,dict) else {}
    rows=list(raw.values()) if isinstance(raw,dict) else (raw if isinstance(raw,list) else [])
    now=int(datetime.now(timezone.utc).timestamp())
    seen=set(); counts={"rows":len(rows),"has_names":0,"virtual_name_or_competition":0,"future":0,"not_live":0,"accepted":0}; samples=[]
    for g in rows:
        if not isinstance(g,dict): continue
        home=str(g.get("team1_name") or "").strip()
        away=str(g.get("team2_name") or "").strip()
        competition=str(g.get("competition_name") or "").strip()
        joined=(home+" "+away+" "+competition).casefold()
        if home and away: counts["has_names"]+=1
        if "virtual" in joined or "betual" in joined: counts["virtual_name_or_competition"]+=1
        try: start=int(float(g.get("start_ts") or 0))
        except (TypeError,ValueError): start=0
        if start>10**12: start//=1000
        gid=str(g.get("id") or "")
        live=g.get("is_live")
        not_live=(live is False or live==0 or str(live).strip().lower() in ("0","false","no",""))
        if not home or not away or not gid: continue
        if start>now: counts["future"]+=1
        if not_live: counts["not_live"]+=1
        if len(samples)<12: samples.append({"home":home,"away":away,"competition":competition,"start_ts":start,"is_live":live,"sport_id":g.get("sport_id")})
        if "virtual" not in joined and "betual" not in joined: continue
        if start<=now or not not_live: continue
        if gid in seen: continue
        seen.add(gid)
        out["fixtures"].append({"game_id":gid,"home_team":home,"away_team":away,"start_ts":start,
          "competition":competition or "Sanal futbol","sport_id":g.get("sport_id"),
          "competition_id":g.get("competition_id"),"status":"not_started"})
    out["fixtures"].sort(key=lambda x:x["start_ts"])
    out["status"]="success"
    counts["accepted"]=len(out["fixtures"]); out["diagnostics"]={"counts":counts,"sample_rows":samples}
    out["catalogue_rows"]=len(rows)
    out["fixture_count"]=len(out["fixtures"])
except Exception as e:
    out["status"]="failed"
    out["errors"].append(str(e)[:500])
Path("data/pre_match_fixtures.json").parent.mkdir(parents=True,exist_ok=True)
Path("data/pre_match_fixtures.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({k:out.get(k) for k in ["status","catalogue_rows","fixture_count","errors"]},ensure_ascii=False))
