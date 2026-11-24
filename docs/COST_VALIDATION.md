# How the cost model compares with Koelle's work-years

Written by `tools/validate_cost.py`; do not edit by hand. Source: Koelle, *Handbook of Cost Engineering*,
TCS-TR-184, TRANSCOST 7.2, 2007, page numbers as printed. MYr and work-year are the same thing.

Inputs are the Cost tab's defaults (f1 = f3 = 1, 6 launches a year, 60 flights, vertical assembly then
move), each vehicle's country, and each case's own delta-v split. Nothing was chosen to improve a match. Values marked *read off* come
from a log-scale plot and carry about 5 % of reading error.

## A. Are the relations right? Koelle's own worked examples

His masses, his factors, this module's equations.

| Example | Koelle | MERLIN | Difference | Where |
|---|---|---|---|---|
| Ariane 5 SRB: CER | 5,938 | 5,938 | +0.0 % | Table 2-V, p.104 |
| Ariane 5 SRB: with factors | 5,056 | 5,056 | -0.0 % | Table 2-V, p.104 |
| Ariane 5 Vehicle and shroud: CER | 19,692 | 19,692 | +0.0 % | Table 2-V, p.104 |
| Ariane 5 Vehicle and shroud: with factors | 18,368 | 18,368 | -0.0 % | Table 2-V, p.104 |
| Ariane 5 Vulcain engine: CER | 9,800 | 9,800 | +0.0 % | Table 2-V, p.104 |
| Ariane 5 Vulcain engine: with factors | 6,592 | 6,592 | -0.0 % | Table 2-V, p.104 |
| Ariane 5 Third stage and equipment bay: CER | 7,689 | 7,689 | -0.0 % | Table 2-V, p.104 |
| Ariane 5 Third stage and equipment bay: with factors | 5,838 | 5,838 | +0.0 % | Table 2-V, p.104 |
| Ariane 5 Aestus engine: CER | 890 | 890 | -0.1 % | Table 2-V, p.104 |
| Ariane 5 Aestus engine: with factors | 438 | 438 | +0.1 % | Table 2-V, p.104 |
| Ariane 5 programme | 40,827 | 40,824 | -0.0 % | Table 2-V, p.104 |
| SSME development | 17,921 | 17,921 | +0.0 % | p.103 |
| SSME f2 at 900 firings | 1.220 | 1.203 | -1.4 % | p.103 and Fig. 2-11 |
| Five S-II stages, f4 = 0.86 as given | 4,515 | 4,515 | +0.0 % | p.140 |
| S-II learning factor p at 2-3 a year | 0.960 | 0.963 | +0.3 % | p.140 and Fig. 3-07 |
| S-II f4, units 11-15 at p = 0.96 | 0.860 | 0.860 | +0.0 % | p.140 |
| One F-1, f4 = 0.58 as given | 139 | 139 | -0.1 % | pp.140-141 |
| F-1 learning factor p at 14 a year | 0.920 | 0.931 | +1.2 % | p.141 and Fig. 3-15 |
| F-1 f4, units 76-106 at p = 0.91 | 0.580 | 0.542 | -6.6 % | p.141 |
| Winged SSTO engine, f1-f8 as given | 9,780 | 9,780 | +0.0 % | p.113 |

The relations reproduce. The learning factors are the least exact, because they are read off charts;
Koelle's own F-1 example uses p = 0.92 and then 0.91. His f4 = 0.58 for that batch is also a chart reading.

The CER alone, without the factors, against the ten engines' actual cost (Fig. 2-09, p.37, read off):

| Engine | Mass [kg] | Actual | CER, all factors 1 | Difference |
|---|---|---|---|---|
| RL-10 | 137 | 4,450 | 2,938 | -34.0 % |
| HM-7B | 155 | 3,970 | 3,118 | -21.5 % |
| LE-5 | 255 | 3,850 | 3,959 | +2.8 % |
| RZ.2 | 680 | 4,520 | 6,340 | +40.3 % |
| Viking-2 | 825 | 3,480 | 6,956 | +99.9 % |
| J-2 | 1,575 | 12,800 | 9,488 | -25.9 % |
| Vulcain | 1,685 | 11,100 | 9,800 | -11.7 % |
| LE-7 | 1,720 | 5,050 | 9,898 | +96.0 % |
| SSME | 3,180 | 18,146 | 13,294 | -26.7 % |
| F-1 | 8,452 | 17,800 | 21,253 | +19.4 % |

Median ratio 0.96, from 0.66 to 2.00; 3 of 10 within 20 %.
The factors exist to close exactly this gap: neutral factors are a guess about the team and the technology.

## B. Development effort of MERLIN's sized vehicles

