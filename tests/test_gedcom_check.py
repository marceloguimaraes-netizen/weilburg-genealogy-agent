import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import gedcom_check as gc  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "sample.ged"


class DateTests(unittest.TestCase):
    def test_exact(self):
        d = gc.parse_date("12 MAR 1801")
        self.assertTrue(d.exact_day)
        self.assertEqual(d.lo, d.hi)

    def test_year_only_spans_year(self):
        d = gc.parse_date("1801")
        self.assertEqual(d.hi - d.lo, 364)

    def test_qualifiers(self):
        self.assertIsNone(gc.parse_date("BEF 1840").lo)
        self.assertIsNone(gc.parse_date("AFT 1840").hi)
        bet = gc.parse_date("BET 1840 AND 1845")
        self.assertEqual(gc.date.fromordinal(bet.lo).year, 1840)
        self.assertEqual(gc.date.fromordinal(bet.hi).year, 1845)
        self.assertTrue(gc.parse_date("ABT 1802").approx)

    def test_unparseable(self):
        self.assertIsNone(gc.parse_date("(unknown)"))
        self.assertIsNone(gc.parse_date(""))


class NameAndPlaceTests(unittest.TestCase):
    def test_name_key(self):
        self.assertEqual(gc.name_key("João Felipe /Müller/"), gc.name_key("Johann Philipp Mueller"))
        self.assertEqual(gc.name_key("Catarina Weber"), gc.name_key("Katharina Weber"))

    def test_is_brazil(self):
        self.assertTrue(gc.is_brazil("São Leopoldo, Rio Grande do Sul"))
        self.assertTrue(gc.is_brazil("Petrópolis, RJ, Brasil"))
        self.assertFalse(gc.is_brazil("Weilburg, Nassau, Deutschland"))


class CheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.people, cls.fams = gc.build(gc.parse_gedcom(gc.read_text(FIXTURE)))
        cls.findings = gc.check(cls.people, cls.fams)
        cls.codes = {(f.code, tuple(sorted(f.people))) for f in cls.findings}

    def has(self, code, *ids):
        return (code, tuple(sorted(ids))) in self.codes

    def test_planted_errors_found(self):
        self.assertTrue(self.has("death_before_birth", "@I7@"))
        self.assertTrue(self.has("child_after_mother_death", "@I2@", "@I5@"))
        self.assertTrue(self.has("siblings_too_close", "@I3@", "@I4@"))
        self.assertTrue(self.has("married_as_child", "@I3@"))
        self.assertTrue(self.has("possible_duplicate", "@I1@", "@I6@"))
        self.assertTrue(self.has("own_ancestor", "@I10@"))

    def test_no_false_positive_on_valid_parent_ages(self):
        bad = [f for f in self.findings if "@I1@" in f.people
               and f.code.startswith(("father_", "child_after_father"))]
        self.assertEqual(bad, [])

    def test_sources_counted(self):
        self.assertEqual(self.people["@I1@"].source_count, 1)
        self.assertTrue(self.has("unsourced", "@I2@"))

    def test_hints_for_nassau_period(self):
        hints = gc.hints_for(self.people["@I3@"].events["BIRT"], "birth")  # 1826
        self.assertTrue(any("Archion" in h for h in hints))
        self.assertTrue(any("Hauptstaatsarchiv" in h for h in hints))
        self.assertFalse(any("Standesamt" in h for h in hints))
        # 1801 predates the 1818 Nassau duplicate registers
        early = gc.hints_for(self.people["@I1@"].events["BIRT"], "birth")
        self.assertFalse(any("Hauptstaatsarchiv" in h for h in early))

    def test_portuguese_namesake_flagged_as_duplicate(self):
        self.assertTrue(self.has("possible_duplicate", "@I5@", "@I12@"))

    def test_brazil_hints(self):
        death = self.people["@I12@"].events["DEAT"]  # 1910, Joinville
        hints = gc.hints_for(death, "death")
        self.assertTrue(any("inteiro teor" in h for h in hints))
        self.assertTrue(any("natural de" in h for h in hints))
        self.assertFalse(any("Archion" in h for h in hints))
        prio = {r["id"]: r for r in gc.priorities(self.people, self.fams, self.findings, 50)}
        self.assertTrue(any("SIAN" in h for h in prio["@I12@"]["hints"]))

    def test_cli_writes_reports(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            gc.main([str(FIXTURE), "--out", tmp])
            self.assertTrue((Path(tmp) / "report.md").exists())
            self.assertTrue((Path(tmp) / "findings.json").exists())


if __name__ == "__main__":
    unittest.main()
