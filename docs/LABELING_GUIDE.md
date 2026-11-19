# Labeling guide: which OSHA standard does each injury point to?

We label 60 severe injury reports from manufacturing by hand. Each label says which OSHA standard most directly covers the hazard that caused the injury. These labels are the answer key for the safety rules assistant (retrieval over 29 CFR): if it retrieves the standard we chose, it got the case right.

**Your file:** `data/labels/to_label_<your name>.csv` (25 cases: 15 only yours, 10 shared with a teammate). **Time:** about 4 minutes a case, so under 2 hours. **Do not look at a teammate's labels before you finish**; the shared cases measure how much we agree.

## The columns

| Column | Given or yours | What it holds |
|---|---|---|
| `case` | given | C01 to C60 |
| `narrative` | given | what happened, as OSHA published it |
| `event`, `source`, `nature`, `body_part` | given | OSHA's own codes: how it happened, what did it, the injury, where |
| `naics` | given | the industry (31 to 33 is manufacturing) |
| `primary_standard` | **yours** | the one standard that best covers the cause, written like `1910.212(a)(1)`; at least the section (`1910.212`) |
| `secondary_standard` | yours, optional | a second standard that also clearly applies, same format |
| `confidence` | **yours** | `high`, `medium` or `low` |
| `no_standard_reason` | yours, only when there is no primary | `vague narrative`, `no specific standard (general duty)`, or a short reason |
| `notes` | yours, optional | anything that made the case hard |

## How to label a case

1. **Read the narrative twice.** Find the *activity* (normal operation, or cleaning, maintenance, unjamming) and the *hazard* (an unguarded moving part, a fall, a forklift, a hot surface, a chemical).
2. **Look at the given `event` and `source`.** They are OSHA's reading of the same text and usually point to the family of standards.
3. **Pick the family from the cheat sheet below**, then the most specific section that fits. A specific standard wins over a general one: a power press injury is `1910.217`, not the general machine guarding `1910.212`.
4. **Check the wording on eCFR** (https://www.ecfr.gov/current/title-29/subtitle-B/chapter-XVII/part-1910). Open the section and read its first paragraphs. Give the paragraph when you can, for example `1910.212(a)(1)`; the section alone is fine when you are unsure of the paragraph.
5. **Set the confidence.** `high`: the narrative names the machine or the hazard and one standard clearly fits. `medium`: two standards are close, or the machine type is unclear. `low`: you had to guess.
6. **When no standard fits,** leave `primary_standard` empty and fill `no_standard_reason`. Do not force a standard onto a vague narrative.

### Rules that settle most doubts

* **Injured while cleaning, clearing a jam, servicing or setting up a machine:** the cause is usually that the machine was not shut down and locked out, so the primary is `1910.147` (control of hazardous energy). The guarding standard goes in `secondary_standard`.
* **Injured during normal operation by a moving part:** guarding, `1910.212` or the machine's own standard.
* **Fall from a height:** `1910.28` (duty to have fall protection); from a ladder: `1910.23`. **Slip or trip on the same level:** `1910.22` (walking working surfaces, general).
* **Forklift or other powered truck:** `1910.178`; when the narrative points to an untrained operator, `1910.178(l)`.
* **Only one standard per column.** Write the citation only, no title.
* **General industry only.** Our cases are manufacturing, so the standards are in Part 1910 (Part 1926 is construction).
* **Judge the cause, not the injury.** An amputation from an unguarded saw is a guarding case, whatever the body part.

## Cheat sheet

Check every citation on eCFR before you use it; this list is a starting point, not the answer.

| Hazard in the narrative | Start with | Notes |
|---|---|---|
| Caught in or struck by moving machine parts, point of operation, nip points | `1910.212(a)(1)`, point of operation `1910.212(a)(3)(ii)` | general machine guarding |
| Cleaning, unjamming, maintenance or setup without shutting the machine down | `1910.147` | lockout/tagout; procedures in `1910.147(c)(4)(i)`, the program in `1910.147(c)(1)` |
| Mechanical power press | `1910.217` | |
| Belts, pulleys, gears, shafts, chains, sprockets | `1910.219` | mechanical power transmission |
| Saws and woodworking machines | `1910.213` | |
| Grinders, abrasive wheels | `1910.215` | |
| Bakery, textile, pulp and paper, sawmill machinery | `1910.263`, `1910.262`, `1910.261`, `1910.265` | industry specific machinery |
| Forklift, pallet jack, powered industrial truck | `1910.178` | training `(l)`, operations `(m)` |
| Overhead crane, hoist, slings | `1910.179`, `1910.184` | |
| Falling or shifting stacked material, storage | `1910.176` | materials handling |
| Fall to a lower level | `1910.28`, systems in `1910.29` | |
| Ladder | `1910.23` | |
| Slip or trip on the same level, housekeeping, wet floor | `1910.22(a)` | |
| Electric shock, arc flash | `1910.333` (work practices), `1910.303` (equipment) | |
| Chemical burn or exposure | `1910.1200` (hazard communication), PPE `1910.132` | |
| Hot surface, molten metal, burns where PPE was missing | `1910.132`, hands `1910.138`, eyes and face `1910.133` | |
| Welding, cutting | `1910.252` | |
| Confined space (tank, silo, pit) | `1910.146` | |
| Flammable liquids, fire, explosion of stored liquids | `1910.106` | |
| Overexertion, ergonomics, a hazard no standard covers | none | `no_standard_reason`: `no specific standard (general duty)`; OSHA would use the General Duty Clause, Section 5(a)(1) of the OSH Act |

## A worked example

> *"An employee's hand was pulled into the rollers of a laminator machine during a cleaning cycle, resulting in an amputation to their right index fingertip."* Event: Caught in running equipment or machinery during maintenance, cleaning.

* Activity: cleaning while the rollers ran. Hazard: an in running nip point.
* Rule: cleaning a running machine points to energy control.
* `primary_standard`: `1910.147` · `secondary_standard`: `1910.212(a)(1)` · `confidence`: `medium` (the narrative does not say whether the machine could have been locked out during the cleaning cycle) · `notes`: "cleaning cycle may need the rollers to run; then guarding is the primary".

## When you finish

Save the file with the same name and tell the team. Kevin merges the three files, compares the 15 shared cases at the section level (`1910.147` against `1910.147`), and the team settles every disagreement together; the settled label goes into the answer key. Our target is that at least 70% of the shared cases agree before discussion. If we agree less, we tighten this guide and label again.
