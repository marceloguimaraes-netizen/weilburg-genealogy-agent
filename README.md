# weilburg-genealogy-agent

A Claude Code agent that **validates a family tree** and looks for evidence beyond
FamilySearch — focused on Weilburg an der Lahn and the former Duchy of Nassau, and on the
family's emigration to Brazil.

## What it does

1. **Consistency check** (`tools/gedcom_check.py`, no dependencies): finds deaths before
   births, children born after a parent's death, impossible parent ages, child marriages,
   siblings born too close together, likely duplicates (including the same person entered once
   under a German and once under a Portuguese name, e.g. Wilhelm / Guilherme), loops in the
   tree, and unsourced people.
   Produces a ranked list of who to research next, with record-type hints by place and period.
2. **Research** (Claude Code skills): evaluates the evidence for each claim using the
   Genealogical Proof Standard, plans searches in Archion, Matricula, Arcinsys Hessen/HHStAW,
   LAGIS, Ortsfamilienbücher, passenger lists, and Brazilian sources (Arquivo Nacional/SIAN,
   Museu da Imigração SP, APEES Projeto Imigrantes, state archives, cartórios, parishes), checks what is
   actually online, transcribes and translates old German records you share as images,
   and keeps a research log per person.

## Getting started

1. Export your tree as GEDCOM (FamilySearch has no direct export: sync with RootsMagic or
   Ancestral Quest, or export from Ancestry / MyHeritage / Gramps) and put it in `trees/`.
2. Open this folder with Claude Code and type `/validate-tree`.
3. Then e.g. `/research-person Johann Philipp Weber, born 1801 Weilburg`.

You can also run the checker directly:

```bash
python3 tools/gedcom_check.py trees/my-tree.ged --out reports
python3 -m unittest discover -s tests
```

## Layout

| Path | Purpose |
|---|---|
| `CLAUDE.md` | Agent instructions: proof standard, rules, workflow |
| `.claude/skills/` | `/validate-tree` and `/research-person` |
| `knowledge/sources-weilburg-nassau.md` | German record sources outside FamilySearch, by period |
| `knowledge/sources-brazil.md` | Brazilian sources, colonies, name equivalents, Portuguese terms |
| `tools/gedcom_check.py` | GEDCOM consistency checker |
| `research/` | Per-person research logs (`TEMPLATE.md`) |
| `trees/`, `reports/` | Your data — gitignored, never pushed |

**Privacy:** keep information on living people out of `research/`; this repository may be shared.
