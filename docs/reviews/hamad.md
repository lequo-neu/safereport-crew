# Hamad's review

## B3. Hand check of the Category 1 rules (issue #4)

**What is checked.** 100 reports from the 2025 holdout (`data/labels/category1_check.csv`,
seed 42), labelled by hand against OSHA's Category 1 criteria; Khoa labels 15 of them on his own
to measure agreement. The labeling rules are in `docs/CATEGORY1_LABELING.md`; Kevin settled the
open points on issue #4 on 21 November 2026.

**Rules for the labels**, as settled on #4:

1. `cannot_tell` counts as neither right nor wrong. Recall and false alarms are scored on the
   cases we can decide; the `cannot_tell` share is reported separately with its reasons.
2. SVEP and repeat offenders: `cannot_tell` for every report (reason: needs violation history).
3. Emphasis programs: labelled against the national programs only; local and regional programs
   are a gap.
4. Employer history: the app's matching rule; a "possible" match is `cannot_tell`, not yes.
5. Imminent danger: `cannot_tell` unless the text says the hazard is still there; reported apart
   from recall.
6. The rules are scored as they are on `main` at `fd15b06`, with no tuning on the 100. A rule
   change the sample suggests goes in a new issue and is not re-scored on the same 100.

**Gaps the check cannot close.**

* **Repeat offenders and SVEP.** OSHA's fourth criterion needs the employer's citation history
  and the Severe Violator Enforcement Program list. The SIR file does not link to OSHA's citation
  records (the inspection numbers do not match; see Limits in the README), so neither the hand
  check nor the crew can tell whether a report meets it.
* **Local and regional emphasis programs.** The memo counts local, regional and national
  programs; the crew encodes only twelve national ones, and seven of those take their scope from
  the title, not the directive. A report covered only by an LEP or REP is missed by the rules and
  is not counted as a miss here. Suspected cases are listed in the labels' `notes`. Adding the
  Region 6 (Texas) programs would be an Advance proposal for #10.
* **Imminent danger.** No rule decides it; the app leaves it to the Area Director's flag. It is
  reported apart.
* **Employer history across states.** The app, and so the hand check, looks for earlier reports
  only in the same state.

**Results.** To come once both label files are back (23 November).

## B1. Review of the triage logic and the app (issue #2)

Checked on `main` at `fd15b06`, offline (no model called, nothing paid). Items marked
**to confirm** are a reviewer's judgement that Hamad still has to make; everything else was
checked against the code, the data or OSHA's memo.

### Category 1 rules against OSHA's memo

The memo of 4 March 2016 (section 5, Category 1) lists six conditions. How the crew covers each
(`triage.category_one`, `signals.py`, `employers.repeats_within`):

| Memo condition | In the crew | Gap |
|---|---|---|
| All fatalities and 2 or more in-patient hospitalizations | `hospitalized >= 2` | No fatality check. The SIR file has no death field; 9 of 105,996 narratives mention a death (none in 2025), so the effect is small, but the rule does not match the memo. |
| Any injury involving a worker under 18 | an age of 14 to 17 next to "employee" or "worker" in the narrative, or a user flag | Narrow: "minor", "teenage" or an age written another way is missed. OSHA's file has no age field. |
| History of the same or similar hazards within 12 months | a confirmed earlier report from the same employer in the same state, same OIICS event division | "Similar" is the first digit of the event code, which is broad (all falls, slips and trips are one division). See USPS below. |
| Repeat offenders and SVEP | not covered | The SIR file does not link to OSHA's citations (Kevin, #4). |
| A hazard under a local, regional or national emphasis program | the 5 national programs whose scope was read from the directive; 7 more only raise the priority | No local or regional programs; trenching, silica, lead and the others force nothing. See 20251111409. |
| Any imminent danger | a person's flag only | By design: a narrative describes what already happened. |

### The Texas week (17 to 23 November 2025): the 8 Category 1 reports

