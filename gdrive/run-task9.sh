#!/bin/bash
# Task 9: Move root-level RPG PDFs to RPG/PDFs
# Run from ~/src/mytools/gdrive with (src) venv active
#
# DRY RUN by default. Add --execute to the move.py calls when ready.
# You can comment out lines for files you don't want to move.

echo "=== Step 1: Move RPG PDFs to RPG/PDFs ==="
python3 move.py --execute --to RPG/PDFs --create-folder \
  10Dr0ATUgwunM8Ge-onopIZED-d3tXHi7 \
  1xvGe5fSemkx_l0A0QzTxnf_ExBK2ZIac \
  10ARSo2P4NEEldu3hxu6UJMNFGRHZ2EJA \
  1lAqO8UlogDcQNunwR2B99SXelUdiSx00 \
  1qXCLL0cpVF_iIYryDnuOkMOFT7w56kOg \
  18QdjaBPA4xycU9u-OYuuPbvpOzTsndyf \
  1vsOF2AkadphcvKGFqC1ZDlJuA6Je32Tr \
  1_kEzunREgmW5zffbLN2Vz65tvjrvLOZj \
  15KtraNXxkFsE8jIpaY62QgxPl7A6Ns7b \
  1Dqt5ejyxM6r3hLnQf5kTHwbvM6lMa3yH \
  1ty6gxHjFBY-YjfUzYoaXP0OEwOQ8GWXY \
  0B67WGpsPYVobMjVQZnM0LVZQb1E \
  1fCIuGkcGq5VQJPaFA51SMGD4kgBIszzV \
  16T30dB9XjypwGowb4oFbh4tkAcwjChM_ \
  1-gZO1UKDyctL6i5HOo613R6OVYgqzH7J \
  0ByjttQlCjDQ_TXQtLUVLVXNRNlk \
  1peF3PywlQ7ka_ti5hTr7wZw3YKXN8ctT \
  1PrVcUmzOytdyguxZ1pAGBd5JXO_omhPu \
  1tcwfyfQSKYD_T3fQU3KQT5GI1FMgDJS7 \
  12P6LA8BO1NdOuol5PX-c44-c3j5sh8C4 \
  1pcc91b7QiWCOKxIsgot6Ah5Ax3koAVeY \
  1TMkhghTeS_QzMT0V4VPH2mM8Uye87b4K \
  1EJqf4Sir6Og3zFPFIrpuMooXpqv3eIoS \
  0B-g9vLTX0eHKWDZHZ05QWkVNZVU \
  1-YxHAlgA7yLe_JHxUyG1fmDZ9a_AI5Qc \
  1SxypzsD_QXr2LCZNTu5N9bHZRZD7TQYk \
  185m_pCsjMxRiTNfbzoOMkIfK_Cgo8jad \
  1YA3yHiAKb1MGks4ZmsW6gpdQspeF9Vfm \
  1y_aPsA7S8si3iziTN04O5b5E1kp0fsbL \
  1azHZB7tvSvANqf7LilEFTwWjeA1px6h4 \
  1Xgz9tqLckqRjFqt6QOcvvuvaQPc3yTMv \
  1vSi4YwYw3C5OzYQ9ZzROgTuCV1fDphRL \
  1WeEak-__ARV4l5LMrIm4hqDqxRGoOfmV \
  1RkPvnbDDFi8HQ22jpExe_lylJYO6cHk5 \
  1ElKmKe5nd9xEepzEmpwbBid_j290ASpd \
  1QGrYnKGBV76DfoAXFaA4Kwq51_hOssRs \
  1XGFF71wim2flrnuxiy4thewxJKlpIFPP \
  140nmCc1OZxG3JgcRyIYNMUqOsmbO4CvZ \
  1zuJqSO0aN56JP_tGmU-sgT9_Dtnd1NiC \
  10fILL2JPu9r6dO97-bAb7t9SkbhZRTWz \
  1w_Zh_eyTWvJoQ3GUBn_nVeYny4HP-NK0 \
  1XmpGCHKwU5m7VYFk1G4y4LNTNdrvSK7J \
  1Mj3tPITlm6XduSCc7oyaxEYu68sSQyfp \
  0B2iwLIBEqXRcRXZwVzMwdzJfc1FyWnlkNHd4WmxnQ09qWlZJ \
  0B2iwLIBEqXRcUU0xcVRSaXJYVHRRalNWdGE1cUZoS1BDT3lZ \
  1HVU9sNTYgTQznQ5CXsWoObfMh4FPaxD5 \
  0B2iwLIBEqXRcUVhSVUtWbDNENFVVQXVUS2VfWVg0S1RwT05n \
  0B2iwLIBEqXRcdkpOd2x0SHhmTDg1aHFYMVBqUVUwQ0ZBLThz \
  0B5NsJ80BORg_bEpRQ3lLd0NBVGc \
  0B2iwLIBEqXRcXzZ0STV4SEQyS083OHRMallna0VUYzVyZFhn \
  1KOwgl_wdE3atTzfXkl-JLiSnZ394bcs8 \
  0Bw1kyeBlBRE9U2I5LU5naUltcEE \
  0Bw1kyeBlBRE9Q3gtMHNNc0R3NFk \
  0B2iwLIBEqXRcUE1OT1BySnFKZUk0Q3JNWlROdXNRWFZkVk9n \
  0B2iwLIBEqXRcTGJGVmxMajJLbFV3VTJ4cG4wVDVOcjVuQmow \
  0B2iwLIBEqXRcYWVHbE52ejlSUXcwNzBCSGp3RnhIVG9tbTdB \
  1ZJPvs9KxWc9HYnTwHMF1vbhmkpsgD9Li \
  1VkNsTG6ApxKJf4QgboacANHyf_6YRv6C \
  1gFPGAyW-kSAQUczwp148nPB8Umcq6HsM \
  16676a6ibhAJRNNeKghEsx7NU8Rh8onfJ \
  198aEURcSnDPsTmYhiJnL284rESq6WLUC \
  1j4AyruuMEzZ5ItNAnajtpTub4iMGCZKV \
  0B2ZFIQcDqDVeMDA0S1Zmd1ZDU1k \
  0B2iwLIBEqXRcOXJUNE11TzJHNzhTTWl1bFJlUDVzS3dSallV \
  1vC1-5qn6T9un_B5Lqn5iB-HJpyJ0t1Hw \
  1DFNzMRbIGiwHAn5G_8yabfIURL0G1o5G \
  1xQlHc5LH0WFLXaAZ3a1AZGGZg0uhgqR7 \
  1AEwCP4gXRYqcoooCYqLOoqYzSz-W41Ij \
  1nraBURJu6PTTBD_Ty-0krBsBdCJKnCq8 \
  1FvQP4ZWVZ9bXFYPZahEs_xLG1vDfkAK-VkEm5njrWCn8TfRAv4AYcBbEh4JCk1jyJAHiLygytC6zgnHO \
  0B2iwLIBEqXRcejdmVTdnVmFkTFlvSkhzOHJpQ1EtaUlSTFk4 \
  0B2iwLIBEqXRcUmljeEx3aUZxUFdrbHl1dXdvdmt5a2dObXBF \
  1kyejKMsT5Sym0QejdPxs0RhkEToZMhpet6JakKW1aiyzCmIBZAw77SNmWuMuizjCSXhddHexCLnh5Q43 \
  0B2iwLIBEqXRcd3J4RFVCTUZWb0draklqbnBJbkJmUlR0Y1dB \
  12PhXiVXtEgfgGp4kpx6RJ29EE81UsIk

