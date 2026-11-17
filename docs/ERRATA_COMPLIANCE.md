# Errata compliance

Source document: *Errata for 1st Edition of "Design of Rockets and Space Launch Vehicles", Edberg & Costa*,
last revised 2023 Jan. 12 (supplied by the user; 38 pages).

The tool is built from the **2nd edition** (AIAA 2022). The errata is written against the **1st edition**, so its
equation numbers are the 1st-edition ones (`eq. 3.24`, `eq. 5.5`, …) while this project cites the 2nd edition
(`Eq. 3:32`, `Eq. 5:5a`, …). Many 1st-edition errors were already fixed in the printing used here; for those items
the entry below says **already correct in the 2nd ed.** and the check exists so that a future edit cannot drift
back to the wrong form.

Every item in the table is pinned by a test in `tests/test_errata.py` unless the "Verification" column says
otherwise. Test suite after this pass: **159 passed, 0 failed**.

Legend for *Status*:

| Status | Meaning |
|---|---|
| **applied** | the tool was changed in this pass to follow the errata |
| **already correct** | the 2nd-edition text the tool was built from already prints the corrected form, and the tool follows it |
| **added** | the errata supplies guidance that is not an equation fix; the tool gained a new option or check |
| **n/a** | the item does not touch anything this tool computes (editorial, figure, or an un-implemented chapter) |

---

## 1. Items that affect a calculation

