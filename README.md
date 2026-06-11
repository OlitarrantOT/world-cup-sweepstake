# 2026 World Cup Sweepstake

A live, auto-updating **last-team-standing** sweepstake page for the 2026 FIFA
World Cup. Each player owns a set of national teams; the leaderboard ranks
everyone by how far their furthest surviving team has progressed. Whoever owns
the eventual champion wins.

It mirrors the old NBA playoff sweepstake site: a static page on GitHub Pages,
with a GitHub Action that pulls live results from ESPN every 30 minutes and
commits an updated `data/bracket.json`.

## The picks

| Player  | Teams |
|---------|-------|
| Bundy   | Spain, Belgium, United States, Morocco |
| Charlie | France, Netherlands, Australia, Iran |
| Jamie   | Portugal, Germany, Norway, Austria |
| Gus     | England, Japan, Croatia, Colombia |
| Ollie   | Brazil, Argentina, Uruguay, Uzbekistan |

Edit `data/picks.json` to change owners or teams. Use ESPN display names
(e.g. **United States**, not USA). Italy did not qualify for 2026, so it is not
included.

## How it works

- **`index.html`** — the page. Three views: Leaderboard, Knockouts, Groups.
- **`data/picks.json`** — who owns which team (you edit this).
- **`data/bracket.json`** — live results, written by the script. Do not edit.
- **`scripts/fetch_worldcup.py`** — pulls ESPN data, computes each team's
  alive/out status and furthest stage, writes `data/bracket.json`.
- **`.github/workflows/update.yml`** — runs the script every 30 min and commits.

The leaderboard math lives in the browser: it reads each team's status from
`bracket.json` and ranks players by their best surviving team.

## Setup (one time)

1. Create a GitHub repo and push these files (or replace the contents of the
   existing `nba-playoff-sweepstake` repo).
2. **Settings → Pages →** set Source to `Deploy from a branch`, branch `main`,
   folder `/ (root)`. Your site appears at
   `https://<user>.github.io/<repo>/`.
3. **Settings → Actions → General →** under *Workflow permissions* choose
   **Read and write permissions** (lets the Action commit data).
4. **Actions** tab → select *Update World Cup data* → **Run workflow** to pull
   live data immediately. After that it runs itself every 30 minutes.

That's it. The page is live and will populate as matches are played.

## Notes

- The group tables fill in once ESPN publishes standings (after the first
  matches). Until then the Groups view shows fixtures, and every picked team
  shows as **Alive / Group**.
- A team is marked **Out** when it loses a knockout match, or when the group
  stage ends and it didn't reach the Round of 32.
- Data source is ESPN's public site API. If they change it, the script's
  `BASE` URL and parsing are the only things that would need a tweak.
