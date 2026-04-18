# FlexAI for Combat Encounters — Rules

> Verbatim extract of the *FlexAI Guidebook* (Infinium Game Studios, 2020),
> pp. 12–22.  Copyright Infinium Game Studios.  Kept here for quick GM
> reference while using `flexai_combat.py`.

## What is FlexAI?

FlexAI is an attempt to model and simulate monster and NPC behavior in a
combat encounter.  It scales in complexity from very simple to as complex
as you as a GM would like it to be.  It can be used in any tabletop
roleplaying game with zero preparation time.

The system takes only a few minutes to learn, is easy and quick to use,
and can enhance any tabletop roleplaying combat experience.

## How to Use FlexAI

### Sanity Checks & Rerolls

Generally speaking, if something "feels wrong", reroll it.

More specifically, if the Outcome determined by FlexAI does not apply
(e.g., creature lacks a ranged attack altogether) or are inappropriate to
the circumstances (e.g., maneuver when the creature is surrounded by
melee opponents), reroll the result to determine a more appropriate
Outcome.

### Three Tiers of Complexity

Not everyone needs, or is interested in, complex AI combat mechanics.
Sometimes, you just want to quickly roll on a single table, and determine
an outcome.

Conversely, some gaming groups like the thrill of the unknown, and like
to add even more.

To support this array of interests, FlexAI provides three levels of
complexity: **Simple**, **Full**, and **Advanced**.

You can pick and choose which of these three approaches you wish to
employ.  You can even switch the method used at any time — even
round-to-round within the scope of the same combat and monsters!

## Behavior Common Concepts

All three levels of complexity share two elements: **Outcomes**, and
**Targeting**.

Simply put, these are what you need to determine the behavior of a
creature in combat.

- **Targeting** dictates *who* the creature attacks.
- **Outcomes** dictate *how* it goes about it.

Together, Outcome and Targeting are referred to as a creature's
**behavior**.

### Combat Outcomes

All three levels of FlexAI difficulty involve Combat Outcomes as the main
output of using the tool.

This represents the behavior of a creature in the combat situation.

Note that not every Combat Outcome necessarily applies to every creature.
For example, not every creature has both a primary and a secondary attack.
The GM is encouraged to use sanity check outcomes (see above).

If the Outcome determined does not require a target, ignore the Targeting
aspect of the behavior determined.

**Table 2: Combat Outcomes**

| Outcome | Description |
| --- | --- |
| **Attack Main** | Creature attacks its target using its standard attack.  For most creatures, this will be melee; for others, it will be ranged. |
| **Attack Secondary** | If the creature's main attack is Melee, the creature attacks using a Ranged attack, and vice versa. |
| **Maneuver** | Creature moves about, either to get closer to its preferred target (see Targeting), to evade the enemies currently surrounding it, or to take advantage of battlefield characteristics. |
| **Use / Defend** | Creature uses an item, such as a wand or staff or potion.  If it does not carry one, creature takes a defensive stance. |
| **Ability** | Creature uses a special ability against its current target.  If it lacks any special abilities, or none of its abilities apply, reroll this result. |
| **Flee** | Creature tries to flee the combat encounter entirely.  This creature flees in a direction most away from its current Target. |

### Combat Targeting

In many circumstances, you can simply use the Outcome to dictate the
current round's worth of behavior for a given creature.  During most
combat, a creature's current target does not change round-to-round.

However, there is value in dynamically changing targeting using FlexAI
rules.

First, it can make things very interesting and keep PCs off their guard
if a monster changes its target from round to round.  Intelligent
monsters might do so even if it serves to their temporary disadvantage
(e.g., if it triggers attacks of opportunity or a less favorable
battlefield positioning).

Second, creatures who are not typically invovled in melee as their
primary combat approach might indeed change their target round-to-round,
particularly if their attacks or abilities inflict status changes (e.g.,
debuffs) or spell effects.

**Table 3: Combat Targeting Summary**

| Outcome | Description |
| --- | --- |
| **Frontline** | The frontmost adversaries.  This can be, but is not always, the same as the **Closest** enemy.  For the purposes of determining "front" and "back", consider the starting positions of each side in the battle; the frontmost creatures of either side are those who began the combat encounter closest to their enemies. |
| **Rearguard** | As **Frontline**, but the rear-most enemies. |
| **Closest** | The opponent which is currently physically closest to this creature.  In most melee circumstances, this represents the creature's current target. |
| **Farthest** | The opponent which is currently physically farthest away from this creature. |
| **Strongest** | The enemy who is currently "strongest", healthiest, or furthest from death.  Typically this can be represented by the enemy with the most current hit points. |
| **Weakest** | As **Strongest**, but the enemy closest to death. |
| **Ranged Enemy** | Targets an enemy who uses a ranged attack as their primary attack. |
| **Melee Enemy** | As **Ranged Enemy**, but select an enemy who uses a melee attack as their primary mode of attack. |

## Simple AI Rules

Simple AI rules assume the most common circumstances of the creature
involved, the combat environment, and the status of the participants.

### Advantages & When to Use

