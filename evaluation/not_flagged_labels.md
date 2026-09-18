# Mutants that ended "not flagged", inspected by hand

Stand-in chat(), 18 September 2026. Each is labelled *equivalent* (the change does not alter what the code computes) or *missed*.

| Sample | Mutant | Label | Why |
|---|---|---|---|
| F_capital | `k * 12.5 * ead` became `k / 12.5 * ead` in `rwa` | missed | The methodology gives this formula only as an image (C-0020) and in loose prose ("scaled by 12.5 and multiplied by ..."). The stand-in judge does not link `rwa` to the image equation, so no check is required and none runs. With a judge that links it, the unit would end *Traced - check undecided* (flagged otherwise). A limit of what can be read, listed in manual chapter 12. |
| A_minimal | `1 - volume_discount(n)` became `1 + volume_discount(n)` in `parcel_price` | missed | The methodology states this step only in prose ("The discount is applied to the price after surcharge"); there is no formula to compare with, so no mathematical check is required. |
| A_minimal | `with_fuel * (1 - ...)` became `with_fuel / (1 - ...)` in `parcel_price` | missed | The same step, the same reason. |
| D_dosing | `dose * factor / 10` became `dose / factor / 10` in `adjusted_dose` | missed | The methodology gives the formula as an image without preserved markup, and in prose ("The dose is multiplied by the factor ..."). The stand-in does not read a formula out of that sentence; a real model might, through the read-formula-from-prose question. |

What the four have in common: the methodology does not state the formula in a form that code can read. None is a case in which a readable formula was linked and the check passed wrongly.

One such case did exist and was found by this harness: `min(0.22, 0.01 * n)` against `min(0.2, 0.01 * n)` was first reported as agreeing, because the two sides only part for n above 20, outside the generic sampling ranges. The numerical check now searches for the points at which the two sides of every maximum, minimum and comparison meet (`aiva4_checks.crossing_points`), and the equivalence corpus holds four pairs of this kind.