| Report | Trigger | Check |
|---|---|---|
| 20251111512, Cavco, Fort Worth (321991) | amputations NEP | Miter saw amputation in an Appendix B industry. **Correct.** |
| 20251111462, DMS-South/Bailey Tool, Lancaster (332119) | amputations NEP | Punch press amputation. **Correct.** |
| 20251111502, Proler Tubing, Dayton (332996) | amputations NEP | Roller machine amputation. **Correct.** |
| 20251111454, Velocity Sheet Metal, Selma (332322) | amputations NEP | Shear amputation. **Correct.** |
| 20251111522, NC Works, San Antonio (314110) | employer history (20241110998) | Same site, same roller-clog hazard, 358 days earlier. **Correct.** |
| 20251111604, Dollar Tree, Abilene (452112) | employer history (2025010815) | Earlier report in Princeton (452319): another store, matched as the same company because the first three NAICS digits agree. Both are trips over a box. **To confirm:** does the memo's "employer" mean the company or the establishment? See below. |
| 20251111619, USPS, Crystal City (491110) | employer history (20241211946) and warehousing NEP | History: the earlier report is a carrier falling into a ditch in Mexia; this one is a ladder fall hanging a display. Both event codes are in group 41 (fall to a lower level); the place, the work and the source differ. Warehousing NEP: the directive covers processing and distribution centers only, and 491110 also holds retail post offices, which a display suggests. **To confirm:** both triggers look weak. See below. |
| 20251111445, Axis Power, Edna (237130) | falls NEP | A 5 foot fall from a crane truck bed in construction. The crew reads the Falls NEP as every construction fall from height. **To confirm:** whether a fall from a vehicle bed under 6 feet is in the program's scope. See below. |

**20251111409** (Everflow Plumbing, Arlington, 238220), Category 2 now: dirt and rock fell from
the wall of an underground tunnel under a building onto a worker's legs (event: collapse in an
open trench or excavation). The trenching and excavation NEP (CPL 02-00-161) is found, but its
scope was never read from the directive, so it only adds to the priority (4.006; the plan still
inspects it, and OSHA did). **To confirm:** if the program covers this work, the memo makes it
Category 1 and the crew misses it; reading the directive's scope into
`data/reference/emphasis_programs.toml` would fix it for every report.

#### The four open cases, against the directives (read 21 November 2026)

Sources: the memo of 4 March 2016, section 5; CPL 03-00-025 (Falls, effective 1 May 2023);
CPL 03-00-026 (Warehousing, the 2026 version, effective 31 July 2026); CPL 02-00-161 (Trenching,
effective 1 October 2018, "in effect until canceled"); 29 CFR 1926.650 and 1926.800 as OSHA's site
reproduces them (eCFR did not load). "OSHA inspected" is the SIR file's own field: a reference,
not the truth. Nothing in the crew is changed. Each case separates what the sources settle
(confirmed) from what is a reading (judgment).

**20251111604, Dollar Tree, Inc., Abilene, 22 November 2025 (452112).**
* Evidence: "They went to step over a box, tripped on the box, and fell on the floor. The
  employee's ankle was fractured." OIICS 4312 (fall on the same level, slip or trip). The earlier
  report, 2025010815 ("Dollar Tree", Princeton, 25 January 2025, 301 days before, 452319): stocking
  shelves, a foot caught in an empty box, a fall; the same code, 4312. OSHA inspected neither.
* Rule that fired: employer history (a confirmed earlier report, same state, same OIICS division,
  within 365 days).
* Source: the memo, Category 1, item 3: "The employer has a history of the same or similar hazards
  or incidents within the past 12 months." It says "employer"; the part of the memo read defines
  neither employer nor establishment.
* Confirmed: the memo's words are met (the same employer, the same hazard of tripping on boxes
  while stocking, inside 12 months).
* Judgment: whether "employer" means a chain across the state. Read that way, any large chain's
  second trip in a year is Category 1.
* **Recommended: Category 1 under the rule as written. Keep it, and ask Kevin to settle company or
  establishment for the whole crew** (a policy choice, not a fix to this row). This is the
  criterion of #18, where B2 found OSHA inspected 20% of the holdout reports it marks.
* **Kevin (22 November):** keep the rule as written, so Dollar Tree stays Category 1; B2 and B3
  are scored on the current rule. The case is added to #18, decided with the B3 labels in the
  Advance stage.

