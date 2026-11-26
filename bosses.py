#!/usr/bin/env python3
"""Builds bosses.json for the IV Lens app: the raid bosses with their dates and the Max Battle rotation by tier.

    python3 bosses.py OUT_FILE [--raids FILE] [--gamemaster FILE] [--previous FILE] [--now 2026-11-25T08:00:00Z]

From Pokebattler's public API (https://www.pokebattler.com/developers: attribution required, cache heavily), one request
per run, plus corrections.json beside this file. Names are PvPoke's (the app's game data), from the mirror's own
gamemaster.json. Exits non-zero, writing nothing, if the data fails its checks, so the published copy stays as it was.
Python 3 standard library only.
"""
import argparse, json, os, re, sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from mirror import Invalid, check, fetch, OWNER, NAME

RAIDS = "https://fight.pokebattler.com/raids"
GAMEMASTER = f"https://{OWNER}.github.io/{NAME}/gamemaster.json"
PUBLISHED = f"https://raw.githubusercontent.com/{OWNER}/{NAME}/bosses/bosses.json"
# Pokebattler gives a boss's local time (6:00 wherever the player is) as that time in California.
CLOCK = ZoneInfo("America/Los_Angeles")
# Bosses stay listed this long after they end: the app uses them to drop ones LeekDuck's list still has.
KEEP_ENDED = timedelta(days=7)
REGIONS = {"_alola": "_alolan", "_galar": "_galarian", "_hisui": "_hisuian", "_paldea": "_paldean"}
ALIASES = {"mewtwo_a": "mewtwo_armored"}
# The forms PvPoke names that Pokebattler leaves out ("TORNADUS" is Tornadus (Incarnate)).
DEFAULT_FORMS = ("incarnate", "altered", "land", "ordinary", "aria", "plant", "overcast", "average", "standard", "male",
                 "midday", "confined", "amped", "hero", "shield", "single_strike", "full_belly", "baile", "disguised")


def stars(tier):
    """RAID_LEVEL_5_SHADOW -> (5, True); 6 is Mega. None for a tier the app doesn't know."""
    if "MAX" in tier or tier.endswith(("_LEGACY", "_FUTURE")):
        return None
    if "MEGA" in tier:
        return 6, False
    if tier in ("RAID_LEVEL_ULTRA_BEAST", "RAID_LEVEL_ELITE"):
        return 5, False
    m = re.fullmatch(r"RAID_LEVEL_([135])(_SHADOW)?", tier)
    return (int(m[1]), bool(m[2])) if m else None


def max_tier(tier):
    m = re.fullmatch(r"RAID_LEVEL_([1-6])_MAX", tier)
    return int(m[1]) if m else None


class Names:
    """Pokebattler's ids ("METAGROSS_MEGA", "TORNADUS_SHADOW_FORM") to PvPoke's names ("Metagross (Mega)")."""

    def __init__(self, gamemaster):
        self.by_key = {}
        for p in gamemaster["pokemon"]:
            if not p["speciesId"].endswith("_shadow"):
                self.by_key.setdefault(p["speciesId"].replace("_", ""), p["speciesName"])

    def find(self, key):
        return self.by_key.get(key.replace("_", ""))

    def name(self, pokemon, costume=False):
        t = re.sub(r"_form$", "", pokemon.lower())
        t = re.sub(r"_shadow$", "", t)
        t = re.sub(r"_(gigantamax|eternamax)$", "", t)
        for a, b in REGIONS.items():
            t = re.sub(f"{a}$", b, t)
        t = ALIASES.get(t, t)
        found = self.find(t) or next((n for d in DEFAULT_FORMS if (n := self.find(f"{t}_{d}"))), None)
        if found:
            return found
        # The regular form, and costumes (same stats): the species itself. Any other unknown form has its own stats.
        if t.endswith("_normal"):
            return self.find(t[:-len("_normal")])
        if costume or re.search(r"_20\d\d(_|$)", t):
            parts = t.split("_")
            return next((n for i in range(len(parts) - 1, 0, -1) if (n := self.find("_".join(parts[:i])))), None)
        return None


def local(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).astimezone(CLOCK).strftime("%Y-%m-%dT%H:%M:%S")