Much of the time, the single table that results will provide a rich,
dynamic result.  The single dice roll, the fact that it's a d20 as
opposed to a d100, and the fact that there is a single table that does
not have to be looked up (and indeed, whose contents could even be
memorized) all make using the Simple AI approach very easy and quick to
integrate.

### Limitations

It should be noted that the entire purpose of design behind the FlexAI
concept is intended to acount for a more nuanced, contextually-appropriate
pool of results and related probability.  An elder dragon at full health
should simply not behave anything similar to a lurking thief hiding in
the shadows; the Simple AI approach cannot take this into account.

**Table 4: Simple AI Outcomes**

| d20 | Outcome |
| --- | --- |
| 01–12 | Attack Main |
| 13–14 | Attack Secondary |
| 15 | Maneuver |
| 16 | Use / Defend |
| 17–19 | Ability |
| 20 | Flee |

**Table 5: Simple AI Targeting**

| d20 | Outcome |
| --- | --- |
| 01–05 | Frontline |
| 06–07 | Rearguard |
| 08–13 | Closest |
| 14 | Farthest |
| 15–16 | Strongest |
| 18 | Weakest |
| 19 | Ranged Enemy |
| 20 | Melee Enemy |

> Note: the Guidebook leaves roll 17 unmapped on the Targeting d20 table.
> Treat a 17 as a reroll.

## Full AI Rules

This is the heart of FlexAI and its power to provide
contextually-appropriate combat actions.

Instead of traditional tables, you use **FlexTables** (see the overview
of FlexTale earlier in this document).  And instead of using the same
table regardless of what is going on, you intelligently select the
appropriate FlexTable based on the nature of the creature involved and
the battlefield circumstances.

In short, the concepts of Outcomes and Targeting still apply; it's just
a matter of how they are determined.

### Additional Factors: Role & Stance

To determine which FlexTable is most appropriate for the monster and
combat circumstances, Full AI rules require two additional elements:
**Roles** and **Stances**.

- A creature's **Role** represents its typical combat behavior and
  approach to battle.
- A creature's **Stance** indicates its current combat circumstances.

Together, these two factors help determine the contextual probabilities
that should apply to the creature's behavior in combat.

### Combat Roles

**Table 6: Combat Roles**

| Role | Description |
| --- | --- |
| **Brute** | Inflicts high damage, typically via melee attacks.  Has a great deal of hit points, but possibly low defenses.  Examples: Ape, Bear, Cyclops, most Dinosaurs, most Elementals, most Giants.  Classes: Barbarian, some Fighters. |
| **Soldier** | Focuses on defense, usually in melee, but can also have high ranged defenses.  Average health, and a variety of attack strengths.  Examples: Giant ants, Boars, most Demons, most Devils, most Golems.  Classes: Most Fighters; some Paladins and Clerics. |
| **Artillery** | Ranged attacks are the main focus of Artillery.  Typically have very low hit points and/or defenses, however.  Examples: Tritons, Pale Stranger, some Gremlins, Rangers and many Elves.  Classes: Rangers; some Fighters and Rogues. |
| **Skirmisher** | Skirmishers may be average in many categories, but excel in mobility, and use this to their tactical advantage in selecting targets where they can do the most damage.  Examples: Badgers, Bats, Beetles, Chimeras, some Demons, nimble Dinosaurs, Gargoyles, Hawks, Harpies, Owls, Rats.  Classes: Rogues, Rangers, Bards. |
| **Lurker** | Most Lurkers prefer to surprise or ambush their opponents, or to remove themselves from the possibility of easy attack once battle is joined.  Examples: Assassin Vines, Basilisks, most Oozes, Chokers, Doppelgangers, Ghosts, Ghouls, most Undead.  Classes: Rogues and Bards. |
| **Controller** | Controllers typically have sets of abilities that allow them to force enemies into disadvantage, either by moving enemies around, or controlling the battlefield itself.  Examples: Chaos Beasts, some Dragons, Hydras, Nagas.  Classes: Wizards, Sorcerers, some Clerics. |
| **Leader** | Leaders are special creatures with sets of abilities that make them a force to be reckoned with regardless of the circumstances.  Although "leader" typically indicates that the creature is in charge of others, Leader creatures may be encountered on their own.  Examples: Behemoths, many Demons, most Dragons, Rakshasas, Vampires.  Classes: Paladins, some Clerics and Fighters. |

### Combat Role Variations

**Table 7: Combat Role Variations**

| Role Variant | Description |
| --- | --- |
| **Normal** | Many monsters and most NPCs fall into this category.  Neither particularly powerful nor weaksauce, Normal creatures are just that: normal. |
| **Minion** | Minions are weaker than Normal creatures, and are rarely found in the absence of a ruling, more powerful, presence.  Typically, Minions are encountered in groups. |
| **Elite** | Elite creatures are powerful, flexible, and formidable enemies.  A single Elite creature might rule over dozens of Minions and several Normal creatures in a complex combat encounter. |
| **Solo** | Solo creatures are often special cases: typically discovered on their own, they usually have sufficient power and ability to represent a significant challenge in and of themselves. |
| **Mindless** | Mindless creatures do not typically think or plan their combat reactions, and simply act from a visceral, second-to-second standpoint.  Most of the time, this means fighting to the death, but even Mindless creatures can make combat actions that spice things up a bit from the typical "skeleton keeps attacking the first PC they see" approach to things. |

