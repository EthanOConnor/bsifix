"""Regression tests: known combos are found, known non-combos are not, and the
Lean kernel agrees with the Python engine (run with `python3 -m unittest`)."""
import unittest
from engine.pool import DB, BY_NAME as N
from engine.model import Engine, ZERO, acc
from engine.search import search_set, check_cert
from engine.symbolic import Symbolic
from engine import leangen

E = Engine(DB)


def outcomes(*names):
    res, _ = search_set(E, [N[x] for x in names])
    return {o for r in res for o in r["outcomes"]}, res


class Search(unittest.TestCase):
    def test_known_pairs(self):
        for names, want in [
            (("Devoted Druid", "Vizier of Remedies"), "mana"),
            (("Kiki-Jiki, Mirror Breaker", "Zealous Conscripts"), "tokens"),
            (("Basalt Monolith", "Power Artifact"), "mana"),
            (("Felidar Guardian", "Saheeli Rai"), "tokens"),
            (("Walking Ballista", "Heliod, Sun-Crowned"), "damage"),
            (("Nim Deathmantle", "Composite Golem"), "mana"),
            (("Midnight Guard", "Presence of Gond"), "tokens"),
        ]:
            self.assertIn(want, outcomes(*names)[0], names)

    def test_known_triples(self):
        self.assertIn("life", outcomes("Kitchen Finks", "Viscera Seer", "Vizier of Remedies")[0])
        self.assertIn("damage", outcomes("Devoted Druid", "Vizier of Remedies", "Walking Ballista")[0])
        self.assertIn("damage", outcomes("Sanguine Bond", "Exquisite Blood", "Spike Feeder")[0])
        self.assertIn("damage", outcomes("Mikaeus, the Unhallowed", "Walking Ballista", "Viscera Seer")[0])

    def test_non_combos(self):
        # Melira makes the Druid's cost unpayable; Bond + Blood need a first life change
        self.assertFalse(outcomes("Devoted Druid", "Melira, Sylvok Outcast")[0])
        self.assertFalse(outcomes("Sanguine Bond", "Exquisite Blood")[0])
        self.assertFalse(outcomes("Mikaeus, the Unhallowed", "Walking Ballista")[0])
        self.assertFalse(outcomes("Kitchen Finks", "Viscera Seer")[0])

    def test_legend_rule(self):
        # copying a legendary Forsaken Monument must not double its bonus
        self.assertFalse(outcomes("Saheeli Rai", "Grim Monolith", "Forsaken Monument")[0])

    def test_single_return(self):
        # persist and Nim Deathmantle both try to return the same card: only one may succeed
        s = E.init_state([(N["Kitchen Finks"], -1), (N["Viscera Seer"], -1), (N["Nim Deathmantle"], -1)],
                         acc(c=4, life=20))
        s = E.run(s, [("act", 1, 0, ZERO, 0, 0, 0)])
        while s.stack:
            t = s.stack[0]
            s = E.step(s, ("resolve", acc(c=t.cost), 0, 0))
        self.assertEqual(sum(1 for p in s.bf if p.card == N["Kitchen Finks"]), 1)

    def test_filter_keeps_known(self):
        S = Symbolic(DB)
        for names in [("Devoted Druid", "Vizier of Remedies"), ("Nim Deathmantle", "Composite Golem"),
                      ("Vizier of Remedies", "Kiki-Jiki, Mirror Breaker", "Intruder Alarm"),
                      ("Devoted Druid", "Mikaeus, the Unhallowed", "Impact Tremors")]:
            self.assertTrue(S.candidate([N[x] for x in names]), names)


@unittest.skipUnless(leangen.find_lean(), "Lean toolchain not installed")
class Kernel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        leangen.write_cards(DB)
        ok, log = leangen.build_kernel()
        assert ok, log

    def cert(self, *names):
        _, res = outcomes(*names)
        r = res[0]
        return {"id": "test", "names": list(names), "claim": "test", "grade": r["grade"], "cards": r["cards"],
                "float": r["float"], "pre": r["pre"], "loop": r["loop"], "delta": r["delta"], "summary": r["summary"]}

    def test_accepts_true_certificates(self):
        for names in [("Devoted Druid", "Vizier of Remedies"), ("Kiki-Jiki, Mirror Breaker", "Zealous Conscripts"),
                      ("Kitchen Finks", "Viscera Seer", "Vizier of Remedies")]:
            v = leangen.verify(self.cert(*names))
            self.assertEqual(v["status"], "verified", v["log"])
            self.assertEqual(v["tactic"], "decide +kernel")

    def test_rejects_false_claim(self):
        c = self.cert("Devoted Druid", "Vizier of Remedies")
        c["delta"] = acc(g=2)                      # lie about the yield
        self.assertEqual(leangen.verify(c)["status"], "rejected")
        c = self.cert("Devoted Druid", "Vizier of Remedies")
        c["cards"] = [(N["Devoted Druid"], -1), (N["Melira, Sylvok Outcast"], -1)]   # swap in the wrong card
        self.assertEqual(leangen.verify(c)["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
