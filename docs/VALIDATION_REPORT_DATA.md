# Validation data tables

Generated from `outputs/validation/validation_results.json`. **No parameter was tuned to match a vehicle.** Unsourced engine values are tagged `assumed` in `validation/*.yaml`.

## 1. Real vehicles (payload and orbit as published)

| Vehicle | Published GLOM [t] | As-published split | Optimised split | Lean margins (diag.) | Published casing k (diag.) | Length pred./pub. [m] |
|---|---|---|---|---|---|---|
| NASA SLS Block 1 (2 x five-segment SRB + 4 x RS-25 + ICPS) | 2,610.0 | 2,343.8 (-10%) | 2,068.3 (-21%) | 2,012.3 (-23%) | n/a | 111.2 / 98.1 |
| JAXA/MHI H3-24L (4 x SRB-3 + 2 x LE-9 + LE-5B-3) | 575.0 | 552.9 (-4%) | 538.3 (-6%) | 500.8 (-13%) | n/a | 66.6 / 63.0 |
| Ariane 62 (2 x P120C + Vulcain 2.1 + Vinci) | 530.0 | 405.2 (-24%) | 404.9 (-24%) | not feasible | n/a | 52.7 / 63.0 |
| Ariane 64 (4 x P120C + Vulcain 2.1 + Vinci) | 860.0 | 779.7 (-9%) | 771.1 (-10%) | 754.4 (-12%) | n/a | 61.9 / 63.0 |
| Orbital/Northrop Minotaur I (4 solid stages) | 36.2 | 33.3 (-8%) | 31.3 (-13%) | 29.6 (-18%) | n/a | 23.6 / 19.2 |
| CASC/SAST Long March 12 (2 kerolox stages) | 433.0 | 364.0 (-16%) | 349.5 (-19%) | not feasible | n/a | 55.0 / 62.0 |
| Rocket Lab Electron (LOX/RP-1, composite) | 13.0 | 16.8 (+29%) | 16.4 (+26%) | 13.6 (+5%) | n/a | 20.8 / 18.0 |
| SpaceX Falcon 9 Block 5 (expendable, LOX/RP-1) | 549.1 | 636.3 (+16%) | 627.1 (+14%) | 544.3 (-1%) | n/a | 81.5 / 70.0 |
| Titan II GLV (N2O4/Aerozine-50) | 154.0 | 178.6 (+16%) | 178.3 (+16%) | 148.1 (-4%) | n/a | 39.4 / 33.2 |
| Saturn V (RP-1/LOX, LH2/LOX, LH2/LOX) to TLI | 2,894.0 | 2,825.7 (-2%) | 2,511.3 (-13%) | 2,169.2 (-25%) | n/a | 130.0 / 110.6 |
| LandSpace Zhuque-2 (LOX/CH4) | 219.0 | 150.1 (-31%) | 149.5 (-32%) | 126.7 (-42%) | n/a | 39.9 / 49.5 |
| Pegasus XL (3 solid stages, air-launched) | 23.1 | 20.1 (-13%) | 19.1 (-18%) | 18.2 (-21%) | 32.6 (+41%) | 18.9 / 17.6 |
| Vega (P80 + Zefiro 23 + Zefiro 9 + AVUM) | 137.0 | 188.4 (+38%) | 137.6 (+0%) | 124.1 (-9%) | 143.9 (+5%) | 58.8 / 30.0 |
| Epsilon (3 solid stages) | 95.4 | 76.5 (-20%) | 71.3 (-25%) | 67.8 (-29%) | n/a | 28.7 / 26.0 |
| Scout G-1 (4 solid stages) | 21.7 | 30.7 (+41%) | 19.2 (-11%) | 17.6 (-19%) | n/a | 25.5 / 22.9 |
| Vega C (3 solid stages + AVUM+) | 210.0 | 287.8 (+37%) | 219.6 (+5%) | 199.0 (-5%) | n/a | 64.6 / 34.8 |
| M-V (3 solid stages) | 139.0 | 144.5 (+4%) | 139.9 (+1%) | 125.5 (-10%) | n/a | 35.5 / 30.8 |
| Firefly Alpha (LOX/RP-1, composite) | 54.0 | 58.8 (+9%) | 57.3 (+6%) | 44.1 (-18%) | n/a | 33.3 / 29.0 |
| Delta II 7920 (9 x GEM-40, 6 ground-lit + 3 air-lit) | 231.9 | 297.4 (+28%) | 231.0 (-0%) | 210.2 (-9%) | n/a | 56.3 / 38.9 |
| Atlas V 551 (5 x AJ-60A + CCB + Centaur III) | 587.0 | 538.6 (-8%) | 475.5 (-19%) | not feasible | n/a | 78.4 / 58.3 |
| Ariane 5 ECA (2 x EAP + EPC + ESC-A) | 780.0 | 855.4 (+10%) | 802.8 (+3%) | 757.1 (-3%) | n/a | 80.6 / 52.0 |
| H-IIA 202 (2 x SRB-A + LE-7A core + LE-5B) | 285.0 | 302.2 (+6%) | 302.2 (+6%) | 284.4 (-0%) | n/a | 64.4 / 53.0 |
| Soyuz-2.1b (4 tapered strap-ons + Blok A + Blok I) | 312.0 | 361.0 (+16%) | 279.3 (-10%) | not feasible | n/a | 45.4 / 46.1 |
| Delta IV Heavy (3 x Common Booster Core + DCSS) | 733.0 | 735.8 (+0%) | 735.8 (+0%) | 715.1 (-2%) | n/a | 77.1 / 70.7 |