### Combat Stances

**Table 8: Combat Stances**

| Stance | Description |
| --- | --- |
| **Ambushing** | The creature is ambushing its prey: lying in wait, hiding, or using stealth, invisibility, or aspects of the terrain to make their presence unknown until the moment to strike is nigh. |
| **Unprepared** | The reverse of Ambushing, in a way: the creature is surprised by the PCs, or is aware of them, but not ready to participate in combat. |
| **Fresh** | In most combats, creatures begin the encounter in this Stance: well-rested, at full hit points, and ready to do battle. |
| **Bloodied** | Creatures fight differently when they have suffered wounds.  Some fight more aggressively; others become more defensive; many will tend toward fleeing outright if brought low by injury. |
| **Cornered** | Creatures who are Cornered have few options in terms of maneuverability, either as a result of the combat environment, and/or the PCs themselves. |
| **Overwhelmed** | Overwhelmed creatures are fighting against significant odds, in some combination of capability and/or simple numbers. |
| **Relentless** | Relentless creatures fight with little care for odds or the environment in which they do battle. |
| **Mindless** | Mindless creatures may still take different kinds of actions in combat round-to-round, but are not driven so much by tactics or intelligence. |

### FlexAI & FlexTable Listing

The Full Edition of FlexAI contains a separate FlexTable for each
distinct combination of Role and Stance.

With 35 Roles and 8 Stances, that makes for a grand total of 280
FlexTables, each one designed for a unique combination of a type of
creature behavior, and its current circumstances.

## Advanced AI Rules

In addition to the wide range of dynamic combat behavior offered by the
Full AI Rules, FlexAI offers Advanced AI rules.  These allow for even
more versatility in combat behavior, and reflect a more complex and
nuanced creature intelligence.

### Advantages & When to Use

Advanced AI is pretty much the same system as Full AI, with possible
additional boosts and penalties to the creature involved.  It's a useful
tool in providing a more unexpected and interesting combat experience
for your PCs.

### Limitations

Of the three FlexAI rules systems, Advanced AI is the only one that
departs tangibly from the RAW (Rules as Written) combat mechanics of the
roleplaying system you are using.

Since Advanced AI provides the possibility of additional bonuses and
penalties on combat actions, and does so outside the context of spells,
spell-like abilities, racial effects, and so on, there is little in the
rules mechanics.

### Surges & Lulls

Advanced AI takes the Full AI rules and extends them through the use of
Surges and Lulls.

This is intended to represent the wide variance of combat abilities and
behavior that every creature exhibits.  Rules purists will point out
that the roll of a die (typically a d20) to provide randomness already
models this range of behavior.

The FlexTables provided in FlexAI describe not only the Outcomes, but
also the possibility of Surges and Lulls for each Outcome.

### Combat Surges

A Surge is a boost to a creature's combat behavior.  If a Surge is
indicated in the FlexTable results rolled, it applies for the combat
actions of that creature alone, and for the current combat round only.

Surges rolled do not apply to any other creature, friend or foe, this
round.  Benefits last until the start of the next round of combat for
that creature.

This means that the benefit may still apply during the enemy's combat
turn.  For example, a Surge for a creature using Use/Defend Outcome
might boost its Armor Class; this benefit lasts throughout the enemy's
next round.

**Table 9: Combat Surges**

| Outcome | Minor Surge | Major Surge |
| --- | --- | --- |
| **Attack Main** | +1 / +2 / +3 / +4 Attack | +2 / +4 / +5 / +6 Attack |
| **Attack Secondary** | +1 / +2 / +3 / +4 Attack | +2 / +4 / +5 / +6 Attack |
| **Maneuver** | +1 Init; +5' Move (escalating to +4 Init; +5' Move) | +2 Init; +5' Move (escalating to +7 Init; +15' Move) |
| **Use / Defend** | +1 impact / +1 AC (escalating to +1 impact die / +4 AC) | +1 impact die / +3 AC (escalating to +2 impact dice / +6 AC) |
| **Ability** | +1 impact / +1 DC / +5' range (escalating to +1 impact die / +4 DC / +10' range) | +1 impact die / +3 DC / +10' range (escalating to +2 impact dice / +6 DC / +20' range) |
| **Flee** | +1 AC / +5' Move (escalating to +4 AC / +20' Move) | +2 AC / +10' Move (escalating to +7 AC / +25' Move) |

### Combat Lulls

Combat Lulls are a temporary handicap, penalty, or other negative impact
to a creature's combat abilities.  Lulls represent the reality that in
the shifting chaos of fighting, a creature might get distracted, trip,
stumble, miscalculate, or otherwise perform not as well as it might
typically, either through its own failure or the circumstances of the
battle.

If a Combar Lull is indicated in the FlexTable results rolled, it
applies for the combat actions of that creature alone, and for the
current combat round only.

**Table 10: Combat Lulls** — mirrors Table 9 with negative values.