| # | Errata item (1st-ed. page) | 2nd-ed. reference | What it says | Status | What the tool does | Verification |
|---|---|---|---|---|---|---|
| 1 | p. 159 item 1 — remove the spurious `s` and `s²` from the denominators of **eq. 3.24** | Eq. 3:32, p.181 | `dv_total = sqrt(v_circ² + 2 g0 h (R/(R+h))²) + 0.0015 Ta² + 0.0882 Ta + 1,036 m/s`; the coefficients carry the units, `Ta` is a plain number of seconds | **added** | implemented as its own loss model, `mission.losses.model: book_simple` → `delta_v.simple_total_mps`. Method register **M50** | `test_eq_3_32_simple_total_speed` pins the polynomial term by term and the 1,379 m/s hand value at Ta = 450 s |
| 2 | p. 159 item 2 — "`Ta` is the ascent time in seconds" | p.181 | fixes the units of the input | **added** | `Ta` is taken from the summed sized burn times plus staging delays (same quantity M37 uses), or from `mission.ascent_time_override_s` | same test; `ASCTIME` warning when overridden |
| 3 | (companion fit, not an erratum) | Eq. 3:33–3:34, p.181 | `dv_penalty = K1 + K2·Ta`, `K1 = 662.1 + 1.602 Hp + 0.001224 Hp²`, `K2 = 1.7871 − 0.0009687 Hp` | **added** | third loss model `book_k1k2` → `delta_v.k1k2_penalty_mps`. Method register **M51**. Added because items 1–2 forced a review of all three published fits | `test_eq_3_33_k1_k2_penalty`; `test_the_three_book_loss_models_agree_within_the_regression_scatter` shows the three fits spread 302 m/s on the default case (9,231 / 9,408 / 9,533 m/s), inside the regression's own ~260 m/s RMS |
| 4 | p. 163 item 2 — **Eq. 3.31** middle line: `sin β` replaces `cos β` | Eqs. 3:39–3:40, p.185 | `v_burnout,East = v_burnout cos γ **sin β**` | **already correct** | `orbit.needed_speed` builds the East component with `sin(azimuth)`, so a due-East launch subtracts the whole site speed and a due-North launch adds it in quadrature | `test_example_3_9_east_component_uses_sine_of_the_azimuth` — the two limiting cases would be swapped if `cos β` were used |
| 5 | p. 165 / p. 183 — Pegasus air-drop **drag loss is 322 m/s**, not 40 m/s | §3.7 (air launch) | the first Pegasus flight measured 322 m/s of drag loss; air launch is not the drag saving it is assumed to be | **applied** | `validation/pegasus_xl.yaml` now carries `drag_loss_mps: 322` with the errata as its `s:` provenance (it was 50 m/s, a plausible-looking guess). Ref. [21] (Mosier et al., 1990) recorded in the YAML source field | `tools/make_validation_cases.py`; the Pegasus case is re-run in `tests/test_validation_cases.py`. Effect: GLOM **+15.2 %** (32,040 → 36,908 kg against a published 23,130 kg), i.e. the error grows from +38 % to +60 % at the baseline Δv split (+30 % → +45 % after the Δv-split optimisation). The errata makes the honest answer worse |
| 6 | p. 242 — **eq. 5.5**: the right-hand denominator is `m_s + m_PL`-corrected, i.e. `σ = m_s/(m_s + m_p) = m_s/(m_0 − m_PL)` | Eq. 5:5a, pp.274–275 | the structural factor excludes the payload from both numerator and denominator | **already correct** | this is the tool's primary convention (M11): `s = m_s/(m_s + m_p)` with the carried upper mass excluded from `m_s`; `eps = s/(1−s)` is derived, never input | `tests/test_staging.py` round-trip; `test_discarded_hardware_excluded_from_next_stage` |
| 7 | p. 260 — `µ = exp(∆v/(g0 Isp))` (missing parenthesis) | Eq. 5:84, p.321 | the whole `g0 Isp` product is in the denominator | **already correct** | `staging.mass_ratio_from_dv` | `test_example_1_stage_2_propellant_matches_the_corrected_value` (µ = 4.2725 from 4,842 m/s at 340 s) |
| 8 | p. 286 — use **eq. 5.66** for the strap-on exit speed, and use the *total* SRB mass flow | Eq. 5:66, p.306 | the parallel-burn phase must use the mass-averaged exhaust speed `v_e,ave = Σ(v_ei ṁ_i)/Σṁ_i`, with all boosters' flow summed | **already correct** | `boosters.mass_averaged_isp` averages over the core plus *every* booster in the group (`n_boosters × ṁ_booster`), per phase | `tests/test_boosters.py` reproduces the book's Shuttle exercise (pp.323–325) independently of the sizing loop |
| 9 | p. 296 — NOTE: claimed payload ratios of 14 % are unreal, "lucky to get 4 %"; the usual cause is failing to carry the whole loaded upper step as the lower step's payload | p.296 | a sanity rule for the designer | **added** | two things: (a) the tool *does* carry the entire loaded upper step — that is `convergence.carried()`, and it is tested; (b) a new **PAYFRAC** warning fires when `m_PL/GLOM > 6 %`, naming the three usual culprits (structural factors, Isp, losses). Method register **M53**. The threshold is 6 %, not 4 %, so that legitimate high-energy and air-launched designs are not flagged on every run | `test_optimistic_payload_fraction_is_flagged` — trips at 6.1 % with `s = 0.02` and an 8,000 m/s budget, and shows the same optimistic structure reaches only 3.9 % on the real 9.4 km/s mission. No validation case trips it |
| 10 | p. 296 — the ∆v bookkeeping: `∆v1 + ∆v2 + ∆v_loss = ∆v_design`, with the loss either split in proportion to the ∆v shares or assigned entirely to step 1 | §5 staging | two admissible ways to allocate losses between steps | **already correct** | losses enter the single `dv_required_mps` budget, which is then split between stages by `vehicle.dv_allocation_mode` (`fractions`, `equal_mu`, `optimize`). Assigning the whole loss to step 1 is reproducible by setting the stage-1 fraction accordingly | `tests/test_orbit_deltav.py` (budget lines sum to the total, margin applied once) |
| 11 | p. 419 — **Eq. 8.1** second term should read `ṁ = T/(g0 Isp)` | Eq. 8:1, p.469 | mass flow from thrust | **already correct** | `propulsion.mass_flow` | `test_eq_8_1_mass_flow_is_thrust_over_g0_isp` |
| 12 | p. 427 — **Table 8.2**, last two rows (added 2022FEB04): a √2 ellipsoidal dome has area `1.62323 πR²` and volume `1.48096 R³` (**no π**); a barrel with two of them has area `2πRh + 3.24645 πR²` and volume `πR²h + 2.96192 R³` | Table 8.2, p.462 | the volume coefficient is dimensionless-with-no-π — the classic trap | **already correct** | `tank_sizing.dome_area` / `dome_volume` are the general AR forms; at AR = √2 they return exactly these coefficients, and at AR = 1 the hemisphere limits | `test_table_8_2_sqrt2_ellipsoidal_dome_coefficients` and `test_hemispherical_dome_is_the_ar_1_limit` |
| 13 | p. 430 item 2 — **Example 1**: `m_p2 = m_PL2 (µ2−1)(1−σ2)/(1−µ2σ2) = 51.44 T` | Eq. 5:85, p.321 | the corrected printed value | **already correct** | `staging.propellant_aggregate`. Note on rounding: the errata prints µ rounded to 4.27, which gives 51.36 T; the **unrounded** µ = 4.2725 implied by the example's own 4,842 m/s and 340 s gives 51.44 T, i.e. the printed answer | `test_example_1_stage_2_propellant_matches_the_corrected_value` pins both values so the rounding sensitivity stays documented |
| 14 | p. 436 — a solid motor has **no added thrust structure and no rocket engine**; the aft casing is the thrust structure and includes the nozzle | §8.5, pp.486–490 | the SRM casing MER is all-inclusive | **already correct** | `solid_motor.size_solid_stage` adds casing, insulation-in-casing, igniter and TVC only through `k_SRM`; the engine, gimbal, thrust-structure and feed-system MERs are never applied to a solid stage. Stated in method register **M41** | `tests/test_solid_motor.py::test_solid_stage_has_no_engine_thrust_structure_or_feed_system` |
| 15 | p. 443 item 2 — **Table 8.8** item 3: "(Use `m_PAF = 0.15 m_PL` for smaller payloads.)" | Table 8.8, p.495 | the `0.0755 m_PL + 50` MER over-predicts for small payloads | **applied** | `vehicle.payload_adapter_method: mer \| fraction \| auto`. `auto` uses `0.15 m_PL` below `paf_fraction_payload_threshold_kg` (1,000 kg, an **assumption**, in `config/engineering_assumptions.yaml`) and the MER above it. Default stays `mer` so large-vehicle results are unchanged. New **PAFSMALL** warning when the MER exceeds 20 % of the payload. Method register **M52** | `test_payload_adapter_small_payload_guidance` (150 kg → 61 kg MER vs 22.5 kg fraction; 10 t → 805 kg either way) and `test_heavy_adapter_on_a_small_payload_is_flagged` (the 150 kg solid smallsat example: 41 % of payload, flagged, and the `auto` run is lighter). All small-launcher validation cases now use `auto` |
| 16 | p. 452 — **Table 8.11**: the payload fairing belongs to **step 1**, because it is jettisoned soon after step 1 is jettisoned and is not carried to orbit | Table 8.11, p.504 | fairing mass is carried by the lower step only | **already correct** | the fairing is carried in `U_j` only while `j+1 < jettison_at_stage_start`; the default in every example and validation case is 2, i.e. jettisoned at the start of the stage-2 burn, so stage 1 carries it and stage 2 does not. `FAIRJET` rejects anything outside 2..N+1 | `tests/test_mass_accounting.py::test_conservation_of_mass_across_burns_and_separation` (stage-2 ignition mass = stage-1 burnout minus stage 1 **and** the fairing) and `test_fairing_carried_to_burnout_changes_upper_stage` (setting jettison to N+1 makes the upper stage heavier) |
| 17 | p. 469 — **Example 4**: `x_interstage = h_interstage + z_c = 23.64 + 1.90 = 25.54 m` | Example 4, p.504 | an arithmetic fix in the CM bookkeeping | **already correct** | `mass_properties` places every item at `z0 + local CM offset` from the global layout, so this addition is structural rather than a magic number | `tests/test_center_of_mass.py::test_two_body_hand_calculation` and `test_liftoff_cm_matches_independent_recomputation`; book Table 8.22 roll inertia reproduced within 1 % in `tests/test_inertia.py` |