## 2. Delta-v of the *published* stage masses vs the requirement the tool computes

| Vehicle | Ideal dv from published masses [m/s] | Required (loss model) [m/s] | Margin |
|---|---|---|---|
| Orbital/Northrop Minotaur I (4 solid stages) | 8,424 | 8,743 | -3.6 % |
| Rocket Lab Electron (LOX/RP-1, composite) | 9,136 | 9,551 | -4.3 % |
| SpaceX Falcon 9 Block 5 (expendable, LOX/RP-1) | 9,221 | 9,097 | +1.4 % |
| Titan II GLV (N2O4/Aerozine-50) | 9,201 | 8,988 | +2.4 % |
| Saturn V (RP-1/LOX, LH2/LOX, LH2/LOX) to TLI | 12,987 | 12,359 | +5.1 % |
| Pegasus XL (3 solid stages, air-launched) | 7,976 | 8,461 | -5.7 % |
| Vega (P80 + Zefiro 23 + Zefiro 9 + AVUM) | 9,876 | 10,279 | -3.9 % |
| Scout G-1 (4 solid stages) | 9,087 | 9,704 | -6.4 % |
| Vega C (3 solid stages + AVUM+) | 10,237 | 10,321 | -0.8 % |
| M-V (3 solid stages) | 9,772 | 8,684 | +12.5 % |

## 3. Structural factors: predicted vs published

