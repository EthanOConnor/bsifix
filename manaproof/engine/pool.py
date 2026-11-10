"""The card pool: each card written as a program in the DSL.

`text` is a plain-language note describing the behaviour that is *modelled*
(not official rules text).  Simplifications are deliberate and listed in the
README; they are the trusted base of every certificate.
"""
from .dsl import *

T = cost(tap=True)
SAC_CREATURE = cost(sac=CREATURE)
NONLEG_OTHER = F("creature", no="legendary", other=True)

# ---- tokens ---------------------------------------------------------------
card("Elf Warrior", "creature", "G", pt=(1, 1), subs="elf warrior", token_def=True, text="1/1 token.")
card("Squirrel", "creature", "G", pt=(1, 1), subs="squirrel", token_def=True, text="1/1 token.")
card("Zombie", "creature", "B", pt=(2, 2), subs="zombie", token_def=True, text="2/2 token.")
card("Wurm", "artifact creature", "", pt=(3, 3), subs="wurm", token_def=True, text="3/3 artifact token.")
card("Saproling", "creature", "G", pt=(1, 1), subs="saproling", token_def=True, text="1/1 token.")
card("Treasure", "artifact", "", token_def=True, subs="treasure",
     ab=[act(cost(tap=True, sac="self"), any_color(1))], text="Tap, sacrifice: one mana of any colour.")

# ---- counters & persist ---------------------------------------------------
card("Devoted Druid", "creature", "G", 2, (0, 2), "elf druid",
     ab=[act(T, mana("G")), act(cost(putNeg=1), UNTAP_SELF)],
     text="Tap: add G. Put a -1/-1 counter on it: untap it.")
card("Vizier of Remedies", "creature", "W", 2, (2, 1), "human cleric", negReduce=True,
     text="-1/-1 counters put on your creatures are reduced by one.")
card("Melira, Sylvok Outcast", "legendary creature", "G", 2, (2, 2), "human scout", noNeg=True,
     text="Your creatures can't have -1/-1 counters put on them.")
card("Kitchen Finks", "creature", "GW", 3, (3, 2), "ouphe",
     ab=[kw("persist"), trig(ETB, gain(life=2))], text="Persist. Enters: gain 2 life.")
card("Murderous Redcap", "creature", "BR", 4, (2, 2), "goblin assassin",
     ab=[kw("persist"), trig(ETB, gain(opp=2))], text="Persist. Enters: damage equal to its power to the opponent (modelled as 2).")
card("Geralf's Messenger", "creature", "B", 3, (3, 2), "zombie",
     ab=[kw("undying"), trig(ETB, gain(opp=2))], entersTapped=True,
     text="Enters tapped. Undying. Enters: opponent loses 2.")
card("Young Wolf", "creature", "G", 1, (1, 1), "wolf", ab=[kw("undying")], text="Undying.")
card("Mikaeus, the Unhallowed", "legendary creature", "B", 6, (5, 5), "zombie cleric",
     grants=[grant(kw("undying"), F("creature", no="human", other=True)),
             grant(tough(1), F("creature", no="human", other=True))],
     text="Other non-Human creatures get +1/+1 and have undying.")
card("Walking Ballista", "artifact creature", "", 2, (0, 0), "construct", setupCtr=1,
     ab=[act(cost("4"), ctr_self(1)), act(cost(removeCtr=1), ping(1))],
     text="Enters with X counters (X=1 at setup). {4}: add a counter. Remove a counter: 1 damage.")
card("Spike Feeder", "creature", "G", 3, (0, 0), "spike", setupCtr=2, enterCtr=2,
     ab=[act(cost(removeCtr=1), gain(life=2)), act(cost("2", removeCtr=1), ctr_target(CREATURE))],
     text="Enters with two +1/+1 counters. Remove one: gain 2 life. {2}, remove one: counter on target creature.")
card("Ghave, Guru of Spores", "legendary creature", "WBG", 5, (0, 0), "fungus shaman", setupCtr=5, enterCtr=5,
     ab=[act(cost("1", removeCtr=1), token("Saproling")), act(cost("1", sac=CREATURE), ctr_target(CREATURE))],
     text="Enters with five counters. {1}, remove a counter: Saproling. {1}, sacrifice a creature: counter on target creature.")