**20251111619, United States Postal Service, Crystal City, 22 November 2025 (491110).**
* Evidence: "An employee was using a ladder to hang a display. While coming back down the ladder,
  she missed the last step and fell to the floor, fracturing her left knee." OIICS 4141, source
  portable ladders. The earlier report, 20241211946 (Mexia, 30 December 2024, 327 days before):
  "walking to deliver mail and fell into a grass-covered ditch", OIICS 4140, source ditches. OSHA
  inspected neither.
* Rules that fired: employer history (OIICS division 4) and the warehousing NEP (491110 is in its
  industry list in `emphasis_programs.toml`).
* Source: the warehousing NEP, Table 2: "Postal Service (Processing & Distribution Centers only)";
  XII.A: inspections "do not include postal or package transportation/delivery to residences and
  businesses"; XII.B: no NEP inspection if "The establishment is a post office location that is
  not a processing and distribution center."
* Confirmed: the NEP leaves out retail post offices and delivery routes; the two incidents differ
  in place, work and source.
* Judgment: that Crystal City is a retail post office and not a processing center (hanging a
  display points that way; the data cannot tell), and that a fall on a delivery route and a fall
  from a ladder indoors are not "similar".
* **Recommended: Category 2.** Neither trigger should force it. For the crew: 491110 should only
  raise the priority (`possible_emphasis_program`), not force Category 1, since the file cannot
  tell a processing center from a post office. Kevin opened this as #26 for the Advance stage;
  nothing changes now, and the call on this report is Hamad's.

**20251111445, Axis Power LLC, Edna, 17 November 2025 (237130).**
* Evidence: "standing on the bed of a crane truck working to pin the jib of the crane to the main
  boom so it could be stowed away. He fell off the bed of the truck approximately 5 feet to the
  ground". OIICS 4141 (fall to a lower level, under 6 feet), source truck-mounted crane. OSHA did
  not inspect.
* Rule that fired: the Falls NEP (a construction NAICS, 23, and a fall from or off something).
* Source: the Falls NEP, II.A: "All construction inspections related to falls will be conducted
  pursuant to this NEP." The directive sets no height; its purpose is falls "while working at
  heights in all industries".
* Confirmed: the employer is in construction, the injury is a fall to a lower level, and the NEP's
  construction scope has no height threshold (the 6 foot trigger is in the fall protection rule,
  1926.501, not in the NEP).
* Judgment: whether rigging a truck crane for the road is construction work, and whether 5 feet
  off a truck bed is "working at heights".
* **Recommended: Category 1, keep.** The NEP's scope reads on it. The weaker point is that no fall
  protection rule may be citable, which matters for the inspection, not for the category.

**20251111409, Everflow Plumbing, Heating & Air, Arlington, 17 November 2025 (238220).**
* Evidence: "using a hammer to break away old existing sewer pipe from underneath a building. A
  section of dirt/rock fell from the side of the underground tunnel wall onto the employee's legs.
  The employee sustained two broken legs." OIICS 632 (collapse or engulfment in an open trench or
  excavation), source 611 (ditches, channels, trenches, excavations). OSHA inspected it (inspection
  1859803).
* Rule: none forces it. The trenching NEP is `verified = false` (its scope was never read), so it
  only adds `possible_emphasis_program`, and its narrative triggers (`trench`, `excavat`,
  `cave in`) do not match "tunnel".
* Source: the trenching NEP, II: "All inspections of trenching and excavation operations will be
  reported pursuant to this NEP", with no depth or industry limit. 1926.650(b): an excavation is
  "any man-made cut, cavity, trench, or depression in an earth surface, formed by earth removal".
  1926.800(a) covers "underground tunnels, shafts, chambers, and passageways" and leaves out
  "Excavation and trenching operations covered by subpart P".
* Confirmed: the NEP covers every trenching and excavation operation; OSHA's own coding calls the
  event a collapse in a trench or excavation; the crew cannot force it.
* Judgment: whether a hand-dug tunnel under a slab is an excavation (Subpart P) or underground
  construction (Subpart S).
* **Recommended: Category 1; the crew misses it.** For the crew: read the NEP's scope into
  `emphasis_programs.toml` (`verified = true`, no industry limit) and let OIICS 632 or source 611
  trigger it, not only the narrative's words. Kevin opened this as #27 for the Advance stage;
  nothing changes now, and under B3's rule 6 it is not re-scored on the same 100.

