#!/usr/bin/env python3
"""Generate automatic forecasts for live BetConstruct virtual football fixtures.

The current live catalogue exposes fixture IDs/team names but not reliable
in-play score/minute fields. Therefore these are fixture forecasts, not
in-play score predictions. Non-football virtual sports are excluded.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from predictor import predict

NON_FOOTBALL = (
    "basket", "nba", "wnba", "tennis", "volley", "hockey", "rugby",
    "cricket", "baseball", "handball", "table tennis", "darts", "boxing",
    "mma", "cycling", "racing", "golf", "badminton", "esports",
    "call of duty", "dota", "counter-strike", "league of legends",
    "perugia", "trentino", "bublik", "ruud", "collignon", "vacherot",
)
FOOTBALL_HINTS = (
    "fc ", " cf", " united", " city", " real ", " atletico", " athletic",
    "barcelona", "madrid", "valencia", "chelsea", "arsenal", "liverpool",
    "bayern", "dortmund", "juventus", "milan", "inter ", "sevilla",
    "leverkusen", "schalke", "mainz", "monaco", "psg", "marseille",
    "tottenham", "everton", "fulham", "brighton", "brentford", "wolves",
    "leeds", "sunderland", "coventry", "ipswich", "racing santander",
    "deportivo", "osasuna", "getafe", "girona", "celtic", "rangers",
    "poland", "slovenia", "brazil", "germany", "france", "spain",
    "england", "netherlands", "argentina", "portugal", "italy",
)


def is_football_fixture(match):
    home = str(match.get("home_team") or "")
    away = str(match.get("away_team") or "")
    joined = (home + " " + away).casefold()
    if "virtual" not in joined:
        return False
    if any(token in joined for token in NON_FOOTBALL):
        return False
    # Known football-club/country naming patterns reduce accidental inclusion
    # of virtual basketball and other sports with generic team names.
    return any(token in joined for token in FOOTBALL_HINTS)


def main():
    live_path = Path("data/betual_live_games.json")
    archive_path = Path("data/matches.json")
    if not live_path.exists():
        raise SystemExit("data/betual_live_games.json bulunamadı; önce collector.py çalıştırın.")
    live = json.loads(live_path.read_text(encoding="utf-8"))
    archive = json.loads(archive_path.read_text(encoding="utf-8")) if archive_path.exists() else {"matches":[]}
    candidates = [m for m in live.get("matches", []) if is_football_fixture(m)]
    forecasts = []
    for m in candidates:
        args = SimpleNamespace(
            home=m["home_team"], away=m["away_team"], data=str(archive_path),
            minute=0, home_score=0, away_score=0, home_shots=None, away_shots=None
        )
        try:
            forecast = predict(args)
            forecasts.append({
                "game_id": m.get("game_id"),
                "home_team": m["home_team"],
                "away_team": m["away_team"],
                "start_ts": m.get("start_ts"),
                "is_live": m.get("is_live"),
                "forecast_type": "fixture_baseline_not_live_score",
                "prediction": forecast,
                "source": m.get("source"),
            })
        except Exception as exc:
            forecasts.append({
                "game_id": m.get("game_id"),
                "home_team": m.get("home_team"),
                "away_team": m.get("away_team"),
                "error": str(exc)[:300],
            })
    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "live_catalogue_count": len(live.get("matches", [])),
        "football_fixture_count": len(candidates),
        "forecast_count": len(forecasts),
        "note": "Live feed currently provides fixture names/IDs but no verified in-play score or clock. These are pre-match-style fixture estimates, not live-state forecasts.",
        "forecasts": forecasts,
    }
    Path("data").mkdir(exist_ok=True)
    Path("data/live_predictions.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "status": output["status"],
        "live_catalogue_count": output["live_catalogue_count"],
        "football_fixture_count": output["football_fixture_count"],
        "forecast_count": output["forecast_count"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
