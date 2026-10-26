---
name: research-person
description: Research and validate one person or couple in the family tree using sources beyond FamilySearch (Archion, Matricula, Arcinsys/HHStAW, LAGIS, Ortsfamilienbücher, emigration and destination-country records). Use when the user names an ancestor to verify, asks "is this right?", "find more about …", or wants a research plan.
---

# Research one person

## 1. Gather what the tree claims
- Get the person from the user, or from `reports/findings.json` / the GEDCOM in `trees/`
  (search by name or `@I…@` id). Collect: names and variants, events with dates and places,
  parents, spouses, children, and the sources currently attached.
- Read any existing log in `research/` for this person — do not repeat finished searches.

## 2. Evaluate the existing evidence
Make a table: *claim | current source | original or derivative | primary or secondary info |
direct or indirect | assessment*. A claim backed only by another tree, or by an index without
an image, is **not proven**.

## 3. Build a research plan
- Identify the parish and civil jurisdiction **for that year** (LAGIS / Meyers Gazetteer —
  villages changed parish and district).
- Pick record types from `knowledge/sources-weilburg-nassau.md` by period, and order them:
  the records most likely to answer the open question come first, then the cheapest ones.
- Include sources that confirm the person *indirectly*: siblings' baptisms (same parents),
  godparents, the parents' marriage, burial entries with age at death, emigration files,
  arrival records in the destination country.

## 4. Search what is online
Use WebSearch / WebFetch to check what is really available: Arcinsys finding-aid entries,
Archion parish coverage and years, Matricula parish lists, OFB entries, newspaper hits,
passenger lists. Report exact titles/signatures and URLs **only if you saw them**. Paid or
login-only sites (Archion, Ancestry) → tell the user exactly which book/year/page range to open.

If the user shares images of records, transcribe → translate → extract facts (see CLAUDE.md).

## 5. Conclude and record
- For each claim: *proven / probable / possible / not supported / disproven*, with reasoning.
- Proposed corrections to the tree.
- Next steps (specific records, who to write to — e.g. a sample request to the Standesamt or archive in German, if useful).
- Save/update `research/<Surname>_<Given>_<birthyear>.md` following `research/TEMPLATE.md`,
  including negative searches. Skip details about living people.
