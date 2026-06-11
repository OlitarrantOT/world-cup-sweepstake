#!/usr/bin/env python3
"""
Fetch live 2026 FIFA World Cup data from ESPN and write data/bracket.json.

No third-party dependencies - uses the standard library only, so the GitHub
Action just needs `python3`.

Data source (public, unofficial ESPN site API):
  scoreboard:  https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard
  standings:   https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/standings

The sweepstake is "last team standing": each owner is ranked by how far their
furthest surviving team has progressed. This script computes, for every team,
whether it is still alive and the furthest stage it has reached. The front-end
(index.html) reads data/bracket.json + data/picks.json and builds the
leaderboard from that.
"""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"
OUT = "data/bracket.json"

# Calendar "value" -> (json key, progression stage index, display name).
# The 3rd-place match is round 6; it is not a progression stage, so its index
# is None (reaching it does not advance you in the sweepstake).
ROUND_MAP = {
    "1": ("group",          0, "Group"),
    "2": ("round_of_32",    1, "Round of 32"),
    "3": ("round_of_16",    2, "Round of 16"),
    "4": ("quarterfinals",  3, "Quarter-final"),
    "5": ("semifinals",     4, "Semi-final"),
    "6": ("third_place", None, "3rd-place match"),
    "7": ("final",          5, "Final"),
}
STAGE_NAME = {0: "Group", 1: "Round of 32", 2: "Round of 16",
              3: "Quarter-final", 4: "Semi-final", 5: "Final", 6: "Champion"}


def get(url, tries=4):
    """GET JSON with a few retries; returns {} on persistent failure."""
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "wc-sweepstake/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as e:
            sys.stderr.write(f"  warn: {url} -> {e} (attempt {attempt+1})\n")
            time.sleep(2 * (attempt + 1))
    return {}


def ymd(iso):
    """'2026-06-28T07:00Z' -> '20260628'."""
    return iso[:10].replace("-", "")


def comp_team(c):
    """Pull a tidy team dict out of an ESPN competitor object."""
    t = c.get("team", {}) or {}
    name = t.get("displayName") or t.get("name") or c.get("displayName") or "TBD"
    score = c.get("score")
    try:
        score = int(score) if score not in (None, "") else None
    except (TypeError, ValueError):
        score = None
    return {
        "team": name,
        "abbr": (t.get("abbreviation") or "").lower(),
        "logo": t.get("logo"),
        "score": score,
        "winner": bool(c.get("winner")),
        "homeAway": c.get("homeAway"),
        "advance": (c.get("advance") or {}).get("yes") if isinstance(c.get("advance"), dict) else None,
    }


def fetch_calendar():
    """Return list of (round_value, start_iso, end_iso) from the scoreboard calendar."""
    sb = get(f"{BASE}/scoreboard")
    out = []
    try:
        cal = sb["leagues"][0]["calendar"][0]["entries"]
        for e in cal:
            out.append((e.get("value"), e.get("startDate"), e.get("endDate")))
    except (KeyError, IndexError, TypeError):
        pass
    return out


def fetch_round_events(round_value, start_iso, end_iso):
    """Fetch every event in a round's date window."""
    url = f"{BASE}/scoreboard?dates={ymd(start_iso)}-{ymd(end_iso)}&limit=100"
    data = get(url)
    events = data.get("events", []) or []
    out = []
    for ev in events:
        comps = ev.get("competitions", [{}])
        comp = comps[0] if comps else {}
        status = (((comp.get("status") or {}).get("type")) or {})
        competitors = [comp_team(c) for c in comp.get("competitors", [])]
        # order home first for stable rendering
        competitors.sort(key=lambda c: 0 if c["homeAway"] == "home" else 1)
        out.append({
            "id": ev.get("id"),
            "date": ev.get("date"),
            "round": round_value,
            "state": status.get("state"),            # pre | in | post
            "completed": bool(status.get("completed")),
            "detail": status.get("shortDetail"),
            "competitors": competitors,
        })
    return out


def winner_of(event):
    """Return the winning team name of a completed match, or None."""
    if not event["completed"]:
        return None
    cs = event["competitors"]
    for c in cs:
        if c["winner"]:
            return c["team"]
    # fall back to higher score (ESPN sometimes omits the winner flag briefly)
    scored = [c for c in cs if c["score"] is not None]
    if len(scored) == 2 and scored[0]["score"] != scored[1]["score"]:
        return max(scored, key=lambda c: c["score"])["team"]
    return None


def build_standings():
    """Best-effort group tables from the standings endpoint (empty pre-tournament)."""
    data = get(f"{BASE}/standings")
    groups = []
    children = data.get("children") or []
    for ch in children:
        name = ch.get("name") or ch.get("displayName") or ""
        entries = ((ch.get("standings") or {}).get("entries")) or []
        teams = []
        for en in entries:
            t = en.get("team", {}) or {}
            stats = {s.get("name"): s.get("value") for s in en.get("stats", [])}
            disp = {s.get("name"): s.get("displayValue") for s in en.get("stats", [])}
            teams.append({
                "team": t.get("displayName") or t.get("name"),
                "abbr": (t.get("abbreviation") or "").lower(),
                "logo": (t.get("logos") or [{}])[0].get("href") if t.get("logos") else t.get("logo"),
                "rank": stats.get("rank"),
                "p": stats.get("gamesPlayed"),
                "w": stats.get("wins"),
                "d": stats.get("ties"),
                "l": stats.get("losses"),
                "gd": stats.get("pointDifferential"),
                "pts": stats.get("points"),
                "record": disp.get("overall"),
            })
        if teams:
            groups.append({"name": name, "teams": teams})
    return groups


