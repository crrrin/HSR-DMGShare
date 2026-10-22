# HSR damage share — 0.1.1

Experimental standalone tool for associating displayed TOTAL DAMAGE values with action portraits. Designed to accept a reviewbot-selected video and battle interval later. No reviewbot files, webhooks or moderation decisions are modified.

## Windows setup

Extract the ZIP and open PowerShell inside the extracted `hsr-damage-share` folder.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Python 3.11 is the suggested local environment; this release was exercised on Python 3.12 in the build environment. FFprobe must be on PATH, or supply `--ffprobe "C:\path\to\ffprobe.exe"`.

## Scan a video

```powershell
.\.venv\Scripts\python.exe damage_share.py "C:\Users\<User>\Videos\battle.mp4" --team 1310 1321 --output work/test1
```

The example team IDs are Firefly and The Dahlia. Replace them with your team; one to four character IDs or quoted names can be supplied. Names must match `catalog.json`, including punctuation. The requested team's skins, enhanced forms and summons are included automatically, and totals aggregate to the parent character.

Select an interval using source-video seconds:

```powershell
.\.venv\Scripts\python.exe damage_share.py "C:\Videos\battle.mp4" --team 1310 1321 --start 237 --end 265 --output work/test2
```

Output timestamps stay relative to the original file. Use a new or empty output directory each time. Default sampling is 12 fps; change with `--fps`. This is damage scanning frequency, independent of the reviewbot's battle-boundary frequency.

Optional reviewbot OCR backend:

```powershell
.\.venv\Scripts\python.exe damage_share.py "C:\Videos\battle.mp4" --team 1310 1321 --backend reviewbot --reviewbot-root "C:\Users\<User>\Downloads\reviewbot-local" --model latin --output work/test3
```

It loads `auto/ocr.py` and requires the reviewbot's installed models. This adapter was retained but not exercised here. The default standalone backend uses RapidOCR's bundled models.

## Profiles and portraits

`asset_profile.json` defines normalized `[left, top, right, bottom]` regions for the active action portrait and damage panel, template sizes, threshold, and margin. It was calibrated against the supplied 1920x1080 clip. It scales with resolution but is not verified across HUD layouts, aspect ratios or letterboxing. A differing aspect ratio is rejected; a matching ratio alone is not proof of correct alignment.

Actor matching searches the active portrait region using opaque pixels of the RGBA assets. It compares the best score per parent character, so two variants of the same character do not compete against each other for the confidence margin. Unknown/weak matches stay unattributed. Restricting the roster also restricts attribution: provide the actual team and inspect debug output for false matches.

Catalog contents:

- 99 base portraits labeled from the supplied HTML.
- 12 acting variants labeled by the user.
- Mydei's enhanced background indicator stored with actor detection disabled.
- Seven skins labeled by the user.

Only the explicitly retained variants are included. `1404B_Active_Bg` remains despite its B because the user explicitly retained it. Variant labels are in `catalog.json`; every skin/summon/form has a parent character ID. Summons contribute to their owner's total, rather than becoming additional team members. Joint attacks currently belong entirely to the supplied parent mapping; the tool does not split their damage among participants.

`firefly_dahlia_profile.json` retains the previous screenshot-crop profile as a separate regression option. Use `--profile firefly_dahlia_profile.json` to exercise that older matching path.

## How attribution works

A separate marker region checks cyan ally and red enemy colour evidence before matching portraits. It accepts colour evidence without requiring circle/star/diamond shape. Unreadable markers produce an unknown actor; marker calibration is layout-specific. Both supplied cropped markers were classified correctly.

The current visible actor, pending next actor, and owner of the displayed damage are separate states. A stable portrait change alone does not transfer lingering damage. A stable changed number with a different pending actor closes the old event and starts a new one. Sustained panel disappearance also closes an event. OCR failure alone does not count as disappearance. Each event contributes one last stable total, rather than summing repeated readings. A turn without a new total does not inherit the preceding total. Confirmed enemy turns clear pending ally ownership; a changed value during an enemy turn is excluded from ally totals. The same actor after a confirmed enemy turn can begin a new event when its total changes.

This is a provisional heuristic. A still-running old action can increase its total after a new portrait appears and confuse ownership. Same-character consecutive actions without a blank panel, identical consecutive totals, DoT, assists, queued ultimates, and interrupted actions remain unresolved. Cataloging summons does not establish correct interruption handling. Stable OCR errors can still distort totals. Clip boundaries can truncate actions.

Every summary is marked `EXPERIMENTAL_REVIEW_REQUIRED`. Shares describe detected action-panel totals, not independently verified battle damage; there is no completeness percentage.

## Outputs

In the requested output folder:

- `damage_summary.json`: totals, shares, unattributed damage, version, team, profile/catalog hashes and timing.
- `damage_summary.csv`: per-character totals and shares; denominator includes unattributed damage.
- `action_observations.jsonl`: stable named ally observations with `damage_observed` or `no_damage_assigned`. The latter is not proof of zero damage; a missed detection can also produce it.
- `damage_events.jsonl`: accepted events, ownership, final values and evidence times.
- `damage_readings.jsonl`: each sample's actor scores, winning portrait ID, raw OCR, pending actor and displayed owner.
- `evidence/`: last accepted damage and observed portrait crop per event. The observed portrait can already belong to the next actor; use the timeline for ownership evidence.

## Validation

The supplied 4.1-second Firefly/Dahlia overlap clip, using the downloaded asset portraits at 12 fps, produced:

| Character | Damage | Detected share |
|---|---:|---:|
| Firefly | 491,203 | 74.11% |
| The Dahlia | 171,619 | 25.89% |

50 sampled frames, 39 OCR calls, approximately 4 seconds in this environment. Only this overlap clip was exercised with asset matching. Other characters/forms/skins and complete battles remain untested.

Run the ten tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -p "test_*.py"
```

GitHub Actions is configured to run those tests on pushes and pull requests; the workflow has not been executed on GitHub here. It does not run video/OCR tests; no user video is bundled.

## Version control

Create an empty GitHub repository, then from this folder:

```powershell
git init -b main
git add .
git commit -m "Initial damage share prototype v0.1.1"
git tag v0.1.1
git remote add origin https://github.com/YOUR_USERNAME/hsr-damage-share.git
git push -u origin main
git push origin v0.1.1
```

For each later change, review it with `git diff`, run tests, then commit/push. Use a branch for experiments. `.gitignore` excludes local environments, videos, work folders and secrets. Keep `CHANGELOG.md` and the script's `VERSION` in sync when making releases. The ZIP has no initialized Git history or configured remote.