| Programme | Actual | MERLIN | Difference | Where |
|---|---|---|---|---|
| Saturn V | 120,000 | 126,307 | +5.3 % | Fig. 2-01, p.24 (read off) |
| Ariane 5 (Koelle's is the 5G) | 46,500 | 44,343 | -4.6 % | p.105, final; 39,300 as stated in 1996, p.104 |

And the parts of them whose cost can be read off:

| Element | Actual (read off) | MERLIN | Difference | Mass, real / MERLIN [kg] | f2 | Where |
|---|---|---|---|---|---|---|
| F-1 engine | 17,800 | 18,439 | +3.6 % | 8,452 / 6,287 | 1 | Fig. 2-09, p.37 |
| J-2 engine | 12,800 | 8,466 | -33.9 % | 1,575 / 1,242 | 1 | Fig. 2-09, p.37 |
| S-IC stage | 50,500 | 33,815 | -33.0 % | 96,000 / 61,232 | 0.75 | Fig. 2-27, p.53 |
| S-IVB stage | 24,800 | 14,606 | -41.1 % | 11,300 / 8,122 | 0.99 | Fig. 2-27, p.53 |
| Vulcain engine | 11,100 | 6,924 | -37.6 % | 1,685 / 1,119 | 1 | Fig. 2-09, p.37 |

**The programme totals agree better than the parts do, and partly by luck.** MERLIN sizes these vehicles
lighter than they were, so most parts come out cheap. Against that, the Saturn V case names no real engine,
so the J-2 is charged on both stages that use it: 9,502 work-years too many. Charged once, the total is
116,805, -2.7 % against the plot. The spread of the parts is the better
measure of what one number is worth.

S-II, S-IB, H.155, L.140 and the smaller stages of Fig. 2-27 are left out because the scanned labels do not
say which point is whose.

## C. Work-years per flight

Koelle Tables 5-VI and 5-VII (pp.210 and 212) are mostly **prices** asked around 2006, not costs.

| Vehicle | Koelle | MERLIN | MERLIN / middle | Launch mass, his / ours [t] | Trend of real vehicles (book Table 17.5) |
|---|---|---|---|---|---|
| Saturn V | 4,280 | 3,748 | 0.88 | 2,850 / 2,826 | not LEO |
| Ariane 5 ECA | 650-700 | 1,223 | 1.81 | 777 / 855 | not LEO |
| Atlas V 551 | 530-610 | 1,010 | 1.77 | 540 / 539 | 665 |
| Delta IV-H | 600-800 | 2,884 | 4.12 | 733 / 736 | 855 |
| Delta II 7925 (a third stage more) | 350-400 | 557 | 1.49 | 232 / 297 | 298 |
| Falcon 9 (as planned in 2007) | 140-160 | 769 | 5.13 | 300 / 636 | 748 |
| H-IIA 202 | 380-410 | 685 | 1.73 | 285 / 302 | 478 |
| M-5 | 280-300 | 140 | 0.48 | 140 / 144 | 158 |
| Pegasus XL | 80-100 | 61.5 | 0.68 | 23 / 20 | 67.4 |
| Scout | 77 | 95.9 | 1.25 | 22 / 31 | 36.5 |
| Titan II | 250-270 | 448 | 1.72 | 155 / 179 | not LEO |
| Vega (planned price) | 100 | 232 | 2.32 | 130 / 188 | 137 |
| Soyuz-2 from Kourou | 160 | 1,999 | 12.50 | 305 / 361 | 387 |

Median ratio **1.73**, from 0.48 to 12.50. 1 of 13 within 20 %, 8 of 13 within a factor of two.

* small, mostly solid vehicles (4): median 0.96, from 0.48 to 2.32
* liquid vehicles (9): median 1.77, from 0.88 to 12.50
* the trend alone, for the 10 that fly to LEO: median 1.19, from 0.47 to 4.99

Sensitivity to the two assumed inputs (median ratio over the same vehicles):

| Launches a year | Flights | Median ratio |
|---|---|---|
| 2 | 20 | 2.70 |
| 6 | 60 | 1.73 |
| 12 | 120 | 1.37 |
| 12 | 300 | 1.20 |

## What this means

* **The equations are right** (part A): the development and production relations match Koelle's worked examples.
* **Development effort** lands within a few per cent for the two programmes that could be checked, with parts
  up to about 40 % off. Two programmes is a small sample, and +/- 20 % is TRANSCOST's own claim.
* **Cost per flight runs high for liquid vehicles**, about 1.8 times the 2006 price. Those are prices, not costs;
  several vehicles here are later and larger versions than his (the launch-mass column), Falcon 9 and Vega above
  all; and Koelle puts the RS-68, designed for low cost, more than 50 % below his own relation (p.128).
  How much each reason contributes has not been separated.
* **Soyuz** carries Russia's f8 = 2.11 while its price is quoted in European work-years, so the two are not in
  the same unit.
* **Delta IV Heavy** counts each strap-on core with its engine inside, as a hydrogen stage, because MERLIN's
  liquid strap-ons do not separate the engine.
* Launch rate and production run are assumptions, and they move the result by a factor of two (table above).