def main():
    print("Fetching calendar...")
    calendar = fetch_calendar()
    if not calendar:
        # Hard-coded fallback windows for the 2026 tournament.
        calendar = [
            ("1", "2026-06-11", "2026-06-28"),
            ("2", "2026-06-28", "2026-07-04"),
            ("3", "2026-07-04", "2026-07-09"),
            ("4", "2026-07-09", "2026-07-14"),
            ("5", "2026-07-14", "2026-07-19"),
            ("6", "2026-07-18", "2026-07-19"),
            ("7", "2026-07-19", "2026-08-01"),
        ]

    events_by_round = {}
    all_team_meta = {}       # name -> {abbr, logo}
    for value, start, end in calendar:
        if value not in ROUND_MAP:
            continue
        key, _, label = ROUND_MAP[value]
        print(f"Fetching {label}...")
        evs = fetch_round_events(value, start, end)
        events_by_round[value] = evs
        for ev in evs:
            for c in ev["competitors"]:
                if c["team"] and c["team"] != "TBD":
                    meta = all_team_meta.setdefault(c["team"], {})
                    if c["abbr"]:
                        meta["abbr"] = c["abbr"]
                    if c["logo"]:
                        meta["logo"] = c["logo"]

    # Real team names seen in the GROUP stage = the 48 actual participants.
    group_team_names = set()
    for ev in events_by_round.get("1", []):
        for c in ev["competitors"]:
            if c["team"] and c["team"] != "TBD":
                group_team_names.add(c["team"])

    def is_real(name):
        return name in group_team_names

    group_complete = bool(events_by_round.get("1")) and all(
        ev["completed"] for ev in events_by_round.get("1", [])
    )

    # ----- per-team status -----
    teams = {}
    for name, meta in all_team_meta.items():
        if not is_real(name):
            continue
        teams[name] = {
            "abbr": meta.get("abbr", ""),
            "logo": meta.get("logo"),
            "in_tournament": True,
            "stage_index": 0,
            "stage": "Group",
            "status": "alive",
        }

    champion = None

    # Walk knockout rounds (2..7) to mark eliminations & advancement.
    for value in ["2", "3", "4", "5", "7"]:           # skip 6 (3rd place)
        key, stage_idx, label = ROUND_MAP[value]
        for ev in events_by_round.get(value, []):
            present = [c["team"] for c in ev["competitors"] if is_real(c["team"])]
            # Reaching a knockout round counts as reaching that stage.
            for nm in present:
                if nm in teams and stage_idx is not None:
                    teams[nm]["stage_index"] = max(teams[nm]["stage_index"], stage_idx)
            if ev["completed"]:
                w = winner_of(ev)
                for nm in present:
                    if nm not in teams:
                        continue
                    if w and nm != w:
                        teams[nm]["status"] = "out"
                if value == "7" and w:               # Final winner = champion
                    champion = w

    # Group-stage eliminations: once the group stage is over, any participant
    # that does not appear in a real Round-of-32 fixture is out.
    if group_complete:
        r32_present = set()
        for ev in events_by_round.get("2", []):
            for c in ev["competitors"]:
                if is_real(c["team"]):
                    r32_present.add(c["team"])
        if r32_present:                               # only trust this once R32 is drawn
            for nm, t in teams.items():
                if nm not in r32_present and t["status"] == "alive":
                    t["status"] = "out"

    if champion and champion in teams:
        teams[champion]["status"] = "champion"
        teams[champion]["stage_index"] = 6

    for t in teams.values():
        t["stage"] = STAGE_NAME.get(t["stage_index"], "Group")

    # ----- assemble output -----
    standings = build_standings()
    # attach group name to each team's status entry when standings are available
    for g in standings:
        for gt in g["teams"]:
            if gt["team"] in teams:
                teams[gt["team"]]["group"] = g["name"]

    knockout = {}
    for value in ["2", "3", "4", "5", "6", "7"]:
        key, _, _ = ROUND_MAP[value]
        knockout[key] = events_by_round.get(value, [])

    if champion:
        phase = "complete"
    elif any(events_by_round.get(v) for v in ["2", "3", "4", "5", "7"]):
        phase = "knockout"
    else:
        phase = "group"

    out = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "phase": phase,
        "champion": champion,
        "groups": standings,
        "knockout": knockout,
        "group_fixtures": events_by_round.get("1", []),
        "teams": teams,
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"Wrote {OUT}: phase={phase}, teams={len(teams)}, "
          f"groups={len(standings)}, champion={champion}")


if __name__ == "__main__":
    main()
