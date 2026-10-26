---
name: validate-tree
description: Validate a GEDCOM family tree export — run the consistency checker, explain impossible or suspicious facts, and rank who to research next. Use when the user adds or updates a tree file, or asks "is my tree correct?", "check my tree", "find errors".
---

# Validate a family tree

1. Find the tree: the newest `*.ged` in `trees/` (or the path the user gives). If there is
   none, tell the user how to export one: FamilySearch → *Tree* → no direct GEDCOM export,
   so use a desktop program synced with FamilySearch (e.g. RootsMagic or Ancestral Quest),
   or export from Ancestry / MyHeritage / Gramps / any genealogy program → *Export GEDCOM*. Save it in `trees/`.
2. Run `python3 tools/gedcom_check.py trees/<file>.ged --out reports`.
3. Read `reports/findings.json` and explain the results:
   - **Errors first**, grouped by family. For each: what the tree says, why it is
     impossible, and the most likely explanation (wrong person merged, typo in year,
     baptism date entered as birth, child attached to the wrong parents, namesake sibling).
   - **Warnings** — explain briefly; many will be fine once checked.
   - **Gaps** — just summarise the counts of unsourced people and people without dates.
4. Propose the top 5 people to research next (from `priorities`), with the reasons and
   record hints, and offer to start `/research-person` on the first one.
5. Do not change the GEDCOM yourself. List proposed corrections for the user to make in
   their genealogy program.

The checker's thresholds are in `LIMITS` at the top of `tools/gedcom_check.py`; tune
them if the user's tree produces too many warnings.
