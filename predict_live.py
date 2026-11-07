#!/usr/bin/env python3
"""Create predictions only when a verified in-play score and clock are available.

The current BetConstruct live catalogue contains fixture IDs and team names but
no verified live score/clock. Never label a pre-match estimate as a live forecast.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from predictor import predict


def main():
    live_path = Path("data/betual_live_games.json")
    archive_path = Path("data/matches.json")
    live = json.loads(live_path.read_text(encoding="utf-8")) if live_path.exists() else {"matches": []}
    archive = json.loads(archive_path.read_text(encoding="utf-8")) if archive_path.exists() else {"matches": []}

    source_fetched_at = live.get("source_fetched_at") or live.get("updated_at")
    try:
        source_age_seconds = max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(source_fetched_at.replace("Z", "+00:00"))).total_seconds())
        source_fresh = source_age_seconds <= 120
    except (AttributeError, TypeError, ValueError):
        source_age_seconds = None
        source_fresh = False

    candidates = []
    waiting = []
    for m in live.get("matches", []):
        joined = (str(m.get("home_team") or "") + " " + str(m.get("away_team") or "")).casefold()
        if "virtual" not in joined:
            continue
        raw = m.get("raw_score_fields") or {}
        info = raw.get("info") or {}
        stats = raw.get("stats") or {}
        additional = info.get("additional_data") or {}
        # Keep only the two requested virtual sports. Football feeds expose
        # goal statistics; basketball exposes quarterScores/quarter metadata.
        if isinstance(stats.get("goal"), dict):
            sport = "football"
        elif additional.get("quarterScores") or additional.get("quarter") is not None:
            sport = "basketball"
        else:
            continue
        if sport == "basketball":
            continue  # separate basketball forecast model is added below
        if not source_fresh:
            waiting.append({
                "game_id": m.get("game_id"), "home_team": m.get("home_team"),
                "away_team": m.get("away_team"), "sport": sport,
                "status": "blocked_stale_or_missing_source_timestamp",
                "source_age_seconds": source_age_seconds,
            })
            continue
        minute = m.get("minute")
        hs, aws = m.get("home_score"), m.get("away_score")
        # Never infer a live score from a fixture or kickoff timestamp.
        # The collector marks a state verified only when Swarm returned both
        # nested info.score1/score2 and a parseable in-play clock.
        verified = m.get("live_state_verified") is True
        if (not verified or not isinstance(minute, (int, float))
                or not isinstance(hs, int) or not isinstance(aws, int)):
            waiting.append({
                "game_id": m.get("game_id"),
                "home_team": m.get("home_team"),
                "away_team": m.get("away_team"),
                "display_clock": m.get("display_clock"),
                "period": m.get("period"),
                "sport": sport,
                "status": "waiting_for_verified_live_score_and_minute",
            })
            continue
        candidates.append((m, minute, hs, aws, sport))

    forecasts = []
    for m, minute, hs, aws, sport in candidates:
        try:
            from types import SimpleNamespace
            args = SimpleNamespace(
                home=m["home_team"], away=m["away_team"], data=str(archive_path),
                minute=int(minute), home_score=hs, away_score=aws,
                home_shots=m.get("home_shots"), away_shots=m.get("away_shots")
            )
            forecasts.append({
                "game_id": m.get("game_id"),
                "home_team": m["home_team"],
                "away_team": m["away_team"],
                "live_state": {"minute": int(minute), "score": f"{hs}-{aws}"},
                "sport": sport,
                "display_clock": m.get("display_clock"),
                "period": m.get("period"),
                "status": "live_prediction",
                "prediction": predict(args),
            })
        except Exception as exc:
            forecasts.append({
                "game_id": m.get("game_id"),
                "home_team": m.get("home_team"),
                "away_team": m.get("away_team"),
                "status": "prediction_error",
                "error": str(exc)[:300],
            })

    status = "success" if forecasts else "waiting_for_live_data"
    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source_fetched_at": source_fetched_at,
        "source_age_seconds": round(source_age_seconds, 1) if source_age_seconds is not None else None,
        "source_fresh": source_fresh,
        "status": status,
        "archive_match_count": len(archive.get("matches", [])),
        "live_catalogue_count": len(live.get("matches", [])),
        "football_live_count": sum(1 for m in live.get("matches", []) if "virtual" in (str(m.get("home_team",""))+" "+str(m.get("away_team",""))).casefold() and isinstance(((m.get("raw_score_fields") or {}).get("stats") or {}).get("goal"),dict)),
        "live_forecast_count": len(forecasts),
        "waiting_count": len(waiting),
        "note": "Only verified live score and minute can trigger a live prediction. No pre-match estimate is presented as a live prediction.",
        "forecasts": forecasts,
        "waiting_for_live_data": waiting,
    }
    Path("data").mkdir(exist_ok=True)
    Path("data/live_predictions.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: output[k] for k in (
        "status", "archive_match_count", "live_catalogue_count",
        "live_forecast_count", "waiting_count"
    )}, ensure_ascii=False))


if __name__ == "__main__":
    main()