## 2. Items reviewed and found not to touch this tool

| Errata item | Why it does not apply |
|---|---|
| p. 141 Example 3.3 — missing `²` on `v_HE` in the escape-speed radical | the tool has no hyperbolic/escape-energy model. Listed as a gap in the roadmap (C3 / escape missions) |
| p. 190 item 3 — **Eq. 4.2** mixture bulk density `ρ` | the tool never uses a mixture bulk density: oxidiser and fuel are split by O/F (Eq. 8:5a/b) and each tank is sized at its own propellant density |
| p. 196 — `I_tot = T_c t_b`, `T_ave = I_tot/t_b` | already the form used by `solid_motor.propellant_mass_from_total_impulse` via 2nd-ed. Eqs. 8:21–8:22 |
| p. 203 — replacement Table 4.3 (thrust / Isp / c* / C_F identities) | `propulsion` uses `T = ṁ g0 Isp` and `c* `/`C_F` only inside `engine_geometry` (Eqs. 8:28–8:33); the replacement table is a consolidated restatement of relations already implemented, with no numerical change |
| p. 243 Fig. 5.4 and p. 244 **eq. 5.12** (`v = −c ln[σ + (1−σ)π]`) | the tool works in mass ratio `µ` and structural factor `s` throughout; the payload-ratio form `π` is reported but never used as a sizing equation |
| p. 244 items 2–3 (2.071 instead of 2.09; `c ≥ 4.538 km/s`) | numbers inside a worked SSTO discussion that the tool does not reproduce |
| p. 261 Table 5.2, p. 278 Table 5.3 ("Stage" → "Step") | terminology. This project uses "stage" throughout and says so in the user manual |
| Chapter 6 (pp. 298–327): `R_planet` for `R_e`, sign fixes in Eqs. 6.23 / 6.26 / 6.36 / 6.40 | no trajectory integration existed at this pass (v0.4). One was added in v0.6, and this row has not been re-audited against it |
| Chapter 10 (pp. 576–602): Eqs. 10.21 / 10.42 / 10.45 and Examples 6b | no loads or structural-analysis module existed at this pass. They were added later, and this row has not been re-audited against them |
| Chapter 12 (pp. 708+): Eqs. 12.12 / 12.23 / 12.24 | no stability-and-control module existed at this pass. One was added later, and this row has not been re-audited against it |
| Name changes (CCAFS → CCSFS, VAFB → VSFB, Aerojet Rocketdyne, Orbital ATK) | affects prose only; the launch-site table in `config/launch_sites.yaml` uses the current names |
| p. 22 item 3 — add Mahia Peninsula, NZ (39.26° S, 177.86° E) to Table 1.1 | no launch-site database existed at this pass; `config/launch_sites.yaml` now provides one. The Electron validation case already uses the Mahia latitude, with the errata's value as its source |
| All remaining items (figure captions, spelling, comma removal in Delta PAF model numbers such as 7925/3712A, bold-face vector notation, paragraph inserts) | editorial; no equation or number used by the tool |

