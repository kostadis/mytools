# Obelisk Module Structure — reference index

Compiled during the ch6–8 (`_scan_C.md`) pass. Reuse as a starting index for the next scan so you don't re-derive chapter boundaries and the named-exclusion list each time.

## Chapter map (obelisk.md, 6,078 lines)
Verified start lines; chapter ENDS are inferred from the next chapter's start.
- Ch1 A Dangerous Journey — ~line 562 onward
- Ch2 Trouble in Phandalin — ~line 716
- Ch3 The Spider's Web — ~line 1100
- Ch4 Wave Echo Cave — ~line 1500
- Ch5 Paths of Peril — ~line 2150
- Ch6 The Shattered Obelisk — **starts line 2919**, ends ~4079
- Ch7 Rifts in Reality — **starts ~4080**, ends ~4942
- Ch8 Beyond a Lightless Star — **starts ~4943**, ends 6078 (file end)

Each chapter is a top-level `#` heading. Confirm by reading the first lines of your requested range.

## Area-code legend (codes repeat across maps — always cite chapter)
- **Z** = Zorzula's Rest (ch5)
- **H** = Cragmaw Hideout (ch1) · **C** = Cragmaw Castle (ch1–3) · **R** = Redbrand hideout / Tresendar (ch2) · **W** = Wave Echo Cave (ch1–4)
- **T** = Talhundereth (ch6) · **P** = Crypt of the Talhund (ch6) · **G** = Gibbet Crossing (ch6)
- **J** = Underdark tunnels / grell caves (ch7) · **X** = Illithinoch (ch7) · **F** = Feeder Trenches rift (ch7) · **S** = Spawn Hollow rift (ch7) · **L** = Labyrinth of Eyes rift (ch7)
- **B** = Briny Maze (ch8) · **M** = Mire of Doubt (ch8) · **W** = Wailing Battlefield / Endless Void nodules (ch8 — NOTE collision with Wave Echo Cave's W) · **O** = Occluding Miasma · other Endless Void nodules (Crystal Dome, Empty Bridge, Toppled Statue, etc.)

⚠️ **`W` collides**: Wave Echo Cave (ch4) vs Wailing Battlefield (ch8, "W1: Prison Pyramid" ~line 5720). Disambiguate by chapter, never by letter alone.

## Monster-type → named-exclusion index (ch6–8)
For each unnamed/generic type found in ch6–8, the named individuals to EXCLUDE (per name_glossary.md) so the type stays "unnamed only":
- Grell (J-caves): exclude leader **Vundru** (grell psychic, J7)
- Grell (Feeder Trenches F2/F4): exclude host **Feedkeeper Naruv** (F4)
- Grimlocks (G18/G23/G24): exclude master **Qunbraxel** (mind flayer warlock)
- Slaadi (X7/S2): exclude **Chalaag** (gray slaad, S3)
- Slaad tadpoles (S2): none named
- Flumphs (B11): exclude **Wise Borblish**
- Mind flayers (Illithinoch minions): exclude **Shalghast/Ulthundul** (X2 guards), **Qunbraxel**, **Ahooshathan**, **Gulguush** (prophet), **Oshundo** (alhoon), and the three fanatics **Chishinix/Hashutu/Voalsh**; the Refraction of Ilvaash is the final boss (skip as a minion)
- Mind flayer prophets (unnamed): exclude **Gulguush** (X11); epilogue squads stay generic
- Mezzoloths (Wailing Battlefield): exclude commander **Nellik** (nycaloth) and adjutant **Frevvik**; exclude former boss **Ashripask** (arcanaloth)
- Umber hulks (W1): none named
- Aberrant zealots (generic residents): exclude **Duoro Engletor**, **Shalfi Lewin**, **Nouashu/Groushim**, **Ablinash**
- Flesh meld: exclude **Jitterjaws** (Shalfi's named pet)
- Cult of the Obelisk mutates: exclude **Ontharyx Henlifel** + **Chals/Harralie/Paulam** (T20), **Falfark** (T19), **Malinia** (T17)
- Drow (G25 thieves): none named (distinct from named drow Erdan/Thiala/Vellios at T14 and Nythalyn/Yanthdel at T15)
- Beholder/oculorb: exclude **Golcuus** (oculorb, L7) and **Mublinesh** (beholder, B14)
- Spectator: exclude **Jomlus** (B10)
- Githyanki: exclude **Varakkta/Kianka/Vazzi** (B7)
- Spirit nagas: exclude **Valsyx/Charnyz** (Mire of Doubt)
- Krakens: exclude **Ghaluzesh** (epilogue)
- Amethyst dragon / mage: exclude **Lowarnizel/Gossa** (B17)
- Medusa / galeb duhr: exclude **Honna** + **Fremine/Frowode/Cameren** (T2/T3)
- Xorn: exclude **Zoklork** (G14)
- Chain devil: exclude **Vakketar** (G6)
- Svirfneblin: exclude **Rivibiddel** (P9)
- Yochlol: exclude **Zuluthl** (G20)
- Nothic: exclude **Bashudu** (F4)
- Cloaker mutate (J8): none named (but it puppets named corpse **Thorgran Ironquill** — exclude Thorgran, keep the cloaker)
- Psychic gray oozes (Town Green): spawned by **Daisy** the cow (named animal, excluded; oozes generic)

## Counts that matter (ch6–8 pass)
- 36 distinct unnamed/generic monster groups captured in `_scan_C.md`.
- Key die-roll counts to preserve verbatim: Tunnel Encounters table (4188–4200) grells `1d4`, gibbering mouthers `1d6`, quaggoths `1d6`+thonot, intellect devourer `1`, hook horrors `1d4+1`, troglodytes `1d6`+barlgura, shriekers `2d4`. Endless Void intellect snares `1d6`/hour. Slaad tadpoles = 12 (literal). Specters up to 7.