| Vehicle | Stage | Type | s predicted | s published | ratio |
|---|---|---|---|---|---|
| Orbital/Northrop Minotaur I | 1 | solid | 0.1408 | 0.0993 | 1.42 |
| Orbital/Northrop Minotaur I | 2 | solid | 0.1519 | 0.1131 | 1.34 |
| Orbital/Northrop Minotaur I | 3 | solid | 0.0789 | 0.0958 | 0.82 |
| Orbital/Northrop Minotaur I | 4 | solid | 0.0821 | 0.1406 | 0.58 |
| Rocket Lab Electron | 1 | liquid | 0.0819 | 0.0931 | 0.88 |
| Rocket Lab Electron | 2 | liquid | 0.0831 | 0.1087 | 0.76 |
| SpaceX Falcon 9 Block 5 | 1 | liquid | 0.0611 | 0.0608 | 1.01 |
| SpaceX Falcon 9 Block 5 | 2 | liquid | 0.0508 | 0.0404 | 1.26 |
| Titan II GLV | 1 | liquid | 0.0656 | 0.0538 | 1.22 |
| Titan II GLV | 2 | liquid | 0.0827 | 0.0767 | 1.08 |
| Saturn V | 1 | liquid | 0.0733 | 0.0585 | 1.25 |
| Saturn V | 2 | liquid | 0.0811 | 0.0665 | 1.22 |
| Saturn V | 3 | liquid | 0.0855 | 0.0988 | 0.87 |
| Pegasus XL | 1 | solid | 0.0777 | 0.0836 | 0.93 |
| Pegasus XL | 2 | solid | 0.0793 | 0.0958 | 0.83 |
| Pegasus XL | 3 | solid | 0.0825 | 0.1406 | 0.59 |
| Vega | 1 | solid | 0.0766 | 0.0766 | 1.00 |
| Vega | 2 | solid | 0.0771 | 0.0751 | 1.03 |
| Vega | 3 | solid | 0.0775 | 0.0802 | 0.97 |
| Vega | 4 | liquid | 0.1342 | 0.1924 | 0.70 |
| Scout G-1 | 1 | solid | 0.1413 | 0.1314 | 1.08 |
| Scout G-1 | 2 | solid | 0.1763 | 0.2202 | 0.80 |
| Scout G-1 | 3 | solid | 0.0839 | 0.2050 | 0.41 |
| Scout G-1 | 4 | solid | 0.0892 | 0.1602 | 0.56 |
| Vega C | 1 | solid | 0.0765 | 0.0733 | 1.04 |
| Vega C | 2 | solid | 0.0771 | 0.0818 | 0.94 |
| Vega C | 3 | solid | 0.0775 | 0.0808 | 0.96 |
| Vega C | 4 | liquid | 0.1300 | 0.4843 | 0.27 |
| M-V | 1 | solid | 0.1201 | 0.1325 | 0.91 |
| M-V | 2 | solid | 0.1265 | 0.0833 | 1.52 |
| M-V | 3 | solid | 0.1514 | 0.0833 | 1.82 |
| Delta II 7920 | 1 | liquid | 0.0727 | 0.0558 | 1.30 |
| Delta II 7920 | 2 | liquid | 0.0601 | 0.1366 | 0.44 |
| Atlas V 551 | 1 | liquid | 0.0925 | 0.0690 | 1.34 |
| Atlas V 551 | 2 | liquid | 0.0879 | 0.0972 | 0.90 |
| Ariane 5 ECA | 1 | liquid | 0.0895 | 0.0796 | 1.12 |
| Ariane 5 ECA | 2 | liquid | 0.0947 | 0.2335 | 0.41 |
| H-IIA 202 | 1 | liquid | 0.0937 | 0.0982 | 0.95 |
| H-IIA 202 | 2 | liquid | 0.1452 | 0.1531 | 0.95 |
| Soyuz-2.1b | 1 | liquid | 0.1041 | 0.0677 | 1.54 |
| Soyuz-2.1b | 2 | liquid | 0.0714 | 0.0848 | 0.84 |
| Delta IV Heavy | 1 | liquid | 0.0960 | 0.1178 | 0.81 |
| Delta IV Heavy | 2 | liquid | 0.1168 | 0.1136 | 1.03 |

## 4. Propellant types on one mission (10 t to 400 km LEO, 28.5 deg, GLOM-minimising dv split)

| Combination | GLOM [t] | Dry [t] | Payload fraction | Length [m] | dv [m/s] |
|---|---|---|---|---|---|
| LOX/RP-1 + LOX/RP-1 | 353.3 | 15.2 | 2.83 % | 51.8 | 9,429 |
| LOX/LCH4 + LOX/LCH4 | 299.9 | 14.5 | 3.33 % | 53.4 | 9,454 |
| LOX/LH2 + LOX/LH2 | 180.6 | 14.0 | 5.54 % | 53.8 | 9,546 |
| LOX/RP-1 + LOX/LH2 | 211.4 | 13.7 | 4.73 % | 53.1 | 9,521 |
| N2O4/A-50 + N2O4/A-50 | 478.8 | 18.3 | 2.09 % | 55.7 | 9,388 |