card("Scurry Oak", "creature", "G", 3, (1, 2), "treefolk",
     ab=[trig(CTR_SELF, token("Squirrel"), optional=True)],
     text="Whenever +1/+1 counters are put on it, may create a 1/1 Squirrel. (Evolve not modelled.)")
card("Ivy Lane Denizen", "creature", "G", 4, (2, 3), "elf warrior",
     ab=[trig(etb_other(F("creature", color="G")), ctr_target(CREATURE))],
     text="Another green creature enters: +1/+1 counter on target creature.")
card("Cathars' Crusade", "enchantment", "W", 5,
     ab=[trig(etb_other(CREATURE), ctr_all(CREATURE))],
     text="A creature enters: +1/+1 counter on each of your creatures.")

# ---- sacrifice outlets & death triggers -----------------------------------
card("Viscera Seer", "creature", "B", 1, (1, 1), "vampire wizard",
     ab=[act(SAC_CREATURE)], text="Sacrifice a creature: scry 1.")
card("Ashnod's Altar", "artifact", "", 3, ab=[act(SAC_CREATURE, mana("CC"))],
     text="Sacrifice a creature: add CC.")
card("Phyrexian Altar", "artifact", "", 3, ab=[act(SAC_CREATURE, any_color(1))],
     text="Sacrifice a creature: one mana of any colour.")
card("Goblin Bombardment", "enchantment", "R", 2, ab=[act(SAC_CREATURE, gain(opp=1))],
     text="Sacrifice a creature: 1 damage to the opponent.")
card("Krark-Clan Ironworks", "artifact", "", 4, ab=[act(cost(sac=F("artifact")), mana("CC"))],
     text="Sacrifice an artifact: add CC.")
card("Blood Artist", "creature", "B", 2, (0, 1), "vampire",
     ab=[trig(dies_any(CREATURE), gain(opp=1, life=1))], text="A creature dies: opponent loses 1, you gain 1.")
card("Zulaport Cutthroat", "creature", "B", 2, (1, 1), "human rogue ally",
     ab=[trig(dies_any(CREATURE), gain(opp=1, life=1))], text="A creature of yours dies: opponent loses 1, you gain 1.")
card("Pitiless Plunderer", "creature", "B", 4, (1, 4), "human pirate",
     ab=[trig(dies_any(F("creature", other=True)), token("Treasure"))],
     text="Another creature of yours dies: create a Treasure.")
card("Dross Scorpion", "artifact creature", "", 4, (3, 1), "scorpion",
     ab=[trig(dies_any(F("artifact creature")), untap(F("artifact")), optional=True)],
     text="An artifact creature dies: may untap target artifact.")
card("Nim Deathmantle", "artifact equipment", "", 2, enchant=CREATURE,
     ab=[trig(dies_any(F("creature", nontoken=True)), ret("attach"), optional=True, pay=4)],
     text="A nontoken creature dies: may pay {4} to return it and attach this.")
card("Composite Golem", "artifact creature", "", 6, (4, 4), "golem",
     ab=[act(cost(sac="self"), mana("WUBRG"))], text="Sacrifice: add WUBRG.")
card("Wurmcoil Engine", "artifact creature", "", 6, (6, 6), "phyrexian wurm",
     ab=[trig(DIES, token("Wurm", 2))], text="Dies: two 3/3 Wurm tokens.")
card("Grave Titan", "creature", "B", 6, (6, 6), "giant",
     ab=[trig(ETB, token("Zombie", 2))], text="Enters: two 2/2 Zombies.")

# ---- copy / blink / untap creatures ---------------------------------------
card("Kiki-Jiki, Mirror Breaker", "legendary creature", "R", 5, (2, 2), "goblin shaman",
     ab=[kw("haste"), act(T, copy(NONLEG_OTHER))],
     text="Haste. Tap: hasty token copy of target nonlegendary creature.")
card("Zealous Conscripts", "creature", "R", 5, (3, 3), "human warrior",
     ab=[kw("haste"), trig(ETB, untap(ANY))], text="Haste. Enters: untap target permanent.")
card("Deceiver Exarch", "creature", "U", 3, (1, 4), "phyrexian cleric",
     ab=[trig(ETB, untap(ANY))], text="Enters: untap target permanent you control.")