def build(raids, gamemaster, corrections, previous, now):
    names = Names(gamemaster)
    here = now.astimezone(CLOCK).strftime("%Y-%m-%dT%H:%M:%S")
    oldest = (now - KEEP_ENDED).astimezone(CLOCK).strftime("%Y-%m-%dT%H:%M:%S")
    out_raids, out_max, unmapped = {}, {}, set()

    # Bosses with dates.
    for e in raids.get("breakingNews", []):
        tier, pokemon = e["tier"], e["pokemon"]
        s, m = stars(tier), max_tier(tier)
        name = names.name(pokemon, e.get("costume", False))
        if name is None or (s is None and m is None):
            unmapped.add(f"{tier} {pokemon}")
            continue
        start, end = local(e["startDate"]), local(e["endDate"])
        check(start < end, f"{pokemon}: {start} to {end}")
        if end < oldest:
            continue
        if s:
            b = {"name": name, "stars": s[0], "shadow": s[1], "start": start, "end": end}
            out_raids[(name, s, start)] = b
        else:
            b = {"name": name, "tier": m, "gigantamax": "GIGANTAMAX" in pokemon, "start": start, "end": end}
            out_max[(name, m, start)] = b
    # The regular Max Battles: no dates, so not tier 6 (events, left in the list after they end).
    for t in raids.get("tiers", []):
        m = max_tier(t["tier"])
        if m is None or m == 6:
            continue
        for r in t.get("raids", []):
            name = names.name(r["pokemon"])
            if name is None:
                unmapped.add(f"{t['tier']} {r['pokemon']}")
            else:
                out_max.setdefault((name, m, ""), {"name": name, "tier": m, "gigantamax": "GIGANTAMAX" in r["pokemon"]})

    # Raids of the last copy that have ended since Pokebattler dropped them.
    for b in (previous or {}).get("raids", []):
        key = (b["name"], (b["stars"], b["shadow"]), b["start"])
        if key not in out_raids and oldest <= b["end"] <= here:
            out_raids[key] = b

    # By hand: "hide" a boss everywhere until a date, "add" one with its dates.
    hide = [h for h in corrections.get("hide", []) if h.get("until", "9") > here]
    for h in hide:
        check(h.get("kind") in ("raid", "max") and names_known(names, h["name"]), f"corrections: hide {h}")
    for a in corrections.get("add", []):
        check(a.get("kind") in ("raid", "max") and names_known(names, a["name"]), f"corrections: add {a}")
        b = {k: v for k, v in a.items() if k != "kind"}
        if b.get("end", "9") < here:
            continue
        if a["kind"] == "raid":
            check({"stars", "start", "end"} <= b.keys(), f"corrections: add {a}")
            b.setdefault("shadow", False)
            out_raids[(b["name"], (b["stars"], b["shadow"]), b["start"])] = b
        else:
            check("tier" in b and ("start" in b) == ("end" in b), f"corrections: add {a}")
            b.setdefault("gigantamax", False)
            out_max[(b["name"], b["tier"], b.get("start", ""))] = b

    r = sorted(out_raids.values(), key=lambda b: (b["start"], -b["stars"], b["shadow"], b["name"]))
    x = sorted(out_max.values(), key=lambda b: (b.get("start", ""), -b["tier"]))
    on = [b for b in r if b["start"] <= here < b["end"]]
    check(len(on) >= 3, f"only {len(on)} raid bosses on now")
    rotation = [b for b in x if "start" not in b]
    check(len(rotation) >= 10, f"only {len(rotation)} Max Battle bosses")
    total = len(r) + len(x)
    check(len(unmapped) <= max(5, total // 10), f"{len(unmapped)} unknown bosses: {sorted(unmapped)}")
    return {"format": 1, "updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "credit": "Raid and Max Battle bosses from Pokebattler (pokebattler.com)",
            "raids": r, "max": x, "hide": hide, "unmapped": sorted(unmapped)}


def names_known(names, name):
    return name in names.by_key.values()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out")
    p.add_argument("--raids"); p.add_argument("--gamemaster"); p.add_argument("--previous"); p.add_argument("--now")
    a = p.parse_args()

    def load(path, url, optional=False):
        try:
            return json.load(open(path)) if path else json.loads(fetch(url))
        except Exception:
            if optional:
                return None
            raise

    now = datetime.fromisoformat(a.now.replace("Z", "+00:00")) if a.now else datetime.now(timezone.utc)
    here = os.path.dirname(os.path.abspath(__file__))
    corrections = json.load(open(os.path.join(here, "corrections.json")))
    out = build(load(a.raids, RAIDS), load(a.gamemaster, GAMEMASTER), corrections,
                load(a.previous, None if a.raids else PUBLISHED, optional=True) if (a.previous or not a.raids) else None, now)
    with open(a.out, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"{len(out['raids'])} raids, {len(out['max'])} Max Battles, hidden {len(out['hide'])}, unknown: {out['unmapped'] or 'none'}")


if __name__ == "__main__":
    try:
        main()
    except (Invalid, KeyError, TypeError, ValueError) as e:
        sys.exit(f"Check failed, nothing published: {type(e).__name__} {e}")
