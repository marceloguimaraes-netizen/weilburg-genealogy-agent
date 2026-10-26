#!/usr/bin/env python3
"""Validate a GEDCOM family tree for impossible or suspicious facts.

Usage:
    python3 tools/gedcom_check.py trees/my-tree.ged [--out reports/]

Writes reports/report.md (human readable) and reports/findings.json
(machine readable, used by the research skills). Standard library only.
"""

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

DAYS_PER_YEAR = 365.2425

# Thresholds in years. "error" = biologically/logically impossible,
# "warn" = possible but unusual enough to deserve a second look.
LIMITS = {
    "mother_min_error": 11, "mother_min_warn": 15,
    "mother_max_warn": 47, "mother_max_error": 56,
    "father_min_error": 12, "father_min_warn": 16,
    "father_max_warn": 70, "father_max_error": 90,
    "marriage_min_warn": 15, "marriage_min_error": 11,
    "lifespan_warn": 100, "lifespan_error": 120,
    "posthumous_father_days": 300,
    "sibling_gap_days": 270,
    "duplicate_year_window": 2,
}

MONTHS = {m: i + 1 for i, m in enumerate(
    "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}
APPROX_YEARS = 2  # ABT/EST/CAL widen the range by this many years each side


# --------------------------------------------------------------------------
# GEDCOM parsing

@dataclass
class Node:
    level: int
    tag: str
    value: str = ""
    xref: str | None = None
    children: list["Node"] = field(default_factory=list)

    def first(self, *path):
        node = self
        for tag in path:
            node = next((c for c in node.children if c.tag == tag), None)
            if node is None:
                return None
        return node

    def all(self, tag):
        return [c for c in self.children if c.tag == tag]

    def walk(self):
        for c in self.children:
            yield c
            yield from c.walk()


LINE_RE = re.compile(r"^\s*(\d+)\s+(?:(@[^@]+@)\s+)?(\S+)(?:\s(.*))?$")


def read_text(path):
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_gedcom(text):
    roots, stack = [], []
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        level, xref, tag, value = int(m[1]), m[2], m[3].upper(), m[4] or ""
        if tag in ("CONC", "CONT") and stack:
            parent = stack[-1]
            parent.value += ("\n" if tag == "CONT" else "") + value
            continue
        node = Node(level, tag, value, xref)
        while stack and stack[-1].level >= level:
            stack.pop()
        (stack[-1].children if stack else roots).append(node)
        stack.append(node)
    return roots


# --------------------------------------------------------------------------
# Dates

@dataclass
class GDate:
    text: str
    lo: int | None  # earliest possible day ordinal
    hi: int | None  # latest possible day ordinal
    approx: bool = False
    exact_day: bool = False

    @property
    def mid(self):
        if self.lo is not None and self.hi is not None:
            return (self.lo + self.hi) / 2
        return self.lo if self.lo is not None else self.hi

    @property
    def year(self):
        return None if self.mid is None else date.fromordinal(int(self.mid)).year


def _simple(tokens):
    """Parse '[DD] [MON] YYYY' -> (lo, hi, exact_day) or None."""
    tokens = [t for t in tokens if t]
    if not tokens or not re.fullmatch(r"\d{1,4}(/\d{1,2})?", tokens[-1]):
        return None
    year = int(tokens[-1].split("/")[0])
    if year < 1:
        return None
    month = MONTHS.get(tokens[-2]) if len(tokens) >= 2 else None
    day = int(tokens[-3]) if len(tokens) >= 3 and tokens[-3].isdigit() else None
    try:
        if month and day:
            d = date(year, month, day).toordinal()
            return d, d, True
        if month:
            nxt = date(year + (month == 12), month % 12 + 1, 1).toordinal()
            return date(year, month, 1).toordinal(), nxt - 1, False
        return date(year, 1, 1).toordinal(), date(year, 12, 31).toordinal(), False
    except ValueError:
        return None


def parse_date(text):
    if not text:
        return None
    t = re.sub(r"@#D[^@]*@", "", text.upper()).strip()
    t = re.sub(r"\(.*?\)", "", t).strip()
    tok = t.replace(",", " ").split()
    if not tok:
        return None
    q = tok[0]
    if q in ("BET", "FROM") and ("AND" in tok or "TO" in tok):
        sep = tok.index("AND") if "AND" in tok else tok.index("TO")
        a, b = _simple(tok[1:sep]), _simple(tok[sep + 1:])
        if a and b:
            return GDate(text, a[0], b[1], approx=True)
    if q in ("BEF", "TO"):
        s = _simple(tok[1:])
        return GDate(text, None, s[1], approx=True) if s else None
    if q in ("AFT", "FROM"):
        s = _simple(tok[1:])
        return GDate(text, s[0], None, approx=True) if s else None
    if q in ("ABT", "EST", "CAL", "INT"):
        s = _simple(tok[1:])
        if not s:
            return None
        w = int(APPROX_YEARS * DAYS_PER_YEAR)
        return GDate(text, s[0] - w, s[1] + w, approx=True)
    s = _simple(tok)
    return GDate(text, s[0], s[1], exact_day=s[2]) if s else None


def years(days):
    return days / DAYS_PER_YEAR


def age_range(birth, event):
    """(min_age, mid_age, max_age) in years; any element may be None."""
    if not birth or not event:
        return None, None, None
    lo = years(event.lo - birth.hi) if event.lo is not None and birth.hi is not None else None
    hi = years(event.hi - birth.lo) if event.hi is not None and birth.lo is not None else None
    mid = years(event.mid - birth.mid) if event.mid is not None and birth.mid is not None else None
    return lo, mid, hi


# --------------------------------------------------------------------------
# Model

def fold(s):
    s = s.lower().replace("ß", "ss")
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue")):
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if c.isalnum() or c == " ").strip()


# Portuguese (and common spelling) forms of German given names, so that a person
# recorded in Germany and again in Brazil gets the same comparison key.
GIVEN_EQUIV = {
    "joao": "johann", "johannes": "johann", "hans": "johann",
    "guilherme": "wilhelm", "henrique": "heinrich", "henrich": "heinrich",
    "felipe": "philipp", "filipe": "philipp", "philip": "philipp", "phillip": "philipp",
    "jorge": "georg", "frederico": "friedrich", "carlos": "karl", "carl": "karl",
    "pedro": "peter", "jaco": "jakob", "jacob": "jakob", "jose": "joseph", "josef": "joseph",
    "catarina": "katharina", "catharina": "katharina", "margarida": "margaretha",
    "margaretta": "margaretha", "margarete": "margaretha", "isabel": "elisabeth",
    "elisabetha": "elisabeth", "elizabeth": "elisabeth", "madalena": "magdalena",
    "luiz": "ludwig", "luis": "ludwig", "adao": "adam", "cristiano": "christian",
    "cristina": "christina", "ana": "anna", "francisco": "franz", "antonio": "anton",
}


def name_key(name):
    parts = fold(name).split()
    return " ".join(GIVEN_EQUIV.get(w, w) for w in parts)


BRAZIL_WORDS = ("brasil", "brazil", "rio grande do sul", "santa catarina", "sao paulo", "parana",
                "espirito santo", "rio de janeiro", "minas gerais", "petropolis", "joinville",
                "blumenau", "sao leopoldo", "novo hamburgo", "nova friburgo", "brusque",
                "santa cruz do sul", "domingos martins", "santa leopoldina", "santa isabel")


def is_brazil(place):
    p = fold(place)
    return any(re.search(rf"\b{w}\b", p) for w in BRAZIL_WORDS)


@dataclass
class Event:
    tag: str
    date: GDate | None
    place: str
    sourced: bool


@dataclass
class Person:
    id: str
    name: str
    sex: str
    events: dict
    famc: list
    fams: list
    source_count: int

    def ev(self, *tags):
        for t in tags:
            e = self.events.get(t)
            if e and e.date:
                return e
        return None

    @property
    def birth(self):
        e = self.ev("BIRT", "CHR", "BAPM")
        return e.date if e else None

    @property
    def death(self):
        e = self.ev("DEAT", "BURI", "CREM")
        return e.date if e else None

    def label(self):
        b = self.birth.year if self.birth else "?"
        d = self.death.year if self.death else "?"
        return f"{self.name} ({b}–{d}) [{self.id}]"


@dataclass
class Family:
    id: str
    husb: str | None
    wife: str | None
    children: list
    marriage: Event | None


def event_of(node):
    d = node.first("DATE")
    p = node.first("PLAC")
    return Event(node.tag, parse_date(d.value) if d else None,
                 p.value.strip() if p else "", bool(node.all("SOUR")))


def build(roots):
    people, fams = {}, {}
    for r in roots:
        if r.tag == "INDI" and r.xref:
            n = r.first("NAME")
            name = re.sub(r"\s+", " ", n.value.replace("/", " ")).strip() if n else "(no name)"
            sex = (r.first("SEX").value.strip() if r.first("SEX") else "U") or "U"
            events = {}
            for c in r.children:
                if c.tag in ("BIRT", "CHR", "BAPM", "DEAT", "BURI", "CREM", "EMIG", "IMMI", "NATU", "RESI") \
                        and c.tag not in events:
                    events[c.tag] = event_of(c)
            srcs = sum(1 for c in r.walk() if c.tag == "SOUR")
            people[r.xref] = Person(r.xref, name or "(no name)", sex.upper()[:1], events,
                                    [c.value.strip() for c in r.all("FAMC")],
                                    [c.value.strip() for c in r.all("FAMS")], srcs)
        elif r.tag == "FAM" and r.xref:
            h, w, m = r.first("HUSB"), r.first("WIFE"), r.first("MARR")
            fams[r.xref] = Family(r.xref, h.value.strip() if h else None,
                                  w.value.strip() if w else None,
                                  [c.value.strip() for c in r.all("CHIL")],
                                  event_of(m) if m else None)
    return people, fams


# --------------------------------------------------------------------------
# Checks

@dataclass
class Finding:
    severity: str  # error | warning | info
    code: str
    message: str
    people: list


def check(people, fams):
    out = []
    L = LIMITS

    def add(sev, code, msg, *ids):
        out.append(Finding(sev, code, msg, [i for i in ids if i]))

    for p in people.values():
        b, d = p.birth, p.death
        if b and d:
            lo, mid, hi = age_range(b, d)
            if hi is not None and hi < 0:
                add("error", "death_before_birth", f"{p.label()} dies before being born "
                    f"(birth {b.text}, death {d.text}).", p.id)
            elif lo is not None and lo > L["lifespan_error"]:
                add("error", "lifespan", f"{p.label()} would have lived {lo:.0f}+ years.", p.id)
            elif mid is not None and mid > L["lifespan_warn"]:
                add("warning", "lifespan", f"{p.label()} lived about {mid:.0f} years — "
                    "check for two people merged into one.", p.id)
        deat, buri = p.events.get("DEAT"), p.events.get("BURI")
        if deat and buri and deat.date and buri.date and buri.date.hi is not None \
                and deat.date.lo is not None and buri.date.hi < deat.date.lo:
            add("error", "burial_before_death", f"{p.label()} is buried before death.", p.id)
        if not p.birth:
            add("info", "no_birth_date", f"{p.label()} has no birth or baptism date.", p.id)
        if p.source_count == 0:
            add("info", "unsourced", f"{p.label()} has no sources attached.", p.id)

    for f in fams.values():
        husb, wife = people.get(f.husb), people.get(f.wife)
        kids = [people[c] for c in f.children if c in people]
        for parent, role in ((wife, "mother"), (husb, "father")):
            if not parent:
                continue
            for k in kids:
                if not k.birth:
                    continue
                if parent.birth:
                    lo, mid, hi = age_range(parent.birth, k.birth)
                    if hi is not None and hi < L[f"{role}_min_error"]:
                        add("error", f"{role}_too_young", f"{parent.label()} would be under "
                            f"{hi:.0f} at the birth of child {k.label()}.", parent.id, k.id)
                    elif lo is not None and lo > L[f"{role}_max_error"]:
                        add("error", f"{role}_too_old", f"{parent.label()} would be over "
                            f"{lo:.0f} at the birth of child {k.label()}.", parent.id, k.id)
                    elif mid is not None and mid < L[f"{role}_min_warn"]:
                        add("warning", f"{role}_young", f"{parent.label()} was about {mid:.0f} "
                            f"at the birth of {k.label()}.", parent.id, k.id)
                    elif mid is not None and mid > L[f"{role}_max_warn"]:
                        add("warning", f"{role}_old", f"{parent.label()} was about {mid:.0f} "
                            f"at the birth of {k.label()}.", parent.id, k.id)
                pd = parent.death
                if pd and pd.hi is not None and k.birth.lo is not None:
                    grace = 0 if role == "mother" else L["posthumous_father_days"]
                    gap = k.birth.lo - pd.hi
                    if gap > grace:
                        add("error", f"child_after_{role}_death", f"{k.label()} was born "
                            f"{years(gap):.1f} years after {role} {parent.label()} died.",
                            parent.id, k.id)

        m = f.marriage
        if m and m.date:
            for sp in (husb, wife):
                if not sp:
                    continue
                if sp.birth:
                    lo, mid, hi = age_range(sp.birth, m.date)
                    if hi is not None and hi < L["marriage_min_error"]:
                        add("error", "married_as_child", f"{sp.label()} would be about "
                            f"{mid:.0f} at marriage ({m.date.text}).", sp.id)
                    elif mid is not None and mid < L["marriage_min_warn"]:
                        add("warning", "married_young", f"{sp.label()} married at about "
                            f"{mid:.0f} ({m.date.text}).", sp.id)
                if sp.death and sp.death.hi is not None and m.date.lo is not None \
                        and m.date.lo > sp.death.hi:
                    add("error", "married_after_death", f"{sp.label()} marries after death "
                        f"({m.date.text}).", sp.id)

        exact = sorted((k for k in kids if k.birth and k.birth.exact_day), key=lambda k: k.birth.lo)
        for a, b in zip(exact, exact[1:]):
            gap = b.birth.lo - a.birth.lo
            if 2 < gap < L["sibling_gap_days"]:
                add("warning", "siblings_too_close", f"Siblings {a.label()} and {b.label()} "
                    f"were born only {gap} days apart.", a.id, b.id)

    # Possible duplicates: same folded name, birth years within a small window.
    buckets = {}
    for p in people.values():
        buckets.setdefault(name_key(p.name), []).append(p)
    for name, group in buckets.items():
        if len(group) < 2 or not name:
            continue
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a.birth and b.birth and abs(a.birth.year - b.birth.year) \
                        <= L["duplicate_year_window"]:
                    add("warning", "possible_duplicate", f"{a.label()} and {b.label()} may be "
                        "the same person (or a child who died young and a later namesake).",
                        a.id, b.id)

    # Someone who is their own ancestor.
    def parents_of(pid):
        for fid in people[pid].famc:
            f = fams.get(fid)
            if f:
                yield from (x for x in (f.husb, f.wife) if x in people)

    for pid in people:
        seen, stack = set(), list(parents_of(pid))
        while stack:
            q = stack.pop()
            if q == pid:
                add("error", "own_ancestor", f"{people[pid].label()} is their own ancestor "
                    "(loop in parent links).", pid)
                break
            if q not in seen:
                seen.add(q)
                stack.extend(parents_of(q))
    return out


# --------------------------------------------------------------------------
# Research hints: which record types to look for, by place and period.

def hints_for(event, kind):
    if not event or not event.place:
        return []
    place, yr = fold(event.place), (event.date.year if event.date else None)
    h = []
    german = any(w in place for w in ("weilburg", "nassau", "hessen", "hesse", "limburg",
                                      "lahn", "wiesbaden", "deutschland", "germany", "preussen"))
    if german:
        if yr is None or yr < 1875:
            h.append(f"{kind}: Lutheran/Reformed church book (Archion — EKHN) or Catholic "
                     "register (Matricula / Diözesanarchiv Limburg)")
        if yr is None or 1818 <= yr <= 1874:
            h.append(f"{kind}: Nassau church-book duplicates at Hessisches Hauptstaatsarchiv "
                     "Wiesbaden (search Arcinsys Hessen)")
        if yr is None or yr >= 1874:
            h.append(f"{kind}: civil register (Standesamt) — post-1874 Prussian civil "
                     "registration; older registers often in the Stadt-/Kreisarchiv or HHStAW")
        h.append("Local Ortsfamilienbuch (online-ofb.de / HFV) and LAGIS Hessen gazetteer for the parish")
    if is_brazil(event.place):
        h.append(f"{kind}: Catholic parish register (Cúria diocesana) or Lutheran congregation "
                 "book (IECLB/IELB)" + (" — Catholic baptisms often name all four grandparents"
                                        if kind in ("birth", "baptism") else ""))
        civil_from = 1890 if kind == "marriage" else 1889
        if yr is None or yr >= civil_from:
            h.append(f"{kind}: civil registry (Cartório de Registro Civil) — ask for a "
                     "certidão de inteiro teor")
        if kind in ("marriage", "death", "burial"):
            h.append(f"{kind}: may name the German birthplace — check for 'natural de …'")
        if kind in ("death", "burial"):
            h.append("Probate (inventário) in the state court or state archive (e.g. APERS in RS)")
    if any(w in place for w in ("usa", "united states", "texas", "wisconsin", "ohio", "new york",
                                "pennsylvania", "missouri", "illinois")):
        h.append(f"{kind}: state vital records, county courthouse, church records; "
                 "census and naturalization files")
    return h


def priorities(people, fams, findings, top=30):
    weight = {"error": 5, "warning": 2, "info": 1}
    score = {pid: 0 for pid in people}
    reasons = {pid: [] for pid in people}
    for f in findings:
        for pid in f.people:
            score[pid] += weight[f.severity]
            reasons[pid].append(f.code)
    for p in people.values():
        if not p.famc or all(fams.get(fid) is None for fid in p.famc):
            score[p.id] += 1
            reasons[p.id].append("no_parents_in_tree")
    rows = []
    for pid, s in sorted(score.items(), key=lambda kv: -kv[1])[:top]:
        p = people[pid]
        hints = []
        for tag, kind in (("BIRT", "birth"), ("CHR", "baptism"), ("DEAT", "death"),
                          ("BURI", "burial")):
            hints += hints_for(p.events.get(tag), kind)
        for fid in p.fams:
            fam = fams.get(fid)
            if fam and fam.marriage:
                hints += hints_for(fam.marriage, "marriage")
        places = [e.place for e in p.events.values() if e.place]
        if any(is_brazil(pl) for pl in places) and any(not is_brazil(pl) for pl in places):
            hints.append("Immigrant to Brazil: Arquivo Nacional/SIAN (arrival lists, "
                         "naturalisation 1823–1959), Museu da Imigração SP (1882–1958), APEES "
                         "Projeto Imigrantes (Espírito Santo), state archives of the colony — "
                         "see knowledge/sources-brazil.md")
        if p.events.get("EMIG") or p.events.get("IMMI"):
            hints.append("Emigration: HHStAW emigration files (LAGIS emigrant database), "
                         "Hamburg passenger lists, Bremen lists (passagierlisten.de), "
                         "destination arrival records")
        rows.append({"id": pid, "label": p.label(), "score": s,
                     "reasons": sorted(set(reasons[pid])),
                     "hints": list(dict.fromkeys(hints))})
    return rows


# --------------------------------------------------------------------------
# Output

def render_markdown(path, people, fams, findings, prio):
    order = {"error": 0, "warning": 1, "info": 2}
    findings = sorted(findings, key=lambda f: (order[f.severity], f.code))
    counts = {s: sum(f.severity == s for f in findings) for s in order}
    lines = [f"# Tree validation report — {Path(path).name}", "",
             f"{len(people)} people, {len(fams)} families. "
             f"**{counts['error']} errors**, {counts['warning']} warnings, "
             f"{counts['info']} informational notes.", ""]
    for sev, title in (("error", "Errors (impossible as recorded)"),
                       ("warning", "Warnings (unusual — verify)")):
        lines += [f"## {title}", ""]
        items = [f for f in findings if f.severity == sev]
        lines += [f"- `{f.code}` — {f.message}" for f in items] or ["- None"]
        lines.append("")
    info = [f for f in findings if f.severity == "info"]
    lines += ["## Gaps", ""]
    for code, title in (("unsourced", "No sources"), ("no_birth_date", "No birth/baptism date")):
        items = [f for f in info if f.code == code]
        lines.append(f"- **{title}:** {len(items)} people")
    lines += ["", "## Research priorities", "",
              "Ranked by problems found and missing evidence. Hints are starting points, "
              "not guarantees that a record exists.", ""]
    for r in prio:
        if r["score"] == 0:
            continue
        lines.append(f"### {r['label']} — score {r['score']}")
        lines.append(f"Reasons: {', '.join(r['reasons'])}")
        lines += [f"- {h}" for h in r["hints"]]
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("gedcom")
    ap.add_argument("--out", default="reports")
    ap.add_argument("--top", type=int, default=30, help="number of research priorities")
    args = ap.parse_args(argv)

    people, fams = build(parse_gedcom(read_text(args.gedcom)))
    if not people:
        sys.exit("No individuals found — is this a GEDCOM file?")
    findings = check(people, fams)
    prio = priorities(people, fams, findings, args.top)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(render_markdown(args.gedcom, people, fams, findings, prio),
                                   encoding="utf-8")
    (out / "findings.json").write_text(json.dumps({
        "file": str(args.gedcom), "people": len(people), "families": len(fams),
        "findings": [f.__dict__ for f in findings], "priorities": prio,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    n_err = sum(f.severity == "error" for f in findings)
    n_warn = sum(f.severity == "warning" for f in findings)
    print(f"{len(people)} people, {len(fams)} families: {n_err} errors, {n_warn} warnings.")
    print(f"Report: {out / 'report.md'}")


if __name__ == "__main__":
    main()
