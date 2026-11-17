# Optimising the staging split

The tool can search the delta-v allocation between stages for the best vehicle, and — if the design asks —
**size the vehicle from that allocation instead of the one you typed**, so the mass, geometry, loads,
drawing and cost all describe the same rocket as the split that is reported.

This document says what the search does, what it does not promise, and what was measured before any of it
was trusted.

---

## 1. Turning it on

Two inputs in the `vehicle:` block, both visible in the GUI:

```yaml
vehicle:
  optimise_dv_split: {v: true,  u: "-", d: "...", s: "User", t: user}
  optimise_objective: {v: glom, u: "-", d: "glom | cost | payload", s: "User", t: user}
```

With `optimise_dv_split` **on** — the shipped default since v1.1 — the allocation is replaced by the optimum
*before* sizing, and you are told what it changed and from what. With it **off** nothing changes: your split is
used exactly as written. When no split gives a vehicle that sizes, yours is used and the page says the
optimisation was requested but not applied. A design file with no `optimise_dv_split` key is still treated as off. **Your design file is not modified** until you save it; the GUI writes the applied
split into the input panel as a changed value with its revert arrow, like any other override.

Off by default on purpose. The staging split is a decision the designer makes, and a tool that silently
re-made it would be reporting someone else's design.

## 2. What you can optimise towards

| `optimise_objective` | Minimises / maximises | Notes |
|---|---|---|
| `glom` *(default)* | **Minimises** gross lift-off mass at the design payload | The usual question, and the fastest. |
| `cost` | **Minimises** development cost | The mass-driven TRANSCOST CERs (effort ~ dry mass<sup>0.48</sup> per element). **Not** cost per flight — see below. |
| `payload` | **Maximises** payload at the design's own lift-off mass | "The same rocket, carrying as much as it can." ~25× slower than `glom`, because each point bisects on payload. |

**Why `cost` is development cost and not cost per flight.** The chapter's cost per flight is a rule of thumb
on *payload* mass — 5,000 USD/lb — so in this tool it comes out at the same dollar for every vehicle that
carries the same payload. Measured across a 28 % spread of lift-off mass on the shipped default it did not
move by one dollar. An objective that cannot see the design it is optimising is worse than no objective, so
`cost` uses the development CERs, which are mass-driven and do respond. A test pins this, and will fail if
cost per flight ever becomes design-sensitive and the choice is worth revisiting.

**The cost optimum is not the mass optimum.** On the shipped default, minimum GLOM is near a 35/65 split and
minimum development cost near 46/54. That is a real trade and not an error: development effort is a sum of
per-element M<sup>0.48</sup> terms, and the sum is not minimised by minimising the total. It is the main
reason the objective is worth choosing rather than assuming.

**`payload` and `glom` should nearly agree**, and do — 35.4/64.6 against 35.1/64.9 on the default. They are
duals, exactly equal only if the mass relationships were scale-invariant, which power-law MERs are not.

## 3. How the search works, and why it is not just a local search

**Explore, then refine.** The simplex of possible allocations is sampled (uniformly, by a Dirichlet draw),
the feasible points are kept, and a local search runs from the best few. Sampling is adaptive: it stops once
there are enough feasible points to seed the searches, so an easy two-stage vehicle pays for ~25 sizings and
a hard case for up to 200.

This is not sophistication for its own sake. The first version went straight to a local search from the
equal split, and on `examples/example_3stage_leo.yaml` it **failed silently**:

- the equal split of that design does not size at all;
- every neighbouring point in the simplex is equally infeasible, so the search saw a flat penalty with no
  gradient;
- Nelder-Mead gave up after 11 evaluations and returned the equal split it had started from, reporting it
  as the optimum;
- the GUI then wrote that *worse* split into the user's design and reported it as about a trillion
  kilograms lighter, because nothing checked the `success` flag.

A multi-start finds **338,329 kg against that design's own 355,389 kg** — a 4.8 % improvement that was there
to be found the whole time. The failure was structural, not a tuning problem: a launch vehicle's feasible
region in the staging simplex is a narrow band, and a local search started outside it has nothing to follow,
because "infeasible" is one flat value however far outside you are.

**The feasibility ladder.** Each point is ranked: feasible; sized but carrying validation ERRORs; sized but
not converged; would not size. The search always prefers a lower rung, and orders by the objective within a
rung. The penalties are applied to the objective **normalised by the baseline**, because the three
objectives differ by orders of magnitude — a fixed penalty of 1e9 sits above a lift-off mass in kilograms
and below a development cost in dollars, and the ordering would silently invert between objectives.

**Reproducible.** The sampler is seeded, so the same design gives the same answer. Different seeds agree to
well within 1 %.

## 4. What it does not promise

- **It is a local optimum.** Several searches are run and the **spread between them is reported**, which is
  the only honest evidence about whether the answer is *a* local optimum or *the* optimum. On the shipped
  designs the starts agree to 0.000 %, which is good evidence here and not a proof in general.
- **Only the delta-v allocation is searched.** Stage count, propellants, diameters, engines and the
  structural model are all fixed. Those are compared by evaluating configurations you supply
  (`compare_designs`, and the GUI's stage-count and booster controls), never by implicit search.
- **No trajectory quantity enters the objective.** This is deliberate. The drag model is a single
  C<sub>D</sub>(M) curve and the tool has no throttle profile, so a trajectory-derived objective would be
  optimising against the weakest part of the model. The loss regression is used, as in an ordinary sizing.
- **An optimiser exploits model error.** The monocoque structure sizing comes out at ~2.04× the MER mass on
  the default design (roadmap R21) and is not fed back. That disagreement is harmless while nothing searches
  over the variables it affects — it is a reason to be careful about *widening* the search, not about the
  staging split.

## 5. What the optimum is pressed against

The search reports the validation issues present at the optimum **that were not present at the design you
started from**. That difference is the engineering answer: a number alone does not tell you what to change,
and listing the warnings a design already carried would bury the one new constraint under housekeeping you
have already seen.

## 6. Measured before it was trusted

Two things were checked first, prompted by Balesdent (2011), *Multidisciplinary Design Optimization of
Launch Vehicles*, Appendix B, which found a fixed-point iteration converging to **different** optima from
different seeds and a local search succeeding **10 %** of the time from random starts.

**The sizing loop's seed.** `size_vehicle` is a fixed-point iteration seeded from an aggregate guess
(`convergence.SEED_S`, `SEED_DRY_FACTOR`, `SEED_LOADED_FACTOR`). If the converged answer moved with that
guess, every number the tool reports would be a function of where the search began. Swept over
s = 0.05 … 0.18 on five designs — the shipped default, the three-stage example, the solid smallsat,
Ariane 5 ECA and Delta IV Heavy — the converged GLOM was **identical to ~1e-8 relative**, i.e. to the
convergence tolerance. The loop has one fixed point. A seed above ~0.18 cannot start at all on some designs,
because the seeding algebra itself runs out of mass ratio; where it starts, it finishes in the same place.

**The optimiser's own reliability.** 40 random starts on the three-stage example: 10 produced a feasible
design, and of those, 9 landed within 0.1 % of the best. The 25 % feasible-start rate is the same phenomenon
Balesdent measured, and is exactly why the exploration phase exists.

Both are pinned as tests, so they are claims that stay true rather than claims that were true once.
