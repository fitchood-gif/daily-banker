import os
import json
import requests
from datetime import datetime, timezone

# Reads your API key safely from GitHub Secrets
API_KEY = os.environ.get("API_FOOTBALL_KEY")
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}

# Target Odds Window
MIN_ODDS = 1.07
MAX_ODDS = 1.15

# High-scoring leagues (Premier League, Bundesliga, Eredivisie, La Liga, Serie A)
TARGET_LEAGUES = {39, 40, 78, 79, 88, 94, 135, 140, 144, 179}


def get_todays_fixtures():
    """Fetch all scheduled fixtures for today in target leagues."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url = f"{BASE_URL}/fixtures"
    params = {"date": today_str, "status": "NS"}
    
    res = requests.get(url, headers=HEADERS, params=params).json()
    fixtures = res.get("response", [])
    return [f for f in fixtures if f["league"]["id"] in TARGET_LEAGUES]


def check_fixture_odds(fixture_id):
    """Check pre-match odds for Over 0.5 Goals or Double Chance in the 1.08 - 1.13 band."""
    url = f"{BASE_URL}/odds"
    params = {"fixture": fixture_id}
    
    res = requests.get(url, headers=HEADERS, params=params).json()
    odds_data = res.get("response", [])
    if not odds_data:
        return None

    bets = odds_data[0].get("bookmakers", [{}])[0].get("bets", [])
    
    for bet in bets:
        # Bet ID 5 = Goals Over/Under | Bet ID 12 = Double Chance
        if bet["id"] in [5, 12]:
            for val in bet["values"]:
                odd_price = float(val["odd"])
                if MIN_ODDS <= odd_price <= MAX_ODDS:
                    if "Over 0.5" in val["value"] or "Home/Draw" in val["value"] or "Draw/Away" in val["value"]:
                        return {
                            "market": f"{bet['name']} ({val['value']})",
                            "odds": odd_price
                        }
    return None


def verify_team_hit_rate(team_id, min_games=10):
    """Verify the team's last 10 matches had at least 1 goal (90%+ hit rate)."""
    url = f"{BASE_URL}/fixtures"
    params = {"team": team_id, "last": min_games, "status": "FT"}
    
    res = requests.get(url, headers=HEADERS, params=params).json()
    matches = res.get("response", [])
    
    if len(matches) < min_games:
        return 0.0
        
    over_05_count = 0
    for m in matches:
        total_goals = (m["goals"]["home"] or 0) + (m["goals"]["away"] or 0)
        if total_goals >= 1:
            over_05_count += 1
            
    return (over_05_count / len(matches)) * 100


def generate_daily_pick():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanning today's fixtures via API-Football...")
    fixtures = get_todays_fixtures()
    print(f"Found {len(fixtures)} matches in target leagues.")

    qualified_picks = []

    for f in fixtures:
        fixture_id = f["fixture"]["id"]
        home = f["teams"]["home"]
        away = f["teams"]["away"]
        league = f["league"]

        # Skip early season variance (first 5 rounds)
        round_str = league.get("round", "")
        if any(f"- {i}" in round_str for i in range(1, 6)):
            continue

        # Check if pre-match odds fall in 1.08 - 1.13
        odds_match = check_fixture_odds(fixture_id)
        if not odds_match:
            continue

        # Verify 90%+ hit rate over last 10 matches for both teams
        home_rate = verify_team_hit_rate(home["id"])
        away_rate = verify_team_hit_rate(away["id"])

        if home_rate >= 90.0 and away_rate >= 90.0:
            avg_rate = (home_rate + away_rate) / 2
            qualified_picks.append({
                "fixture_id": fixture_id,
                "league": f"{league['country']} • {league['name']}",
                "match": f"{home['name']} vs {away['name']}",
                "kickoff": f["fixture"]["date"],
                "pick": odds_match["market"],
                "odds": odds_match["odds"],
                "hitRate": f"{avg_rate:.0f}% (Last 10)",
                "prob": f"{(1 / odds_match['odds']) * 100:.1f}%"
            })

    if qualified_picks:
        best_pick = sorted(qualified_picks, key=lambda x: x["hitRate"], reverse=True)[0]
        output = {"status": "PICK_FOUND", "data": best_pick}
        print(f"BEST PICK FOUND: {best_pick['match']} | {best_pick['pick']} @ {best_pick['odds']}")
    else:
        output = {"status": "NO_BET_TODAY", "data": None}
        print("NO BET TODAY: No fixtures met all statistical guardrails.")

    with open("pick.json", "w") as outfile:
        json.dump(output, outfile, indent=4)


if __name__ == "__main__":
    generate_daily_pick()
