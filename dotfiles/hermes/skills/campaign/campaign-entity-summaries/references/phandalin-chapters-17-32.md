# Phandalin campaign: chapters 17–32 (session-specific detail)

## Paths
- Chapters: `/home/kostadis/src/campaigns/Phandalin/docs/chapters/chapter_NN_<slug>.md`
- Registry: `/home/kostadis/src/campaigns/Phandalin/docs/entity_registry.yaml`
- Output dir for this session: `/home/kostadis/phandalin-entity-scan/parts/b/`

## Chapter arc quick-reference (17–32)
- **17 Blood Money, Clean Gold, Fine Wine**: Temple of Lathander founding in Tresendar Manor; Sister Kaella's Carver deal offer rejected by Vukradin; supply run to Logger's Camp begins.
- **18 Falcon's Hoard and Hidden Truths**: Vukradin's drawer investigation reveals Falcon is not a dragon slayer; brass ring linked to Iymrith's hoard; Sridar buys Talisman of Moesko.
- **19 Logger's Camp**: Orc ambush in Neverwinter Wood; party captures "Shrimpy" (orc scout); arrive at empty Logger's Camp.
- **20 The Spiral's Grasp**: Kraken Society Cult Fanatic mind-controls Emerald Enclave patrol; party rescues them; Cult Fanatic executed; orcs demand his head.
- **21 Boars Are More Than Boars**: At Falcon's Lodge; Teega's psionic backstory revealed; Mountain's Toe mine poisoning; Woodland Manse investigation begins; Anchorite boar revealed.
- **22 Retreat to Redemption (and Cheese)**: Retreat from Manse; Phandalin council; Adabra vs. party over intervention; mine negotiations with wererats + Stonetallow clan; Don-Jon death mystery.
- **23 Ale, the Ex, Axeholm**: Mine deal struck; Dragonbarrow quest begins; Axeholm exploration starts.
- **24 Breaching Axeholm**: Spatial anomaly dwarves; out-of-phase combat; paralysis "packaging" effect.
- **25 Out-of-Phase Dwarves to Mechanical Mysteries**: Axeholm exploration; Chief Accountant revealed; Aletra Sotorra confrontation; machine room discovery.
- **26 Sisters Against the Machine**: Chief Accountant's history; Aletra's poison-smuggling scheme; Rift Weavers battle.
- **27 Machine Screams, A Family Affair**: Aletra's true plan; poison extraction; portal escape; Valphine's blinding curse.
- **28 Drones, Dread, Dangerous Deliveries**: Aletra's quarters looted; audit drones; dread helm; mine orc/ogre ambush.
- **29 Cheesy Compromise in Mine**: Mine battle; Zeleen's deception exposed; Don-Jon's true killer found; stonetallow/dwarf contract negotiated; carrion crawler relocated.
- **30 Brewbarry's Bloody Axe and Beer Blight**: Mine agreement finalized; Dragonbarrow entry; pit traps; will-o'-wisps; Falcon meets party on Triboar Trail.
- **31 Grave New Friend, Glimmering Blade**: Boney skeletal horse joins; Dragon Slayer Sword found; will-o'-wisp combat; pressure plate tunnel collapse.
- **32 Silencing the Siren's Warning**: Invisible stalker ambush; Dragon Slayer Sword claimed; Lady Alagondar's ghost; Sister Kaella's warning; Jax's final ambush.

## New entities introduced (chapters 17–32)
- **Aletra Sotorra** — Valphine's sister; Sotorra family poison operations; planar machine operator in Axeholm.
- **Chief Accountant** — glitching undead dwarf in Axeholm; keeper of the machine override code.
- **Rift Weavers** — spider-like planar constructs guarding Aletra's machine in Axeholm.
- **Audit drones** — steampunk constructs in Axeholm's secret room behind the fireplace.
- **Dread Helm** — possessed helmet found in Axeholm (glows red eyes when worn).
- **Gauntlets of Ogre Power** — found with the dread helm in Axeholm's secret room.
- **Boney** — skeletal horse reanimated in Dragonbarrow; bonds with Valphine.
- **Xanth** — centaur who warns about Dragonbarrow; wounded by stalker ambush in ch 32.
- **Invisible Stalker** — guards the Dragon Slayer Sword in Dragonbarrow's northern chamber.
- **Jax** — last of the Carver's agents; ambushed the party after Sister Kaella's capture.
- **Rot-Tusk Ogre** — part of Jax's final ambush at Dragonbarrow.
- **Necklace of Fireballs (7 beads)** — found in Dragonbarrow sarcophagus.
- **Flute of Illusions** — found in Dragonbarrow northwest chamber.

## Recurring entity continuity (ch 17–32)
- **Vukradin / Soma / Valphine / Brewbarry** — appear in every chapter 17–32.
- **Harbin Wester** — townmaster throughout; collects fees, pays rewards, makes deals.
- **Falcon the Hunter** — appears ch 17, 18, 20, 28(referenced), 30; lodge owner, dragon hoard claimant, later distraught about overrun lodge.
- **Brewbarry** — narrative POV character in ch 19 (multiple sections); full name revealed ch 30: "Brewbarry Root Smasher Ogalakadu".
- **Sister Kaella** — ch 17 offer, ch 22 council, ch 32 final warning + capture.
- **The Carver** — defeated off-screen (pre-ch 17); referenced ch 17 (reward), ch 19 (displaced orcs), ch 22 (Don-Jon's employers), ch 30/32 (now a hollow shell marching on Icespire Hold).
- **Dragon Slayer Sword** — quest target ch 23; hidden in Dragonbarrow; claimed ch 32.
- **Cryovain** — referenced ch 32 as the white dragon the Carver seeks to bind.
- **Don-Jon Raskin** — escorted to the mine ch 22; death investigated ch 29; killed by Horia's dwarves.

## Verified false-positive patterns to watch
- "Falcon" as a surname vs. "Falcon the Hunter" / "Falcon's Hunting Lodge" — all are the same entity; the lodge is the location, the Hunter is the NPC.
- "Orcs" and "Ogres" appear together frequently at the mine — keep as separate entities but track shared encounters.
- "Audit drones" (plural construct type) vs "Audit drone" (singular instance) — merged into one file.
- "Sarcophagi" appears in both ch 30 and ch 31 (same Dragonbarrow location) — track per chapter.
- "Brewbarry" vs "Brewbary" — spelling varies in ch 31 dialogue; match both.