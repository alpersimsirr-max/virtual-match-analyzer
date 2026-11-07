#!/usr/bin/env python3
"""Experimental score predictor for the verified Betual virtual-results archive.

Usage:
  python predictor.py "Valencia Virtual" "Racing Santander Virtual"
  python predictor.py "Valencia Virtual" "Racing Santander Virtual" --minute 8 --home-score 0 --away-score 0 --home-shots 9 --away-shots 4

This is a small-sample statistical baseline, not a betting guarantee.
"""
import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path


def norm(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def poisson(k, lam):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def read_matches(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [m for m in raw.get("matches", []) if all(
        isinstance(m.get(k), int) for k in
        ("ft_home", "ft_away", "ht_home", "ht_away")
    ) and m.get("home_team") and m.get("away_team")]


def team_rates(matches, team):
    key = norm(team)
    played = scored = conceded = ht_scored = ht_conceded = 0
    for m in matches:
        if norm(m["home_team"]) == key:
            played += 1
            scored += m["ft_home"]
            conceded += m["ft_away"]
            ht_scored += m["ht_home"]
            ht_conceded += m["ht_away"]
        elif norm(m["away_team"]) == key:
            played += 1
            scored += m["ft_away"]
            conceded += m["ft_home"]
            ht_scored += m["ht_away"]
            ht_conceded += m["ht_home"]
    if not played:
        return None
    return {
        "played": played, "scored": scored / played, "conceded": conceded / played,
        "ht_scored": ht_scored / played, "ht_conceded": ht_conceded / played
    }


def shrink(value, prior, n, strength=3.0):
    return (value * n + prior * strength) / (n + strength)


def predict(args):
    matches = read_matches(args.data)
    if not matches:
        raise SystemExit("Arşivde kullanılabilir doğrulanmış maç bulunamadı.")

    home_key, away_key = norm(args.home), norm(args.away)
    home_hist = team_rates(matches, args.home)
    away_hist = team_rates(matches, args.away)

    # Use the teams' shared competition when possible; otherwise use the full archive.
    shared = set(m.get("competition") for m in matches
                 if norm(m["home_team"]) in (home_key, away_key)
                 or norm(m["away_team"]) in (home_key, away_key))
    comp_matches = [m for m in matches if m.get("competition") in shared] if shared else matches
    if len(comp_matches) < 5:
        comp_matches = matches

    avg_h = sum(m["ft_home"] for m in comp_matches) / len(comp_matches)
    avg_a = sum(m["ft_away"] for m in comp_matches) / len(comp_matches)
    avg_ht_h = sum(m["ht_home"] for m in comp_matches) / len(comp_matches)
    avg_ht_a = sum(m["ht_away"] for m in comp_matches) / len(comp_matches)

    def adjusted(team, base, attack_key, defense_key, opponent, opponent_def_key):
        if not team:
            return base
        attack = shrink(team[attack_key], base, team["played"])
        opponent_def = shrink(opponent[defense_key], base, opponent["played"]) if opponent else base
        return max(0.12, base * (0.55 + 0.45 * attack / max(base, 0.1))
                   * (0.55 + 0.45 * opponent_def / max(base, 0.1)))

    lam_h = adjusted(home_hist, avg_h, "scored", "conceded", away_hist, "conceded")
    lam_a = adjusted(away_hist, avg_a, "scored", "conceded", home_hist, "conceded")
    ht_h = adjusted(home_hist, avg_ht_h, "ht_scored", "ht_conceded", away_hist, "ht_conceded")
    ht_a = adjusted(away_hist, avg_ht_a, "ht_scored", "ht_conceded", home_hist, "ht_conceded")

    minute = max(0, min(89, args.minute))
    remaining = (90 - minute) / 90
    # A modest live-shot adjustment; avoid letting a few early shots dominate.
    if args.home_shots is not None and args.away_shots is not None:
        shot_diff = max(-0.25, min(0.25, (args.home_shots - args.away_shots) * 0.025))
        lam_h *= 1 + shot_diff
        lam_a *= 1 - shot_diff

    current_h, current_a = args.home_score, args.away_score
    future_h, future_a = lam_h * remaining, lam_a * remaining
    ft_lam_h, ft_lam_a = current_h + future_h, current_a + future_a

    # First-half score is only forecast while the first half is in progress.
    # In the second half it is already settled and must not be re-predicted.
    ht_scores = []
    if minute < 45:
        ht_remaining = (45 - minute) / 45
        future_ht_h, future_ht_a = ht_h * ht_remaining, ht_a * ht_remaining

    max_goals = 8
    ft_scores = [(current_h + i, current_a + j,
                  poisson(i, future_h) * poisson(j, future_a))
                 for i in range(max_goals + 1) for j in range(max_goals + 1)]
    if minute < 45:
        ht_scores = [(current_h + i, current_a + j,
                      poisson(i, future_ht_h) * poisson(j, future_ht_a))
                     for i in range(max_goals + 1) for j in range(max_goals + 1)]
    best_ft = sorted(ft_scores, key=lambda x: x[2], reverse=True)[:3]
    best_ht = max(ht_scores, key=lambda x: x[2]) if ht_scores else None

    total = sum(p for _, _, p in ft_scores) or 1
    over25 = sum(p for h, a, p in ft_scores if h + a >= 3) / total
    over35 = sum(p for h, a, p in ft_scores if h + a >= 4) / total
    over45 = sum(p for h, a, p in ft_scores if h + a >= 5) / total

    return {
        "match": f"{args.home} - {args.away}",
        "data_matches": len(matches),
        "home_team_matches": home_hist["played"] if home_hist else 0,
        "away_team_matches": away_hist["played"] if away_hist else 0,
        "live_state": {"minute": minute, "score": f"{current_h}-{current_a}"},
        "half_time_prediction": (f"{best_ht[0]}-{best_ht[1]}" if best_ht else None),
        "half_time_status": ("forecast" if best_ht else "completed_not_reconstructed"),
        "full_time_prediction": f"{best_ft[0][0]}-{best_ft[0][1]}",
        "alternative_scores": [f"{h}-{a}" for h, a, _ in best_ft[1:]],
        "probabilities": {
            "over_2_5": round(over25, 3),
            "over_3_5": round(over35, 3),
            "over_4_5": round(over45, 3)
        },
        "warning": "Deneysel tahmin: veri kümesi küçük ve takım başına maç sayısı sınırlı."
    }


def main():
    p = argparse.ArgumentParser(description="Betual virtual match score predictor")
    p.add_argument("home", help="Ev sahibi takım adı")
    p.add_argument("away", help="Deplasman takım adı")
    p.add_argument("--data", default="data/matches.json")
    p.add_argument("--minute", type=int, default=0)
    p.add_argument("--home-score", type=int, default=0)
    p.add_argument("--away-score", type=int, default=0)
    p.add_argument("--home-shots", type=int)
    p.add_argument("--away-shots", type=int)
    args = p.parse_args()
    print(json.dumps(predict(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