card("Pestermite", "creature", "U", 3, (2, 1), "faerie rogue",
     ab=[trig(ETB, untap(ANY), optional=True)], text="Enters: may untap target permanent.")
card("Village Bell-Ringer", "creature", "W", 3, (1, 4), "human scout",
     ab=[trig(ETB, untap_all(CREATURE))], text="Enters: untap all your creatures.")
card("Restoration Angel", "creature", "W", 4, (3, 4), "angel",
     ab=[trig(ETB, blink(F("creature", no="angel")), optional=True)],
     text="Enters: may blink target non-Angel creature.")
card("Felidar Guardian", "creature", "W", 4, (1, 4), "cat beast",
     ab=[trig(ETB, blink(F(other=True)), optional=True)], text="Enters: may blink another target permanent.")
card("Saheeli Rai", "legendary planeswalker", "UR", 3, setupCtr=3, enterCtr=3, subs="saheeli",
     ab=[act(cost(loyal=True), ctr_self(1), gain(opp=1)),
         act(cost(loyal=True, removeCtr=2), copy(F("creature"))),
         act(cost(loyal=True, removeCtr=2), copy(F("artifact")))],
     text="Loyalty 3. +1: 1 damage. -2: hasty token copy of target artifact or creature.")
card("Midnight Guard", "creature", "W", 3, (2, 3), "human soldier",
     ab=[trig(etb_other(CREATURE), UNTAP_SELF)], text="Another creature enters: untap this.")
card("Intruder Alarm", "enchantment", "U", 3, ab=[trig(etb_other(CREATURE), untap_all(CREATURE))],
     text="A creature enters: untap all creatures.")
card("Seeker of Skybreak", "creature", "G", 2, (2, 1), "elf", ab=[act(T, untap(CREATURE))],
     text="Tap: untap target creature.")
card("Aphetto Alchemist", "creature", "U", 2, (1, 2), "human wizard",
     ab=[act(T, untap(CREATURE)), act(T, untap(F("artifact")))], text="Tap: untap target artifact or creature.")
card("Kiora's Follower", "creature", "GU", 2, (2, 2), "merfolk",
     ab=[act(T, untap(F(other=True)))], text="Tap: untap another target permanent.")
card("Tidewater Minion", "creature", "U", 5, (4, 4), "elemental minion",
     ab=[act(T, untap(ANY))], text="Tap: untap target permanent.")
card("Voltaic Construct", "artifact creature", "", 4, (2, 2), "golem construct",
     ab=[act(cost("2"), untap(F("artifact creature")))], text="{2}: untap target artifact creature.")
card("Voltaic Key", "artifact", "", 1, ab=[act(cost("1", tap=True), untap(F("artifact")))],
     text="{1}, tap: untap target artifact.")

# ---- ETB payoffs ----------------------------------------------------------
card("Impact Tremors", "enchantment", "R", 2, ab=[trig(etb_other(CREATURE), gain(opp=1))],
     text="A creature enters: 1 damage to the opponent.")
card("Soul Warden", "creature", "W", 1, (1, 1), "human cleric",
     ab=[trig(etb_other(CREATURE), gain(life=1))], text="Another creature enters: gain 1 life.")
card("Altar of the Brood", "artifact", "", 1, ab=[trig(etb_other(ANY), gain(mill=1))],
     text="Another permanent enters: opponent mills 1.")

# ---- life / drain ---------------------------------------------------------
card("Sanguine Bond", "enchantment", "B", 5, ab=[trig(LIFEGAIN, LOSE_THAT)],
     text="You gain life: opponent loses that much.")
card("Exquisite Blood", "enchantment", "B", 5, ab=[trig(OPPLOSS, GAIN_THAT)],
     text="Opponent loses life: you gain that much.")
card("Vito, Thorn of the Dusk Rose", "legendary creature", "B", 3, (1, 3), "vampire cleric",
     ab=[trig(LIFEGAIN, LOSE_THAT)], text="You gain life: opponent loses that much.")
card("Marauding Blight-Priest", "creature", "B", 3, (3, 2), "vampire cleric",
     ab=[trig(LIFEGAIN, gain(opp=1))], text="You gain life: opponent loses 1.")
