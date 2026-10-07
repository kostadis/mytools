# Phandalin workspace specifics (verified session: chapters 1–16)

## Paths
- Registry: `/home/kostadis/src/campaigns/Phandalin/docs/entity_registry.yaml` (~93KB, 577 entities)
- Chapters: `/home/kostadis/src/campaigns/Phandalin/docs/chapters/chapter_NN_<slug>.md` — 47 chapters total; 1–16 covered so far.
- Chapter frontmatter: `chapter:` and `title:` YAML. Body sections: `## NN.MM <POV-name> <date>` — POV-structured, so most events appear in one character's narration.

## Match counts per chapter (after alias false-positive audit)
ch1=22, ch2=37, ch3=15, ch4=20, ch5=17, ch6=25, ch7=25, ch8=10, ch9=15,
ch10=36, ch11=10, ch12=18, ch13=24, ch14=12, ch15=17, ch16=32

## Confirmed false-positive aliases (exclude)
| Entity | Bad alias | Why |
|---|---|---|
| Anchorites of Talos | `cleric` | generic word |
| Falcon's Hunting Lodge | `courtyard`, `the lodge`, `hunting lodge` | generic words |
| Jenna | `woman`, `the woman in green` | generic; only "Jenna" literal is safe |
| Kazneporium Ketternopappux | `KP` | matches "sage KP" initials — low confidence |

## Legitimate tricky entries
- `Tortle` is its own registry entity (species), separate from Soma — keep both when matching.
- Party members Vukradin / Brewbarry / Valphine / Soma appear in nearly every chapter (ch2 onward).
- Recurring NPCs: Harbin Wester, Adabra Gwynn, Ser Kaelen Thorn, Linene Graywind, Corbin, Sister Kaella, Jenna, Borg the Hammer, Lyra.

## Chapter 6 verified entity set (ch06 extraction, 22 files)
Adabra Gwynn, Harbin Wester, Toblen Stonehill, Vukradin, Soma, Valphine, Brewbarry, Ser Kaelen, Daran Edermath, Corbin, Milo Goodbarrel, Order of the Gauntlet (faction), Lathander, Lolth (deities), War of the Dragons (event), Phandalin, Stonehill Inn, Townmaster's Hall, Barthen's Provisions, Tower of Storms, Neverwinter Wood (locations). Output: `~/phandalin-entity-scan/parts/ch06/`, bullets cite `(NN.MM)` POV sections. Registry note: "Ser Kaelen Thorn" in prose vs `Ser Kaelen` + alias `Ser Kaelen Thorne` in registry — alias covers it.

## Chapter arc quick-reference (for summary bullets)
1. World history excerpt: Neverember sends adventurers to Phandalin; Vukradin recruited.
2. Arrival: party forms (Vukradin/Brewbarry/Valphine/Soma); Dwarven Excavation quest; Dazlyn & Norbus; sending stones; orc ambush; ogre fight.
3–4. Gnomengarde: mimic hunt for Kings Korboz/Gnerkli; hat of wizardry; first mention of the Carver (bandit boss); bandit Corbin spared/joins.
5. Umbrage Hill: manticore killed; Adabra Gwynn refuses to leave; naturalist/interventionist schism introduced; Emerald Enclave revealed.
6. Vukradin joins Order of the Gauntlet via Ser Kaelen; Daran Edermath ("Silverleaf"); Tower of Storms rumor; Valphine joins the music act.
7. Elara/Jarek rescued (disciplined orcs, psionic hints); Wayside Inn (Martisha, Backes, Cooragh); disciplined orc ambush en route to Tower of Storms; Adabra tells Soma of Whispering Wood blight.
8–9. Tower of Storms: harpies; Moesko the Orc Anchorite killed; beating-heart beacon destroyed; Talos talisman + inverted-eye/tentacle talisman found; Miral's conch returned; shipwreck loot (+1 halberd, cloak, wand of secrets, spellbook, pearls).
10. Back in Phandalin: Linene's Coster degraded post-War of the Giants; anonymous letter re House Margaster funding the Gauntlet (actually sent by Jenna); Ser Kaelen tasks the party with finding the Carver.
11–12. Whispering Wood: shimmering stag; planar brambles; corrupted Treant; pool visions; Lyra's failed sealing ritual — rift grows; puppet-like creature gathers components.
13. Confronting Adabra; Enclave agents Thomas & Marian on Lyra's failure; pelts sold to Linene.
14–15. Butterskull Ranch quest: Skippy captured reveals Carver's trap, Sister Kaella spymaster reveal; Big Al Kalazorn freed, cow Petunia recovered; Borg the Hammer burns the ranch and splits off with ogres.
16. Phandalin politics: privy council formed after dragon attack (Vukradin's phantasmal force drives Cryovain off); Locutus killed by Sister Kaella; her deal offer to Valphine; Jenna (Lord's Alliance) agency pitch rejected by Vukradin.

## Companion reference
- `phandalin-chapters-17-32.md` — arc quick-reference, new entity index, and continuity notes for chapters 17–32 (the Falcon/Sridar/Teega/Aletra/Carver arc through Dragonbarrow).