echo ""
echo "=== Step 2: Trash 'Copy of' dupes ==="
python3 trash.py --execute \
  1IB2WZfOpHwYYCqwgrC1XqWvBsqIcrmqR \
  1mKK_L8BSjX1DgCgKbIydv2K4IldeQous \
  1--xfNfMqhbgoMbj43WU4yRE6xk_FILBm \
  1xl466GVIW9LLwpviYXnLz6R4HD-Rqscm \
  1xQU2v_7SmAthdGvMzdsHMgqCCtOzP9ou \
  1AsXCFzwsO3BJf4h8pfpcfj4Z-GtCfo94

# FILE REFERENCE (name → ID for the RPG PDFs above):
#   279 MB  The Complete Roslof Keep Campaign.pdf          10Dr0ATUgwunM8Ge-onopIZED-d3tXHi7
#   231 MB  Before-the-Stroke-of-Midnight-hires.pdf        1xvGe5fSemkx_l0A0QzTxnf_ExBK2ZIac
#   141 MB  The Complete White Ship Campaign.pdf            10ARSo2P4NEEldu3hxu6UJMNFGRHZ2EJA
#   135 MB  The Complete Black Label.pdf                    1lAqO8UlogDcQNunwR2B99SXelUdiSx00
#   119 MB  FAST Core.pdf                                  1qXCLL0cpVF_iIYryDnuOkMOFT7w56kOg
#   116 MB  The Complete Curse of Roslof Keep.pdf           18QdjaBPA4xycU9u-OYuuPbvpOzTsndyf
#   112 MB  BOMM Kickstarter Preview Release_10.27.pdf     1vsOF2AkadphcvKGFqC1ZDlJuA6Je32Tr
#   107 MB  SpicyEncounters.pdf                            1_kEzunREgmW5zffbLN2Vz65tvjrvLOZj
#   105 MB  Gimble's Grimoire of Gnomish Knowledge.pdf     15KtraNXxkFsE8jIpaY62QgxPl7A6Ns7b
#    95 MB  The Storyteller's Arcana.pdf                    1Dqt5ejyxM6r3hLnQf5kTHwbvM6lMa3yH
#    91 MB  TheLostDruid_V2_1.pdf                          1ty6gxHjFBY-YjfUzYoaXP0OEwOQ8GWXY
#    86 MB  The Cities of Sorcery.pdf                      0B67WGpsPYVobMjVQZnM0LVZQb1E
#    86 MB  The Complete Cities of Sorcery Campaign.pdf     1fCIuGkcGq5VQJPaFA51SMGD4kgBIszzV
#    79 MB  Odyssey of The Dragonlords.pdf                 16T30dB9XjypwGowb4oFbh4tkAcwjChM_
#    76 MB  Mission Deck DD Undead Print and Play.pdf      1-gZO1UKDyctL6i5HOo613R6OVYgqzH7J
#    73 MB  Expedition 1.pdf                               0ByjttQlCjDQ_TXQtLUVLVXNRNlk
#    65 MB  Chapter 4 The Main Keep.pdf                    1peF3PywlQ7ka_ti5hTr7wZw3YKXN8ctT
#    65 MB  The-Mystery-of-the-Cursed-Statuette-HiRes.pdf  1PrVcUmzOytdyguxZ1pAGBd5JXO_omhPu
#    61 MB  The Artifacts of Adventure.pdf                 1tcwfyfQSKYD_T3fQU3KQT5GI1FMgDJS7
#    52 MB  Chapter 6 The Halls of Glory.pdf               12P6LA8BO1NdOuol5PX-c44-c3j5sh8C4
#    45 MB  Hommlet - Local Side Quests v.3.pdf            1pcc91b7QiWCOKxIsgot6Ah5Ax3koAVeY
#    37 MB  ROS 1 Final FAST.pdf                           1TMkhghTeS_QzMT0V4VPH2mM8Uye87b4K
#    36 MB  Nightmare Unleash_Quickstarter.pdf             1EJqf4Sir6Og3zFPFIrpuMooXpqv3eIoS
#    33 MB  MonsterModule.pdf                              0B-g9vLTX0eHKWDZHZ05QWkVNZVU
#    33 MB  The-Mystery-of-the-Cursed-Statuette-Std.pdf    1-YxHAlgA7yLe_JHxUyG1fmDZ9a_AI5Qc
#    31 MB  Backers Playtest March 2023.pdf                1SxypzsD_QXr2LCZNTu5N9bHZRZD7TQYk
#    30 MB  ROS 3.pdf                                      185m_pCsjMxRiTNfbzoOMkIfK_Cgo8jad
#    29 MB  Before-the-Stroke-of-Midnight-standard.pdf     1YA3yHiAKb1MGks4ZmsW6gpdQspeF9Vfm
#    29 MB  FAST Compendium V1 Final.pdf                   1y_aPsA7S8si3iziTN04O5b5E1kp0fsbL
#    25 MB  Bastions.pdf                                   1azHZB7tvSvANqf7LilEFTwWjeA1px6h4
#    23 MB  ROS 2 Final FAST.pdf                           1Xgz9tqLckqRjFqt6QOcvvuvaQPc3yTMv
#    21 MB  Folio #26 The Rat Dungeon.pdf                  1vSi4YwYw3C5OzYQ9ZzROgTuCV1fDphRL
#    19 MB  Folio #30 The Great Maze.pdf                   1WeEak-__ARV4l5LMrIm4hqDqxRGoOfmV
#    18 MB  Folio #25 The Labyrinth of Chaos.pdf           1RkPvnbDDFi8HQ22jpExe_lylJYO6cHk5
#    17 MB  Desert Denizens Greyhawk.pdf                   1ElKmKe5nd9xEepzEmpwbBid_j290ASpd
#    14 MB  Folio DQ #4 Stellar Mine.pdf                   1QGrYnKGBV76DfoAXFaA4Kwq51_hOssRs
#    13 MB  Folio DQ #5 Dungeons & Descendants.pdf         1XGFF71wim2flrnuxiy4thewxJKlpIFPP
#    12 MB  Rogues Guide to the Kasbah.pdf                 140nmCc1OZxG3JgcRyIYNMUqOsmbO4CvZ
#    12 MB  Shalvars Gambit Deck Rulebook.pdf              1zuJqSO0aN56JP_tGmU-sgT9_Dtnd1NiC
#     7 MB  CompendiumDarkArts.pdf                         10fILL2JPu9r6dO97-bAb7t9SkbhZRTWz
#     7 MB  goblin_punch_lair_of_the_lamb_final.pdf        1w_Zh_eyTWvJoQ3GUBn_nVeYny4HP-NK0
#     6 MB  flotsam fair printouts.pdf                     1XmpGCHKwU5m7VYFk1G4y4LNTNdrvSK7J
#     6 MB  Elder Evils 5e.pdf                             1Mj3tPITlm6XduSCc7oyaxEYu68sSQyfp
#     4 MB  Folio CRK B3 A Secret Respite.pdf             0B2iwLIBEqXRcRXZwVzMwdzJfc1FyWnlkNHd4WmxnQ09qWlZJ
#     4 MB  Folio CRK B2 Ten Steps Down.pdf               0B2iwLIBEqXRcUU0xcVRSaXJYVHRRalNWdGE1cUZoS1BDT3lZ
#     4 MB  Personality Traits of the Flanaess.pdf         1HVU9sNTYgTQznQ5CXsWoObfMh4FPaxD5
#     4 MB  Folio ROS S1.6 Hard Times.pdf                 0B2iwLIBEqXRcUVhSVUtWbDNENFVVQXVUS2VfWVg0S1RwT05n
#     4 MB  Folio ROS S1.5 Road to West.pdf               0B2iwLIBEqXRcdkpOd2x0SHhmTDg1aHFYMVBqUVUwQ0ZBLThz
#     3 MB  D&D 5e - DMs Cheat Sheet.pdf                  0B5NsJ80BORg_bEpRQ3lLd0NBVGc
#     3 MB  304 Bloods Ridge FULL REPORT.pdf               0B2iwLIBEqXRcXzZ0STV4SEQyS083OHRMallna0VUYzVyZFhn
#     3 MB  Echoes-Nexusar.pdf                             1KOwgl_wdE3atTzfXkl-JLiSnZ394bcs8
#     3 MB  Keep.pdf                                       0Bw1kyeBlBRE9U2I5LU5naUltcEE
#     3 MB  Keep No Labels.pdf                             0Bw1kyeBlBRE9Q3gtMHNNc0R3NFk
#     3 MB  Folio ROS S1.7 House of Eld.pdf               0B2iwLIBEqXRcUE1OT1BySnFKZUk0Q3JNWlROdXNRWFZkVk9n
#     2 MB  Folio CRK B1 Behind Amber Door.pdf            0B2iwLIBEqXRcTGJGVmxMajJLbFV3VTJ4cG4wVDVOcjVuQmow
#     2 MB  Folio #20.5 The Kasbah Assassins.pdf          0B2iwLIBEqXRcYWVHbE52ejlSUXcwNzBCSGp3RnhIVG9tbTdB
#     2 MB  T0 The Journey to Hommlet.pdf                  1ZJPvs9KxWc9HYnTwHMF1vbhmkpsgD9Li
#     1 MB  World of Greyhawk Campaign Resources.pdf       1VkNsTG6ApxKJf4QgboacANHyf_6YRv6C
#     1 MB  a0d3733e-... (unknown).pdf                     1gFPGAyW-kSAQUczwp148nPB8Umcq6HsM
#     1 MB  T5 Beneath Temple of Elemental Evil.pdf        16676a6ibhAJRNNeKghEsx7NU8Rh8onfJ
#     1 MB  2023-03-18-basiliqueen.pdf                     198aEURcSnDPsTmYhiJnL284rESq6WLUC
#     1 MB  D4 City of Spiders.pdf                         1j4AyruuMEzZ5ItNAnajtpTub4iMGCZKV
#     1 MB  toee.pdf                                       0B2ZFIQcDqDVeMDA0S1Zmd1ZDU1k
#     1 MB  304 Bloods Ridge SUMMARY REPORT.pdf            0B2iwLIBEqXRcOXJUNE11TzJHNzhTTWl1bFJlUDVzS3dSallV
#     1 MB  May-2024-1-Eghbariah.pdf                       1vC1-5qn6T9un_B5Lqn5iB-HJpyJ0t1Hw
#     0 MB  Intuition Says - Instead Try.pdf               1DFNzMRbIGiwHAn5G_8yabfIURL0G1o5G
#     0 MB  Players Guide Playtest 1.0.pdf                 1xQlHc5LH0WFLXaAZ3a1AZGGZg0uhgqR7
#     0 MB  YL-KR Conract Eng.pdf                          1AEwCP4gXRYqcoooCYqLOoqYzSz-W41Ij
#     0 MB  Greyhawk's World - Baklunish.pdf               1nraBURJu6PTTBD_Ty-0krBsBdCJKnCq8
#     0 MB  (mail attachment url).pdf                      1FvQP4ZWVZ9bXFYPZahEs_xLG1vDfkAK-VkEm5njrWCn8TfRAv4AYcBbEh4JCk1jyJAHiLygytC6zgnHO
#     0 MB  2896027.pdf                                    0B2iwLIBEqXRcejdmVTdnVmFkTFlvSkhzOHJpQ1EtaUlSTFk4
#     0 MB  GSD Kostadis_Backyard Update Proposal.pdf      0B2iwLIBEqXRcUmljeEx3aUZxUFdrbHl1dXdvdmt5a2dObXBF
#     0 MB  athensclassicmarathon.gr.pdf                   1kyejKMsT5Sym0QejdPxs0RhkEToZMhpet6JakKW1aiyzCmIBZAw77SNmWuMuizjCSXhddHexCLnh5Q43
#     0 MB  T5151420-Confirm-20200109.pdf                  0B2iwLIBEqXRcd3J4RFVCTUZWb0draklqbnBJbkJmUlR0Y1dB
#     0 MB  The Cities of Sorcery.pdf (stub)               12PhXiVXtEgfgGp4kpx6RJ29EE81UsIk
#
# DUPES being trashed:
#    73 MB  Copy of Expedition 1.pdf                       1IB2WZfOpHwYYCqwgrC1XqWvBsqIcrmqR
#    17 MB  Copy of Desert Denizens Greyhawk.pdf           1mKK_L8BSjX1DgCgKbIydv2K4IldeQous
#    16 MB  Copy of T0 The Journey to Hommlet.pdf          1--xfNfMqhbgoMbj43WU4yRE6xk_FILBm
#     3 MB  Copy of Echoes-Nexusar.pdf                     1xl466GVIW9LLwpviYXnLz6R4HD-Rqscm
#     1 MB  Copy of Exoshuffle-SkyRetreat.pdf              1xQU2v_7SmAthdGvMzdsHMgqCCtOzP9ou
#     1 MB  Copy of May-2024-1-Eghbariah.pdf               1AsXCFzwsO3BJf4h8pfpcfj4Z-GtCfo94
