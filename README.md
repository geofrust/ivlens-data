# IV Lens data mirror

A weekly, checked copy of the public game data the IV Lens app downloads, served from GitHub Pages:
**https://geofrust.github.io/ivlens-data/**. Beside it, on the `bosses` branch, the raid and Max Battle bosses, checked
every 6 hours.

The app fetches from here instead of from the original sources directly, so the sources see one request a week rather
than one per user, and a broken or incomplete upstream file never reaches the app.

## What's here

| Path | Source |
|---|---|
| `gamemaster.json`, `rankings/<cup>/overall/rankings-<cp>.json` | [PvPoke](https://github.com/pvpoke/pvpoke) `src/data/`, same paths, all from one commit |
| `pve/fast_moves.json`, `pve/charged_moves.json` | [PoGoAPI](https://pogoapi.net) |
| `privacy.html`, `support.html` | The IV Lens app's privacy policy and support page (the App Store needs public links) |
| `manifest.json` | When it was built, the PvPoke commit, the entry count of each file, and any cup left out |

## The bosses

`bosses.json`, the only file on the [`bosses`](../../tree/bosses) branch: the raid bosses with their dates and the Max
Battle rotation by tier, from [Pokebattler](https://www.pokebattler.com)'s public API.
[`.github/workflows/bosses.yml`](.github/workflows/bosses.yml) runs [`bosses.py`](bosses.py) every 6 hours: one request
to Pokebattler, whatever the number of IV Lens users. It is checked (at least 3 raid bosses on now and 10 Max Battle
bosses, sensible dates, few unknown names); if it fails, the last copy stays.

[`corrections.json`](corrections.json) is for a boss the lists get wrong: `hide` one until a date, or `add` one with
its dates. The file says how. To turn the list off, disable the workflow and delete the branch: the app goes back to
its other lists.

## How it's built

[`.github/workflows/mirror.yml`](.github/workflows/mirror.yml) runs [`mirror.py`](mirror.py) every Monday (or by hand
from the Actions tab). The script downloads every file into a staging folder and checks it:

- the game master parses and has at least 1,000 Pokémon and 300 moves, and hasn't lost more than 5% of its Pokémon
  since the last published copy;
- each league's rankings have at least 300 entries, each cup's at least 20 (a failing cup is left out, as the app does);
- the move files parse and have the expected fields.

If a required file fails, the job stops and the copy already published stays as it was. Otherwise the folder is
published to Pages; its `manifest.json` records what went out.

## Licences and credit

- PvPoke data: MIT licence, Copyright (c) 2019 pvpoke. See [LICENSE-PvPoke](LICENSE-PvPoke).
- PoGoAPI data: provided by pogoapi.net, whose documentation recommends keeping a copy on your own server.
- Bosses: Pokebattler (Battler Empire, LLC), from its [public API](https://www.pokebattler.com/developers), which asks
  for attribution and caching; republished here with Pokebattler's agreement (2026-11-26).
- Pokémon and Pokémon GO are trademarks of their respective owners. This project is not affiliated with Niantic,
  Nintendo, The Pokémon Company or Game Freak.

## Where the source lives

This folder is kept in the (private) IV Lens app repository under `mirror/`. To publish a change, commit it there,
then push just this folder's files as one new commit on top of the public repository, so no private history or commit
messages come along (`git subtree push` would copy them):

```sh
git fetch ivlens-data
C=$(git commit-tree HEAD:mirror -p ivlens-data/main -m "Describe the change")
git push ivlens-data "${C}:refs/heads/main"
```
