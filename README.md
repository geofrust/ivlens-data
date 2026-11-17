# IV Lens data mirror

A weekly, checked copy of the public game data the IV Lens app downloads, served from GitHub Pages:
**https://geofrust.github.io/ivlens-data/**

The app fetches from here instead of from the original sources directly, so the sources see one request a week rather
than one per user, and a broken or incomplete upstream file never reaches the app.

## What's here

| Path | Source |
|---|---|
| `gamemaster.json`, `rankings/<cup>/overall/rankings-<cp>.json` | [PvPoke](https://github.com/pvpoke/pvpoke) `src/data/`, same paths, all from one commit |
| `pve/fast_moves.json`, `pve/charged_moves.json` | [PoGoAPI](https://pogoapi.net) |
| `privacy.html` | The IV Lens app's privacy policy (the App Store needs a public link) |
| `manifest.json` | When it was built, the PvPoke commit, the entry count of each file, and any cup left out |

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