**In sum:** of the 8 Category 1 reports, 7 stand (Dollar Tree on the memo's wording, which Kevin
keeps for now; #18), 1 should be Category 2 (USPS), and 1 Category 2 report should be Category 1
(20251111409). These are Hamad's calls to make; the two crew changes are #26 and #27 (Advance).
Both employer-history cases here (Dollar Tree and USPS) are evidence for #18; under its rules they
are not grounds to tune the criterion on this week.

### The app

* **Director moves, by their handlers** (`tests/test_app.py`, all passing): a row to inspection
  and back, a cleared note and a removed rule, an imminent danger flag set and removed, Approve
  with open employer matches (warned once, then approved), and each role opening on its page.
* **In a browser, at laptop and phone width: walked on 21 November.** Offline (`safereport.cli ui
  --port 7860`, no `--live`, $0), on the working tree of `hamad/b1-review` (code as on `fd15b06`
  plus the Arabic revision). Claude in Chrome connected, but the app's tab stopped responding
  (four timeouts, while a headless Chromium loaded the same page in 4.6 s with no console error), so
  the 15 steps were driven with Playwright and Chromium at 1440 x 900 and in an iPhone 12 Pro
  profile (390 x 844, touch). Screenshots are in `.local/b1/screenshots/`.

  | # | Step | Laptop | Phone | Seen |
  |---|---|---|---|---|
  | 1 | Load the Texas week, 40 days | PASS | PASS | 31 reports, 8 Category 1, 20 inspections, 11 letters, a reason on all 31 rows |
  | 2 | Open a row in the case inspector | PASS | PASS | highlighted narrative, the checks, 3 earlier reports, similar injuries, the letter |
  | 3 | Letter to inspection | PASS | PASS | "Plan updated with 1 changed rows"; 20251111443 is an inspection, 20251111622 drops to a letter for the days |
  | 4 | Back to a letter | PASS | PASS | 20251111443 is a letter again; both moves are listed under "What changed" |
  | 5 | Note, then clear it | PASS | | the reason reads "(note: B1 check note)", then the note is gone |
  | 6 | Always-inspect rule, then empty it | PASS | | 20251111436 C.A. Senecal goes to inspection ("rule: inspect every report from …") and back; a loose spelling (lower case, no commas, no Inc) matches too. See the note below |
  | 7 | Imminent danger on, then off | PASS | | 20251111554 becomes Category 1 "imminent danger", then goes back |
  | 8 | Approve with open matches | PASS | PASS | warning: 31 possible employer matches unanswered, a confirmed one can make a report Category 1 |
  | 9 | Approve again | PASS | | approved and logged; `inspection_list.csv`, `rri_letters.docx`, `week_summary.docx` in Downloads; a later Ask for changes is refused |
  | 10 | Category 1 row to a letter | PASS | PASS | refused by construction: none of the 8 Category 1 rows is offered in **Move to RRI letter**, and typing one finds nothing. The "must be inspected" message is reachable only from code (`tests/test_app.py`), since Note is the only editable column |
  | 11 | Ask, an example | PASS | | the answer (brief with 1910.147, similar injuries, questions) and the trace: agents, models, reasons, estimated cost, "nothing was paid". Clicking an example only fills the box; **Send** is a second click. A time shows only on steps that take 0.01 s or more (most offline steps show none) |
  | 12 | Lockout talk, Arabic | PASS | | yearly chart, state map, `safety_talk_lockout_en.docx` and `safety_talk_lockout_ar.docx`. **Defect** in the page preview, below |
  | 13 | Outage of Claude, ask again | PASS | | "3 of 4 models up; calls to Claude Sonnet 5.5 fail and fall back"; the trace shows `gemini_flash`, "fell back from claude", "fallback after claude failed (server_error)" |
  | 14 | Lift the outage | PASS | | "4 of 4 models up"; the same question routes to `claude` again |
  | 15 | Week CSV from Downloads | FAIL, then PASS after #21 | | the downloaded `inspection_list.csv` holds `\r\r\n` at all 32 line ends: 65 lines for 32 rows. Opened in Excel 16 (by automation): 63 rows, 31 of them blank, one after every row. Excel also shows the 11-digit report IDs as `2.03E+10`. Re-run on 22 November on `main` with #21 and this branch: 32 lines, each ending `\r\n`, none `\r\r\n`; Excel shows 32 rows, none blank |

  **At phone width:** no page scrolls sideways (document width 390); the role picker sits below
  the site name with no overlap; the week table (1,600 px wide), the triggers and the matches scroll
  sideways inside their frames; tabs past **Ask** move into a "…" menu; the Decide pickers and
  **Ask for changes** are full width. Small targets: the "Show" filter radios are 16 px (their labels
  are larger) and the Plotly toolbar icons are 24 x 22. Not walked at phone width: steps 5 to 7, 9
  and 15 (the walkthrough does not ask for them).

  **The other two roles at phone width** (390 x 844, a second pass the same day):

  | Role | Check | Result | Seen |
  |---|---|---|---|
  | Plant safety manager | opens on its page | PASS | **Trends and prevention** selected; no Approve, no AI controls |
  | Plant safety manager | Trends: tiles, chart, map, top events | PASS | 190 reports for Texas, Plastics, from 2019; three charts each 316 px wide inside the 390 px screen; nothing scrolls the page sideways |
  | Plant safety manager | filter and **Apply**, then **Download Selected Data** | PASS | All industries: 10,633 reports; `reports_texas_all_industries_all_events_2019.csv` offered |
  | Plant safety manager | lockout talk in Arabic, **Write the talk** | PASS, with the known defect | `safety_talk_lockout_ar.docx` and `safety_talk_lockout_en.docx`; the Arabic preview computes `direction: ltr` here too |
  | Plant safety manager | the week page is hidden | **FAIL**, fixed on main | the **This week's reports** tab stayed in the bar and opened a blank page (#24). On main after 04eb1f0 the tab is gone from the bar and from the phone's "…" menu (checked 22 November at 1440 x 900 and 390 x 844) |
  | Admin | opens on its page | PASS | **AI controls and evaluation** selected, the controls shown |
  | Admin | outage of Claude, **Apply**, ask on **Ask** (through the "…" menu) | PASS | "3 of 4 models up; calls to Claude Sonnet 5.5 fail and fall back"; the trace shows `gemini_flash`, "fell back from claude" |
  | Admin | lift it, **Apply**, ask again | PASS | "4 of 4 models up"; the trace routes to `claude` again |

  Also at phone width: the tab labels are cut off ("THIS WEEK'S RE", "AI CONTROLS AND EV",
  `phone_admin_01_controls.png`), and once the blank week tab was opened, the next tab read "ASK"
  under the Trends icon (`phone_psm_week_tab_clicked.png`). No console errors in either pass.
* **Limits of the walkthrough.** Driven by a script in Chromium, not by hand in Chrome; the phone
  run is Chromium's iPhone 12 Pro emulation, not a phone. The CSV and one Arabic Word file were
  opened in Excel 16 and Word 16 by automation (below), not read on screen by a person. All of it
  offline: the models' answers are the offline rules', and
  the routing is what the router would call.

**Defects (one issue each).**

* **CSV downloads on Windows have a blank line after every row** (#17, opened by Kevin; fixed
  by #21, merged on 22 November). The text already ends its lines with `\r\n` (`outputs.triage_csv` through the csv module,
  `DataFrame.to_csv()` through `os.linesep`), and `views.save` wrote it in text mode, so Windows
  added another `\r`: each line ended in `\r\r\n` and a reader saw 6 rows for 3. Confirmed in the
  browser: the downloaded `inspection_list.csv` has `\r\r\n` at all 32 line ends. It affects
  `inspection_list.csv`, the week table download and the Trends export. Two tests failed on
  Windows only (`test_the_week_states_its_active_filters_and_downloads_what_it_shows`,
  `test_trends_show_the_dashboard_figures_and_export_the_selection`). #21 writes with
  `newline=""` and adds a test; on Windows it gave 301 passed, 7 skipped, and #17 is closed.
* **The Arabic safety talk shows left to right on the Trends page** (#22). With Arabic
  as the extra language, the Arabic text shows with the bullets on the left, the lines aligned
  left and each sentence's full stop at the start of the line, at laptop and phone width
  (`laptop_s12_arabic_talk_ltr_defect.png`; the page computes `direction: ltr`). The English and
  the Arabic come back as one Markdown string (`views.safety_talk`), and nothing in `app.py` or
  `views.py` sets a direction. **Fixed on main (04eb1f0)**: the Arabic talk is in a right to left
  block; checked on 22 November, the Arabic paragraphs compute `direction: rtl`
  (`mainb1_laptop_arabic_preview.png`).
* **The Arabic Word file is aligned to the left in Microsoft Word** (#23). Opened in Word
  16 (`safety_talk_lockout_ar.docx`, exported by the app after the Arabic revision), every
  paragraph reads right to left (Word reports reading order right to left for all 7), but the
  lines start at the left margin: the title sits on the left, the right edge is ragged and the
  bullets do not line up (`word_arabic_talk_as_exported_left_aligned.png`, from Word's own PDF
  export). The cause is `outputs._script` (`outputs.py:149`): it sets
  `WD_ALIGN_PARAGRAPH.RIGHT` (`w:jc="right"`) on a paragraph marked `w:bidi`, and for a right to
  left paragraph Word reads that as the end side, which is the left. The same file with the
  `w:jc` element removed renders correctly, on the right with the bullets aligned
  (`word_arabic_talk_without_jc_right_aligned.png`); putting `w:bidi` before `w:jc` (the schema
  order) changes nothing. **Fixed on main (04eb1f0)**: no `w:jc` on the Arabic paragraphs and
  `w:bidi` in schema order, with a test. Checked on 22 November on the file the app exports from
  main with this branch's Arabic: Word 16 reads all 7 paragraphs right to left and lays them out
  from the right margin, with the bullets aligned on the right
  (`word_arabic_talk_on_main_with_b1.png`).
* **The Plant safety manager keeps a blank "This week's reports" tab** (#24). Signed in as
  Plant safety manager, the tab is still in the bar at laptop and phone width; opening it shows
  only the footer (`laptop_psm_week_tab_clicked.png`, `phone_psm_week_tab_clicked.png`). The week's
  content stays hidden, so nothing leaks, but the role sees a dead tab. `role_view` returns
  `gr.Tab(visible=False)` for that role and `tests/test_app.py` checks that return value; in
  Gradio 6.31 the tab's panel is hidden but not its button. **Fixed on main (04eb1f0)** with
  `visible="hidden"`; checked on 22 November: no week tab for the Plant safety manager at laptop
  or phone width (`mainb1_laptop_psm_tabs.png`, `mainb1_phone_psm_tabs.png`).

**For Kevin: a row choice beats a later rule.** *Answered on #25: intended, and the status now
says so (main, 71d6648), for example "The employer rule leaves 1 row you set to a letter by hand:
20251111443. Move them to inspection to apply the rule."* The finding as it was: After a row was sent
back to a letter by hand (step 4, 20251111443 Steel Dynamics), an always-inspect rule for the same
employer left it a letter, while the status said "Plan updated with 0 changed rows and a rule for
Steel Dynamics - Southwest - Sinton Division. No row changed." (`laptop_s6_rule.png`). The person's
explicit choice winning is defensible. Is this the intended order, and should the status say that
the rule did not apply to that row?

**For Khoa: a letter cites a standard its own check doubts.** Report **20251111443**, Steel
Dynamics - Southwest - Sinton Division, Sinton, 17 November 2025, now an RRI letter, Standard
column `1910.28`. The narrative: "A large piece of metal scale fell 7 feet off the caster, striking
the employee's left foot and causing a compound fracture" (the employee was disconnecting hoses
while a crane lifted the caster segment; OIICS 6439, confidence 0.88). The case inspector's check
says "check: 1910.28 is about falls, but the worker was hurt by crane load", yet the letter as it
will be sent says "The hazard appears to fall under 1910.28" (`laptop_s2_case_inspector.png`,
offline rules). 1910.28 is fall protection, and the worker did not fall. Should the letter drop or
replace the standard when the check flags it, and is 1910.179 (cranes) or 1910.184 (slings) the
better citation? *Kevin handed this to Khoa's B5 (#6): when the case inspector's check flags a
standard, the letter should not state it as the likely one.*

**Recommendation: make the English lockout step as clear as the Arabic.** *Done by Kevin on main
(71d6648) with the wording below; the other translations keep the old line until their native
speaker review.* The English talk says "Try to start the machine before you reach in, then return
the control to off". Its place after the lock and tag step implies the try-out, but read alone it
could mean starting the machine before reaching in. The Arabic now says it in full: after every
energy source is isolated and locked, stay clear of the hazardous parts, try the normal controls
to confirm the machine does not start, then return them to off. Suggested English: "With every
lock on, stand clear and try the normal start controls to make sure the machine does not start,
then return them to off." The other languages translate the English line, so they would follow.

**Minor UI finding.** The Downloads page says the same sentence twice: "The week's list as CSV;
the brief, the letters and the talks as Word files" in the intro (with ", as you make them") and
again in the note under it.

### Arabic safety talks

* **Word files:** all four topics export; every Arabic paragraph is marked right to left
  (`w:bidi`), with Arabic runs (`w:rtl`, Arial for complex script) and no stray Latin text.
  **Checked in Microsoft Word 16 by automation.** On 21 November the lockout file opened without
  a repair prompt, as one page, read right to left, but laid out from the left margin (#23). On
  22 November, with #23 fixed on main (04eb1f0) and this branch's Arabic merged in for the check,
  the app's `safety_talk_lockout_ar.docx` has `w:bidi` on all 7 paragraphs and no `w:jc`, holds
  the revised text, opens in Word as one page, and Word lays every paragraph out from the right
  margin with the bullets aligned (`word_arabic_talk_on_main_with_b1.png`, from Word's own PDF
  export). **Still for Hamad:** read the file on screen as a native speaker; nothing here is that
  reading.
* **The text: corrected.** Hamad reviewed all 26 lines (the lead and four topics) against the
  English, with an AI assistant's draft and questions, and decided each change. All 26 Arabic
  strings in `src/safereport/talk_languages.py` were revised; the English, the other languages,
  the placeholders (`{{topic_reports}}`, `{{since}}`) and the structure are unchanged. The main
  corrections:
  * **Lockout:** the title names isolating and locking («اعزل الطاقة وأقفلها قبل أن تمد يدك»,
    with the hamza of أقفل); "isolate" (اعزل) replaces "disconnect"; stored spring energy is
    «الطاقة المخزّنة في النوابض». **Safety meaning:** the old step «حاول تشغيل الآلة قبل أن تمد
    يدك» could read as "start the machine before you reach in". It now says that, after every
    energy source is isolated and locked, the worker stays clear of the hazardous parts and tries
    the normal controls to confirm the machine does not start, then returns them to off.
  * **Machine guarding:** «حواجز الحماية» for guards; «رد الفعل» replaces the calque «يتفاعل»;
    the case endings of «منزوعًا، مثنيًا، معطَّلًا» are fixed.
  * **Falls:** the title is «كل حافة غير محمية قد تشكّل خطرًا للسقوط»; a mezzanine is
    «طابق نصفي (ميزانين)», not an upper floor; a fall-protection harness is «حزام الجسم الكامل
    للحماية من السقوط» and a lift «منصة العمل المرتفعة», where «الحزام» and «الرافعة» could be read
    as a belt and a crane.
  * **Forklifts:** «المشغّلون الذين أتمّوا التدريب واجتازوا التقييم» for trained and evaluated
    operators (the old «المقيَّمون» read as «المقيمون», residents, without its diacritics);
    «المشاة» for people on foot.
  * **Lead:** «منذ عام {{since}}، أبلغت مصانع مماثلة لمصنعكم عن إصابات خطيرة من هذا النوع، وبلغ
    إجمالي عدد الإصابات {{topic_reports}}.» The old lead put the count before a singular noun
    («{{topic_reports}} إصابة»), which is wrong Arabic for a count ending in 03 to 10, such as 10
    (the smallest count the app shows) or 105. The count now ends the sentence on its own, so it
    reads correctly for any number; checked with 10, 105 and 2,183.
* **Checks:** the strings are stored in logical Unicode order (no bidi control characters or
  presentation forms, NFC normalized), no digit appears outside a placeholder, the placeholders
  render through the FactLedger, and the four Word files exported by the app hold the new text
  with every Arabic paragraph marked right to left. `tests/test_writer.py` (55) and the app's and
  graph's talk tests pass.

### The weights and inspector days in `config/triage.toml`: proposals for Khoa

Nothing is changed: the plan asks Hamad and Khoa to agree the values together. The evidence
below is how often OSHA inspected reports with each factor in 2015 to 2024 (97,284 reports,
33.8% inspected); the 2025 holdout that B2 scores is not read. Past practice is a reference, not
the truth, so it informs the weights rather than setting them.

| Factor | Weight now | Reports | Inspected (95%) | Adjusted log-odds | Reading |
|---|---|---|---|---|---|
| failed safeguard (narrative) | 2.0 | 882 | 78.5% (75.6 to 81.0) | 1.75 | strongest factor, weighted below amputation |
| amputation | 3.0 | 25,790 | 48.4% (47.8 to 49.0) | 1.22 | supported |
| fatality potential (offline rule) | 2.0 | 21,345 | 46.2% (45.6 to 46.9) | 0.81 | supported |
| temporary worker (narrative) | 1.5 | 945 | 51.0% (47.8 to 54.2) | 0.65 | supported; also a factor in the memo's Category 2 list |
| hospitalized, per person (at most two) | 2.0 | 78,134 with one | 30.6% (30.3 to 30.9) | 0.41 | one person hospitalized is inspected less than average, yet adds 2 points |
| loss of an eye | 3.0 | 31 | 48.4% (32.0 to 65.2) | 0.13 | too few reports to tell; the weight rests on severity |

Not measured here: `specific_standard`, `common_in_industry` and `possible_emphasis_program`
need a retrieval run per report.

**What the sources say.** The memo's Category 2 list (section 5) is what the weights stand for.
It names a failed safety program (confined spaces, lockout, process safety management and the
like), a serious hazard ("such as
explosive materials, combustible dust or falls"), temporary or other vulnerable workers, and a
health hazard; it adds "This list is not intended to be exhaustive." Amputation, loss of an eye
and hospitalization are not on that list: they are what 29 CFR 1904.39 makes an employer report,
so in the crew they stand for severity, a reasonable addition the memo allows but does not
weigh. No source gives numbers for any weight, and none gives how long an inspection takes.

**Kevin (22 November): keep the values, so B2 stays valid; write the reason beside each one,
comments only.** Done in its own pull request (branch `hamad/b1-weight-reasons`): every value in
`config/triage.toml` has its reason and evidence beside it, the parsed values are identical, and
B2's command rerun on that branch reproduces every number and the per-report CSV. The proposals
below stay as future work; a change needs Hamad and Khoa to agree, its own pull request and a B2
rerun.

**Proposal for Khoa and Kevin (future work):**

| Value | Now | Proposed | Why |
|---|---|---|---|
| `failed_safeguard` | 2.0 | **3.0** | the memo's safety program failure; the strongest factor in 2015 to 2024 (78.5% inspected, adjusted log-odds 1.75), yet weighted below amputation |
| `amputation` | 3.0 | 3.0 | severity under 1904.39; supported (48.4%, 1.22) |
| `loss_of_eye` | 3.0 | 3.0 | severity; only 31 reports, so the data cannot support or refute it; say so in the file |
| `hospitalized` (per person, at most two) | 2.0 | **1.0** | one hospitalization is inspected less than average (30.6% against 33.8%), and two or more is already Category 1, so the per person weight mostly adds 2 points to an ordinary report |
| `fatality_potential` | 2.0 | 2.0 | the memo's serious hazard; supported (46.2%, 0.81) |
| `temporary_worker` | 1.5 | 1.5 | named in the memo; supported (51.0%, 0.65) |
| `specific_standard`, `common_in_industry`, `possible_emphasis_program` | 1.0 each | 1.0 | not measured (each needs a retrieval run per report); keep, and say they are unmeasured |
| `[inspection_days]` and `default_capacity` | as now | as now | no source and no data in the repository give inspection lengths or an office's week (that needs OSHA's inspection records); keep them as stated assumptions, with that reason written in the file |

**If the weights change:** B2 (`scripts/eval_inspection_auc.py`) must be rerun and say so, and
the change must not be chosen by looking at B2's AUC on the holdout. B4's decisions may also
move. The analysis is `.local/b1/weights_evidence.py` on Hamad's machine (it can be added to
`scripts/` if the team wants it in the repository).
