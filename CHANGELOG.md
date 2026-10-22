# Changelog

## 0.1.1

- Cyan/red marker evidence gates portrait matching; unclear markers remain unknown.
- Non-damaging turns do not inherit lingering damage; action observations expose unassigned turns.
- Confirmed enemy turns clear pending actors and exclude changed enemy-turn values from ally totals.
- Track repeated same-character actions separated by a confirmed enemy turn.
- Ten tests; both supplied marker crops classified correctly; original overlap totals retained.

## 0.1.0

- Standalone displayed-action damage OCR, with source-relative timestamps and interval selection.
- Separate current actor, pending actor and displayed damage owner.
- Stable repeated readings; one final total per detected event.
- Catalog of 99 base portraits, 12 acting variants, one non-acting background indicator and seven skins.
- Optional masked asset matching with a supplied team and configurable active portrait region.
- Variants, summons and skins aggregate to parent character; raw logs retain the winning portrait ID.
- JSON/CSV summaries, per-frame diagnostics and evidence crops.
- Reviewbot OCR adapter retained; no automatic pipeline or webhook integration.

This release remains experimental. The overlap clip is a regression case, not proof of full-battle completeness.