## 3. Net numerical effect of this pass

All figures are measured, not estimated: each is the difference between two runs of the same input file.

| Change | Effect |
|---|---|
| Pegasus drag loss 50 → 322 m/s (item 5) | Pegasus XL GLOM **+15.2 %** (32,040 → 36,908 kg). Against the published 23,130 kg the optimised-split error grows from +30 % to +45 %, making Pegasus the worst case in the validation set. Recording the source is the point: the tool now carries the measured flight value instead of a plausible guess |
| `payload_adapter_method: auto` on the small-launcher cases (item 15) | Electron −4.4 %, Pegasus XL −2.1 %, Firefly Alpha −0.3 %, and the 150 kg solid smallsat example −9.5 % (40,343 → 36,503 kg) GLOM. Vega and Epsilon are unchanged: their payloads are above the 1,000 kg switch-over |
| Two added loss models (items 1–3) | no change to any default or validation case — `book_penalty` remains the default. On the default design the three book fits give Δv = 9,231 (Eq. 3:32) / 9,408 (Eqs. 3:35–3:38) / 9,533 m/s (Eqs. 3:33–3:34), a 302 m/s spread, and GLOM 380,893 / 410,003 / 432,288 kg — a ±6 % sizing band from the choice of fit alone |
| New PAYFRAC / PAFSMALL / PAFMETH / LOSSMODEL checks (items 9, 15) | no numerical change. No validation case trips PAYFRAC; the 150 kg smallsat example trips PAFSMALL under the `mer` method |
| Everything else | already compliant; no numbers moved |

## 4. What the errata did **not** fix

Two numerical problems found while validating remain open and are **not** errata items — they are limitations of the book's own MERs, documented in `docs/VALIDATION_REPORT.md`:

1. **Solid-motor casing MER (Eq. 8:18–8:19).** `k = 0.1154` for graphite-epoxy gives `s = 0.1035`, but real filament-wound motors run 0.08–0.09 (Vega P80 0.083, Zefiro 23 0.081, Pegasus Orion 50S XL 0.091). Every solid stage comes out 1.2–1.6× heavy; substituting published casing ratios moves Vega from +25 % to +5 %.
2. **Avionics MER (Table 8.8 line 6).** The 75 kg → 350 kg step at 1 t payload is heavy for a small launcher and contributes several per cent of GLOM on the Electron-class cases.