card("Heliod, Sun-Crowned", "legendary enchantment", "W", 3, subs="god",
     ab=[trig(LIFEGAIN, ctr_target(CREATURE)), act(cost("1W"), lifelink(F("creature", other=True)))],
     text="You gain life: +1/+1 counter on target creature. {1}{W}: another target creature gains lifelink.")
card("Archangel of Thune", "creature", "W", 5, (3, 4), "angel",
     ab=[trig(LIFEGAIN, ctr_all(CREATURE))], text="You gain life: +1/+1 counter on each of your creatures.")

# ---- mana -----------------------------------------------------------------
card("Basalt Monolith", "artifact", "", 3, ab=[act(T, mana("CCC")), act(cost("3"), UNTAP_SELF)],
     text="Tap: add CCC. {3}: untap.")
card("Grim Monolith", "artifact", "", 2, ab=[act(T, mana("CCC")), act(cost("4"), UNTAP_SELF)],
     text="Tap: add CCC. {4}: untap.")
card("Mana Vault", "artifact", "", 1, ab=[act(T, mana("CCC"))], text="Tap: add CCC.")
card("Sol Ring", "artifact", "", 1, ab=[act(T, mana("CC"))], text="Tap: add CC.")
card("Thran Dynamo", "artifact", "", 4, ab=[act(T, mana("CCC"))], text="Tap: add CCC.")
card("Gilded Lotus", "artifact", "", 5, ab=[act(T, any_color(3))], text="Tap: three mana of one colour.")
card("Palladium Myr", "artifact creature", "", 3, (2, 2), "myr", ab=[act(T, mana("CC"))], text="Tap: add CC.")
card("Forsaken Monument", "legendary artifact", "", 5, bonusC=True,
     text="Whenever you tap a permanent for C, add one extra C.")
card("Power Artifact", "enchantment aura", "U", 2, enchant=F("artifact"), reduceHost=2,
     text="Enchanted artifact's abilities cost {2} less (minimum one mana).")
card("Freed from the Real", "enchantment aura", "U", 3, enchant=CREATURE,
     grants=[grant(act(cost("U"), UNTAP_SELF))], text="{U}: untap enchanted creature.")
card("Pemmin's Aura", "enchantment aura", "U", 3, enchant=CREATURE,
     grants=[grant(act(cost("U"), UNTAP_SELF))], text="{U}: untap enchanted creature.")
card("Umbral Mantle", "artifact equipment", "", 3, enchant=CREATURE,
     grants=[grant(act(cost("3", untap=True)))], text="Equipped creature has {3},{Q}: +2/+2.")
card("Presence of Gond", "enchantment aura", "G", 3, enchant=CREATURE,
     grants=[grant(act(T, token("Elf Warrior")))], text="Enchanted creature has Tap: create a 1/1 Elf Warrior.")
card("Staff of Domination", "artifact", "", 3,
     ab=[act(cost("1"), UNTAP_SELF), act(cost("2", tap=True), gain(life=1)),
         act(cost("3", tap=True), untap(CREATURE)), act(cost("5", tap=True), gain(draw=1))],
     text="{1}: untap this. {2},T: gain 1. {3},T: untap target creature. {5},T: draw.")
card("Bloom Tender", "creature", "G", 2, (1, 1), "elf druid", ab=[act(T, MANA_PER_COLOR)],
     text="Tap: one mana of each colour among your permanents.")
card("Priest of Titania", "creature", "G", 2, (1, 1), "elf druid", ab=[act(T, mana_per(F("elf"), "G"))],
     text="Tap: add G for each Elf.")
card("Elvish Archdruid", "creature", "G", 3, (2, 2), "elf druid", ab=[act(T, mana_per(F("elf"), "G"))],
     text="Tap: add G for each Elf you control.")
card("Cryptolith Rite", "enchantment", "G", 2, grants=[grant(act(T, any_color(1)), CREATURE)],
     text="Your creatures have Tap: one mana of any colour.")
card("Springleaf Drum", "artifact", "", 1, ab=[act(cost(tap=True, tapOther=CREATURE), any_color(1))],
     text="Tap, tap an untapped creature: one mana of any colour.")

DB = finalize()
POOL = [c.idx for c in DB if not c.is_token]
BY_NAME = {c.name: c.idx for c in DB}
