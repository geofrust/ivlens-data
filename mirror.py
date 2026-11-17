#!/usr/bin/env python3
"""Builds the IV Lens data mirror: a checked copy of the PvPoke and PoGoAPI files the app downloads.

    python3 mirror.py OUT_DIR

Writes OUT_DIR with the same paths as PvPoke's src/data folder (gamemaster.json, rankings/<cup>/overall/...),
PoGoAPI's move files under pve/, and manifest.json. Everything comes from one PvPoke commit. Exits non-zero, writing
nothing usable, if a required file is missing or fails its checks, so the published copy stays as it was.
Python 3 standard library only.
"""
import json, os, shutil, sys, time, urllib.request
from datetime import datetime, timezone

PVPOKE_REPO = "pvpoke/pvpoke"
PVPOKE_RAW = "https://raw.githubusercontent.com/pvpoke/pvpoke/{sha}/src/data/{path}"
POGOAPI = "https://pogoapi.net/api/v1/{file}"
# owner/name of this repository: set by GitHub Actions, or the default when run by hand.
REPO = os.environ.get("GITHUB_REPOSITORY", "geofrust/ivlens-data")
OWNER, NAME = REPO.split("/")
PUBLISHED = f"https://{OWNER}.github.io/{NAME}/manifest.json"
LEAGUES = (1500, 2500, 10000)
UA = {"User-Agent": f"ivlens-data-mirror (+https://github.com/{REPO})"}


def fetch(url, tries=3):
    headers = dict(UA)
    if "api.github.com" in url and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise RuntimeError(f"{url}: {e}")
            time.sleep(5 * (i + 1))


def fetch_json(url):
    raw = fetch(url)
    return raw, json.loads(raw)


class Invalid(Exception):
    pass


def check(cond, msg):
    if not cond:
        raise Invalid(msg)


def check_gamemaster(gm):
    check(isinstance(gm, dict), "gamemaster: not an object")
    mons, moves = gm.get("pokemon", []), gm.get("moves", [])
    check(len(mons) >= 1000, f"gamemaster: only {len(mons)} Pokémon")
    check(len(moves) >= 300, f"gamemaster: only {len(moves)} moves")
    for m in mons[:50]:
        check({"speciesId", "dex", "baseStats", "types"} <= m.keys(), f"gamemaster: Pokémon entry missing fields: {m.get('speciesId')}")
    check(isinstance(gm.get("formats"), list) and isinstance(gm.get("cups"), list), "gamemaster: no formats/cups")


def check_rankings(rows, name, minimum):
    check(isinstance(rows, list) and len(rows) >= minimum, f"{name}: {len(rows) if isinstance(rows, list) else 'no'} entries")
    for r in rows[:20]:
        check({"speciesId", "score", "moveset"} <= r.keys(), f"{name}: entry missing fields")


def check_pve(rows, name, minimum):
    check(isinstance(rows, list) and len(rows) >= minimum, f"{name}: only {len(rows) if isinstance(rows, list) else 0} moves")
    for r in rows[:20]:
        check({"name", "power", "type", "duration", "energy_delta"} <= r.keys(), f"{name}: entry missing fields")


def cups(gm):
    """The cups the app offers (same rule as Cup.available in the app): (cup, cp, rankings folder)."""
    by_name = {c["name"]: c for c in gm.get("cups", []) if "name" in c}
    seen, out = set(), []
    for f in gm.get("formats", []):
        c = by_name.get(f.get("cup"))
        if f.get("hideRankings") is True or f.get("cup") in ("custom", "all", "mega") or not c or c.get("presetOnly") in (True, 1):
            continue
        key = (f["cup"], f["cp"])
        if key not in seen:
            seen.add(key)
            out.append((f["cup"], f["cp"], c.get("rankingAlias") or f["cup"]))
    return out


def write(out, path, raw):
    p = os.path.join(out, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(raw)


def main(out):
    stage = out + ".staging"
    shutil.rmtree(stage, ignore_errors=True)
    _, commit = fetch_json(f"https://api.github.com/repos/{PVPOKE_REPO}/commits/master")
    sha = commit["sha"]
    print(f"PvPoke commit {sha[:10]} ({commit['commit']['committer']['date']})")

    files = {}
    raw, gm = fetch_json(PVPOKE_RAW.format(sha=sha, path="gamemaster.json"))
    check_gamemaster(gm)
    write(stage, "gamemaster.json", raw); files["gamemaster.json"] = len(gm["pokemon"])

    # Don't publish a game master that lost a lot of Pokémon since the last published one.
    try:
        _, prev = fetch_json(PUBLISHED)
        before = prev.get("counts", {}).get("gamemaster.json", 0)
        check(len(gm["pokemon"]) >= 0.95 * before, f"gamemaster: {len(gm['pokemon'])} Pokémon, was {before}")
    except Invalid:
        raise
    except Exception as e:
        print(f"(no published manifest to compare with: {e})")

    for cp in LEAGUES:
        path = f"rankings/all/overall/rankings-{cp}.json"
        raw, rows = fetch_json(PVPOKE_RAW.format(sha=sha, path=path))
        check_rankings(rows, path, 300)
        write(stage, path, raw); files[path] = len(rows)

    skipped = []
    for cup, cp, folder in cups(gm):
        path = f"rankings/{folder}/overall/rankings-{cp}.json"
        if path in files:
            continue
        try:
            raw, rows = fetch_json(PVPOKE_RAW.format(sha=sha, path=path))
            check_rankings(rows, path, 20)
            write(stage, path, raw); files[path] = len(rows)
        except (Invalid, RuntimeError, ValueError) as e:
            skipped.append(f"{cup}-{cp}: {e}")   # the app leaves out a cup it can't download

    for name, minimum in (("fast_moves.json", 60), ("charged_moves.json", 180)):
        raw, rows = fetch_json(POGOAPI.format(file=name))
        check_pve(rows, name, minimum)
        write(stage, f"pve/{name}", raw); files[f"pve/{name}"] = len(rows)

    manifest = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pvpokeCommit": sha,
        "gamemasterTimestamp": gm.get("timestamp"),
        "counts": files,
        "skippedCups": skipped,
    }
    write(stage, "manifest.json", json.dumps(manifest, indent=1).encode())
    here = os.path.dirname(os.path.abspath(__file__))
    for f in ("LICENSE-PvPoke", "index.html", "privacy.html", "support.html"):
        if os.path.exists(os.path.join(here, f)):
            shutil.copy(os.path.join(here, f), os.path.join(stage, f))
    open(os.path.join(stage, ".nojekyll"), "w").close()

    shutil.rmtree(out, ignore_errors=True)
    os.rename(stage, out)
    print(f"{len(files)} files OK" + (f"; skipped {len(skipped)} cup(s): " + "; ".join(skipped) if skipped else ""))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        main(sys.argv[1])
    except Invalid as e:
        sys.exit(f"Check failed, nothing published: {e}")
