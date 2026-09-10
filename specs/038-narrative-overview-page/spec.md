# Feature Specification: Narrative Overview Page

**Feature Branch**: `038-narrative-overview-page`

**Created**: 2026-09-10

**Status**: Draft

**Input**: User description: "The generated wiki's Overview page is a manifest, not an explanation. Today it shows the repository root, detected languages, last-indexed date and commit; one sentence of counts ("48 documented modules, 35 classes, 83 top-level functions"); a feature-to-module-count table; a repository-wide class diagram; a bullet per feature; and a bullet per module. A reader finishes it knowing the repository's dimensions and none of its ideas — not what the project does, not how a request travels through it, not which module to open first, not why the code is arranged the way it is. Change what the Overview page says. It should read like the overview pages produced by DeepWiki and Google Code Wiki: several paragraphs of explanation first, structure second, every claim anchored to a source file or symbol that actually exists in the analysed repository, and each paragraph routing the reader onward to the feature and module pages the wiki already generates. Declarative present tense. No marketing adjectives, no second person. Slice it into independently shippable user stories, roughly in this order of value, and say in each why it stands alone: P1 — The narrative lead. Two to four paragraphs at the top of the Overview: what this repository is and does in its own terms, the major subsystems named inline with links to their pages, and how the pieces fit together — where work enters the system and where it ends up. Shipping only this already transforms the page. P2 — The subsystems section. Replace the feature/count table with a real one (subsystem, responsibility, entry point or key module), followed by a short paragraph per major subsystem, each ending in a link to its page. P3 — A "getting started" section: how the analysed project is built, run and tested, derived only from real evidence in that repository. It must not render at all when the evidence doesn't support it. P4 — Module-list hygiene, which needs no AI at all and is independently visible: every module row with no description currently ends in a stray "(" floating at the right edge; roughly eight rows all read "`__init__`" with nothing to tell them apart; and a README row dumps raw Markdown, heading hash included, cut off mid-sentence. Three behaviours are requirements, not implementation preferences, because a reader and a tester can both observe them directly: With no AI provider configured, unreachable, refusing the call, or returning something unparseable, the Overview page must still build and must navigate identically. Only the prose is missing. Never a crash, never a half-built page, never a different structure. The page must never name a file, module or symbol that does not exist in the analysed repository. A shorter true page beats a longer plausible one. Model-written text must be visibly marked as generated, as it already is elsewhere in this wiki. Re-running the analysis on an unchanged repository must produce an identical Overview page. Success criteria should be about the reader and be technology-agnostic — for example, that someone who has never seen the repository can name its main subsystems and say where an operation begins after reading only this page; that every path or symbol named in the prose resolves to something real; that the no-provider page has the same navigation as the with-provider one. Do not put file paths, module names, model names or token counts in the spec; those belong in the plan."

## Clarifications

### Session 2026-09-10

- Q: Which parts of the Overview page does an AI model write, and which are
  filled in directly from the analysis? → A: Prose only. The narrative lead and
  the per-subsystem paragraphs are generated; every fact — repository details,
  counts, the subsystems table (its responsibility column taken from each
  subsystem's existing description), the module list and every link — comes
  straight from the analysis, never from a model answer produced for this page.
- Q: When no provider is available, what does a reader see where the prose would
  have been? → A: Nothing at all. The prose blocks are simply absent — no
  placeholder, no apology, no "AI unavailable" banner — with the same headings,
  links and navigation; the omission is reported only in the analysis's own
  progress output.
- Q: What happens to the repository-wide class diagram that renders inline as
  thirty-odd illegible boxes? → A: Reduce it to its existing link. It no longer
  renders inline on the Overview; the "View the repository class diagram" link
  stays and leads to its own zoomable page.
- Q: Is the "getting started" section part of the first release? → A: No. User
  Story 3 stays in the spec as the bar a later release must meet, but the first
  release covers User Stories 1, 2 and 4 only.
- Q: How long may the generated prose be before it stops being an overview? →
  A: Hard caps. The lead is at most four paragraphs; each major subsystem gets
  at most one paragraph of up to three sentences; at most eight subsystems get
  a paragraph (the table still lists all of them); all generated prose on the
  page together stays under 600 words.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Read what the repository is before reading what it contains (Priority: P1)

Someone opens the documentation of a repository they have never seen. Today the
first thing they meet is a list of facts about the checkout — where it lives on
disk, which languages were detected, when it was analysed — followed by a
sentence of counts and a table of how many modules each part of the code has.
They finish the page knowing how big the repository is and nothing about what it
does. To learn that, they have to guess which of dozens of pages to open first.

With this story, the page opens with two to four paragraphs of explanation. The
first says what the repository is and does, in the repository's own terms. The
following ones name its major subsystems inline, each name a link to the page the
wiki already publishes for it, and describe how the pieces fit together: where
work enters the system, what it passes through, and where it ends up. Every fact
the page showed before is still reachable below the explanation. Three things
leave it:

- the inline class diagram, which keeps its link (FR-003b);
- the analysis timestamp, which the page footer already carries (FR-003);
- the unmarked, model-written subsystem descriptions in the subsystem list,
  which remain on each subsystem's own page (FR-012a).

Every file, module and symbol the paragraphs name exists in the analysed
repository. Where the system cannot say something truthfully, it says less. The
paragraphs are visibly marked as generated, the same way generated text is
marked everywhere else in the wiki.

**Why this priority**: It is the whole difference between a manifest and an
overview. It needs nothing else in this specification. It adds a block above the
existing page and, below it, only removes what is illegible, run-specific or
unmarked. So it ships alone and still changes what a first-time reader takes
away.

**Independent Test**: Analyse a repository with an AI provider available and
open its Overview page. Two to four marked paragraphs precede everything else on
the page. They describe the repository's purpose and flow, and link to its
subsystem pages. Every name they mention can be found in the repository. The
remainder of the page keeps every fact it showed before the story shipped, and
carries no unmarked generated text.

**Acceptance Scenarios**:

1. **Given** an analysed repository and an available AI provider, **When** the
   reader opens the Overview page, **Then** between one and four paragraphs of
   explanation appear directly beneath the page title, before any list, table or
   diagram. Two to four are asked for (FR-005). A single paragraph on a
   repository with at least two subsystems, with none rejected, is a review
   finding (SC-007), not a failure of this scenario.
2. **Given** the narrative lead, **When** the reader reads its first paragraph,
   **Then** it states what the repository is and what it does, without relying
   on counts of modules, classes or functions to say it.
3. **Given** the narrative lead, **When** the reader looks for the repository's
   major subsystems, **Then** each one the lead mentions is named inline and
   linked to its existing page in the wiki.
4. **Given** the narrative lead, **When** the reader looks for how work moves
   through the repository, **Then** the lead identifies where work enters the
   system and where its results end up, naming the real file, module or symbol
   at each end.
5. **Given** any paragraph of the lead, **When** the reader reaches its end,
   **Then** it contains at least one link onward to a subsystem or module page
   that exists in the wiki.
6. **Given** any file, module or symbol named in the lead, **When** a tester
   looks for it in the analysed repository, **Then** it exists there.
7. **Given** the narrative lead, **When** the reader views it, **Then** it is
   visibly marked as generated, the same way generated text is marked on the
   wiki's other pages.
8. **Given** no AI provider is configured, or every configured provider is
   unreachable, refuses the request, or returns something the system cannot
   use, **When** the analysis runs, **Then** it completes and the Overview page
   is produced with the same headings, links and navigation as it would have
   with a provider. The only difference is that the explanatory paragraphs are
   missing.
9. **Given** a repository analysed once, **When** it is analysed again with no
   change to its contents and the same providers available, **Then** the
   Overview page's content is identical to the one produced the first time.
10. **Given** a repository whose Overview has a narrative, **When** the
    repository changes and is analysed again while no provider can answer,
    **Then** the earlier narrative appears, minus every paragraph that now names
    something absent. It is marked as describing an earlier version of the
    repository, and the analysis output says the narrative is from an earlier
    version.

---

### User Story 2 - See the subsystems as a map, not a tally (Priority: P2)

Having read the lead, the reader wants the repository's parts laid out side by
side. Today the Overview gives them a table pairing each subsystem with a number
of modules. That number says how big a subsystem is, not what it is for or where
to start reading it.

The table is replaced by one that answers those questions. It has one row per
subsystem, with three columns: the subsystem's name, linked to its page; what it
is responsible for; and the entry point or key module to open first, linked to
that module's page. Beneath the table, each major subsystem gets a short
paragraph that says what it does and how it relates to its neighbours, and ends
with a link to its page.

**Why this priority**: It is the second-largest gain after the lead and builds
on the same grounding rules. The lead is not a prerequisite for it. The table's
structure is derived entirely from the analysis, so it can ship on a page that
has no lead, and a reader of the table gains a starting point in every subsystem
either way.

**Independent Test**: Open the Overview of an analysed repository. Where the
count table used to be, a table appears with a responsibility and a linked
starting module for every subsystem. It is followed by one marked paragraph per
major subsystem, each ending in a working link to that subsystem's page.

**Acceptance Scenarios**:

1. **Given** an analysed repository, **When** the reader opens the Overview,
   **Then** the table pairing subsystems with module counts is gone, and a table
   with columns for subsystem, responsibility and entry point or key module is in
   its place.
2. **Given** the subsystems table, **When** the reader looks down it, **Then**
   every subsystem the wiki publishes a page for appears in it exactly once, in
   the same order the wiki's navigation lists them.
3. **Given** a row in the subsystems table, **When** the reader follows the
   subsystem link or the entry-point link, **Then** each leads to a page that
   exists in the wiki, and the entry-point module belongs to that subsystem.
4. **Given** the paragraphs beneath the table, **When** the reader reaches the
   end of each, **Then** it ends in a link to the page of the subsystem it
   describes.
5. **Given** no AI provider is available, **When** the Overview is produced,
   **Then** the table still appears with every row, every link and every column.
   Only the per-subsystem paragraphs are missing.

---

### User Story 3 - Learn how to build, run and test the project (Priority: P3)

*Deferred: not part of the first release (see Clarifications). Specified here so
a later release has a fixed bar to meet.*

A reader who now understands what the repository does wants to try it. The
Overview gains a "getting started" section that says how the analysed project is
built, run and tested. Every instruction in it comes from evidence in that
repository, such as a declared script, a build definition or the repository's
own documentation, and the section names the file each instruction comes from.
Where the repository gives no such evidence, the section does not appear at all.

**Why this priority**: Useful but not essential to understanding. It is also the
slice most at risk of stating something plausible and wrong, because build and
run instructions are exactly what a reader will try to execute. It stands alone:
it is a self-contained section that depends on neither the lead nor the
subsystems section, and removing it leaves the rest of the page unchanged.

**Independent Test**: Analyse a repository that declares how it is built, run
and tested, and confirm that a "getting started" section appears with those
instructions and the files that declare them. Analyse a repository that declares
none, and confirm the section is entirely absent, including its heading.

**Acceptance Scenarios**:

1. **Given** a repository whose own files declare how to build, run or test it,
   **When** the reader opens the Overview, **Then** a "getting started" section
   gives those instructions, each attributed to the file that declares it.
2. **Given** an instruction shown in the section, **When** a tester looks in the
   attributed file, **Then** the instruction is found there as shown.
3. **Given** a repository that declares how to test it but not how to run it,
   **When** the Overview is produced, **Then** the section shows only what the
   evidence supports and does not guess at the rest.
4. **Given** a repository with no evidence of how it is built, run or tested,
   **When** the Overview is produced, **Then** no "getting started" heading or
   section appears, and no placeholder stands in for it.

---

### User Story 4 - A module list that can be read (Priority: P4)

Below the explanation, the Overview lists every module. Three defects make that
list harder to read than it should be, and none of them involve AI at all. First,
every row without a description ends in a stray opening parenthesis pushed to the
right-hand edge. Second, several rows share an identical label, so nothing
distinguishes them without following each link. Third, a row whose description
comes from a documentation file shows that file's raw markup, heading markers
included, cut off partway through a sentence.

After this story, every row reads cleanly. There is no stray punctuation. Every
label differs from every other label on the list. Every description reads as
plain text and either ends at a sentence boundary or is visibly marked as
shortened. Each row still links to its module page and to its dependency view.

**Why this priority**: Least valuable of the four, but the cheapest to get right
and the most certain. It is visible on every repository, needs no AI provider,
and depends on nothing else in this specification, so it can ship first, last,
or on its own even if the narrative design changes.

**Independent Test**: Analyse a repository that has modules with no
description, several modules sharing a file name, and a documentation file with
headings. Open the Overview and confirm the module list shows no stray
punctuation, no two identical labels, and no raw markup. Confirm also that every
row still reaches both its module page and its dependency view.

**Acceptance Scenarios**:

1. **Given** a module with no description, **When** its row is shown, **Then** it
   contains no unmatched or orphaned punctuation, and nothing floats detached at
   the row's edge.
2. **Given** several modules that share a file name, **When** the list is shown,
   **Then** each of their rows carries a label distinguishing it from the others,
   without the reader having to follow a link to tell them apart.
3. **Given** a module whose description comes from a documentation file, **When**
   its row is shown, **Then** the description contains no raw markup characters
   such as heading markers, emphasis markers or escaped punctuation.
4. **Given** a description too long for its row, **When** it is shown, **Then**
   it ends at a sentence or word boundary with a visible indication that it has
   been shortened, never mid-word.
5. **Given** any module row, **When** the reader wants its dependencies, **Then**
   the row still offers a working link to that module's dependency view.
6. **Given** no AI provider is available, **When** the Overview is produced,
   **Then** the module list meets every scenario above.

---

### Edge Cases

- **The provider answers, but some of what it wrote names things that do not
  exist.** The prose that names them is not published. Accurate prose from the
  same answer may still appear. The exception is the lead's opening paragraph:
  when it is the one withheld, the whole lead goes with it (FR-010a), while
  accurate subsystem paragraphs still appear. If nothing accurate remains, the
  page appears exactly as it would with no provider.
- **Some major subsystems get a paragraph and others do not**, because
  grounding withheld some. The subsystems that keep a paragraph appear in table
  order. The others simply have none: no placeholder, and still a row in the
  table (FR-025a).
- **The repository has changed since its last narrative, and no provider can
  write a new one.** The most recent narrative is shown again, re-checked
  against the repository as it is now, with every paragraph that no longer
  passes removed. It is marked as describing an earlier version, the same way
  the wiki marks a stale summary (FR-017a). A repository that has never had a
  narrative has no prose (FR-014).
- **The provider's answer would change the page's structure.** For example, it
  contains its own headings, tables, raw page markup, or links to pages that do
  not exist. None of that reaches the page. Generated text can never add a
  heading, remove one, or alter the page's outline or navigation.
- **The provider's answer breaks the house style.** It addresses the reader
  directly, uses promotional adjectives, or is written in another tense. It does
  not appear as written.
- **The repository has no description of itself** (no top-level documentation
  file introducing it). The lead describes what the repository does from its code alone, or is omitted if
  it cannot. The system never invents a purpose.
- **The repository describes itself inaccurately**, for instance its own
  documentation describes features the code does not contain. The lead names only files,
  modules and symbols that exist. It does not repeat claims about things that are
  absent from the code.
- **The repository has a single subsystem, or only a handful of modules.** The
  lead does not pad itself to reach a paragraph count. It says what there is to
  say, down to a single paragraph if that is all the evidence supports.
- **The repository has many subsystems.** The lead names the major ones, at most
  eight get their own paragraph, and the table lists them all. A large
  repository never pushes the generated prose past its length limits (FR-005a,
  FR-025), and never makes its production cost grow without bound.
- **The wiki has no subsystems at all**, for instance because none were derived.
  There is too little structure to narrate, so the Overview has no lead. It
  still builds, with every fact and module listed as usual, and the analysis
  output says the narrative was skipped.
- **The repository changes between analyses and something the prose named is
  removed or renamed.** After the update the Overview no longer names it, and
  every name the prose mentions still exists.
- **The repository changes in a way that does not affect anything the narrative
  describes.** The Overview may stay as it was. An unchanged repository must
  produce an identical page (FR-015).
- **The documentation of an already-analysed, unchanged repository is opened
  again.** The reader sees the same Overview the analysis produced. Opening the
  documentation does not quietly rewrite it.
- **A provider switch happens mid-analysis, or the narrative is skipped because
  no provider can produce it.** The analysis says so in its normal progress
  output. It is never silent, and it is never reported on the page itself.
- **Evidence for "getting started" conflicts**, for instance two different
  declared test commands. Either both are shown with their sources, or the
  conflicting part is omitted. The section never picks one silently and states
  it as fact.
- **The subsystem grouping differs between a run with a provider and a run
  without one.** The wiki's existing grouping already names subsystems more
  plainly, and can merge them differently, when no provider is available. The
  Overview inherits that difference and does not add to it: for a given grouping,
  its link destinations, headings and row order are the same whether or not its
  own prose could be written.

## Requirements *(mandatory)*

### Functional Requirements

#### Page shape and identity

- **FR-001**: The Overview page MUST present explanation before structure: when
  present, the narrative lead MUST appear directly beneath the page title and
  ahead of every list, table and diagram on the page.
- **FR-002**: The Overview page MUST keep its current address and its role as
  the wiki's landing page. Existing links to it, search results pointing at it,
  and cross-references into it MUST keep working.
- **FR-003**: All factual content the page shows today MUST remain reachable
  from it. That covers the repository's location, detected languages and
  analysed revision, the counts, every subsystem, every module, and the links to
  the repository-wide diagrams. It may be relocated or reformatted, but it MUST
  NOT be dropped. The time the analysis ran is a fact about the run, not about
  the repository. It is carried by the generation stamp every wiki page's footer
  already shows, not repeated in the Overview's content (see FR-015).
- **FR-003a**: The narrative lead (FR-005) and the per-subsystem paragraphs
  (FR-025) MUST be the only content on the Overview written by an AI model for
  this page. Everything else on it — repository facts, counts, the subsystems
  table, the getting-started section, diagram links, the module list and every
  link — MUST be derived directly from the analysis, never from a model's answer
  produced for the Overview.
- **FR-003b**: The repository-wide class diagram MUST NOT render inline on the
  Overview. The Overview MUST keep its existing link to the class diagram's own
  page, and its existing link to the repository-wide use-case diagram, whether
  or not an AI provider is available.
- **FR-004**: Generated text MUST NOT be able to add, remove or reorder the
  page's headings, or otherwise alter its outline, its navigation, or its links
  outside the generated text itself.

#### The narrative lead (User Story 1)

- **FR-005**: When an AI provider is available and the evidence supports it, the
  Overview MUST open with a narrative lead of one to four paragraphs. It MUST
  state what the repository is and does, name its major subsystems inline, and
  describe how work enters the system and where its results end up. Two to four
  paragraphs are asked for. Fewer than two MAY be published only when the
  repository offers too little evidence for more (a single subsystem, or a
  handful of modules), or when grounding rejected paragraphs (FR-010). The lead
  is never padded to reach a count.
- **FR-005a**: All generated prose on the Overview, the lead and the
  per-subsystem paragraphs together, MUST stay under 600 words. Prose that would
  exceed a length limit in this specification MUST NOT be published as written.
- **FR-006**: Each subsystem named in the lead MUST be linked to the page the
  wiki already publishes for that subsystem.
- **FR-007**: Every paragraph of generated prose, in the lead and in the
  subsystems section, MUST cite by name at least one file, module or symbol of
  the analysed repository that satisfies FR-009, so that each paragraph can be
  traced to the source that justifies it (constitution §2.4). A link to a
  subsystem page alone does not satisfy this. Every lead paragraph MUST also
  contain at least one link onward to a subsystem or module page that exists in
  the wiki; a cited module or symbol that renders as a link satisfies both.
- **FR-008**: The lead MUST use the subsystem grouping the wiki's navigation
  already uses. It MUST NOT introduce, rename or merge subsystems in a way that
  contradicts the wiki's own pages.

#### Grounding and marking (all generated text)

- **FR-009**: Generated text on the Overview MUST name only files, modules and
  symbols that exist in the analysed repository at the analysed revision.
  "Generated text on the Overview" means the narrative written for this page
  **and** any model-written text carried onto it from elsewhere in the wiki,
  such as subsystem descriptions. FR-009 to FR-013 apply to both.
- **FR-010**: Generated text that fails FR-009 MUST NOT be published. The system
  MUST prefer omitting it, so the page is shorter, over publishing an unverified
  claim.
- **FR-010a**: The lead's opening paragraph, the one saying what the repository
  is and does, carries the paragraphs after it. If it is not published, the
  whole lead MUST be withheld, rather than published starting mid-explanation.
  Any later lead paragraph that is not published MUST be dropped on its own. The
  paragraphs that remain keep their original order.
- **FR-011**: Every link inside generated text MUST lead to a page that exists in
  the wiki.
- **FR-012**: Every piece of generated text on the Overview MUST be visibly
  marked as generated, using the same marking the wiki already applies to
  generated text on its other pages, and the marking MUST be legible in both
  light and dark appearance. Where generated text sits in a table cell, which
  cannot carry that marking, the column's heading MUST say the column is
  generated.
- **FR-012a**: Generated text MUST NOT appear on the Overview anywhere it cannot
  be marked under FR-012. In particular, the Overview's list of subsystems MUST
  show subsystem titles only. Model-written subsystem descriptions appear on the
  Overview only in the subsystems table's labelled column (FR-021), and remain
  in full on each subsystem's own page.
- **FR-013**: Generated text MUST be written in declarative present tense, MUST
  NOT address the reader in the second person, and MUST NOT use promotional or
  evaluative adjectives (for example "powerful", "robust", "seamless",
  "modern"). Text that addresses the reader or uses a banned term MUST NOT be
  published. Tense cannot be checked mechanically with any reliability, so
  present tense is required of the generator and verified by the sentence-level
  human review in SC-013, not by an automatic filter.

#### Degradation and determinism

- **FR-014**: The Overview page MUST be produced successfully, complete and with
  identical structure, in each of these cases: no AI provider is configured; every
  configured provider is unreachable; a provider refuses the request; or a
  provider returns output the system cannot use. In every case the page MUST
  have the same headings, the same link destinations outside generated text, and
  the same navigation as a page produced with a working provider. Only the
  generated prose may be absent, and nothing MUST stand in its place: no
  placeholder, notice, apology or banner, and no empty container left visible.
  The one exception is FR-017a: an earlier narrative, re-checked and shown with
  its earlier-version marker. The marker qualifies prose that is present; it
  never stands in for prose that is absent, and it adds no heading and no link.
  A repository whose unchanged state was already narrated keeps that narrative
  with no provider at all (FR-015, FR-016). The prose is absent only when no
  narrative has ever been produced for the repository, or when none of the
  earlier one survives the re-check (FR-017a).
  The comparison holds the wiki's subsystem grouping
  fixed. That grouping comes from an earlier stage, which already names, and
  may merge, subsystems differently when no provider is available. This feature
  MUST NOT add to that variation. The analysis MUST NOT fail, and MUST NOT publish a
  partially built page, because of the narrative.
- **FR-015**: Analysing a repository whose contents have not changed since its
  last analysis, with the same providers available, MUST produce an Overview
  page whose content is identical, byte for byte, to the previous one. The only
  permitted difference is the generation timestamp in the footer that every wiki
  page shares.
- **FR-016**: Opening the documentation of an already-analysed repository whose
  contents have not changed MUST show the same Overview page that the analysis
  produced.
- **FR-017**: After the repository changes, an updated Overview MUST continue to
  satisfy FR-009 and FR-011. Prose naming something that no longer exists MUST
  NOT survive the update.
- **FR-017a**: When the repository has changed since its most recent narrative
  and no provider can produce a new one, for any of the reasons in FR-014, the
  Overview MUST show that most recent narrative rather than none. Before
  publication it MUST be checked against the repository as it is now: every
  paragraph that no longer satisfies FR-009 to FR-013 is dropped, FR-010a and
  FR-025a apply, and every subsystem it links to must still exist. It MUST be
  marked as describing an earlier version of the repository, in the way the
  wiki already marks a summary that has not yet been regenerated. A new
  narrative replaces it as soon as a provider answers. When no earlier
  narrative exists, FR-014 applies unchanged.
- **FR-018**: When the narrative is omitted, partly withheld (FR-010a, FR-025a),
  shown from an earlier version (FR-017a), or produced by a fallback provider,
  the analysis MUST report that in its normal progress output, so the omission,
  reduction or switch is never silent. The Overview page itself MUST NOT carry that report.
- **FR-019**: The narrative MUST be produced only through AI providers the user
  has already configured for the wiki's generated text. It MUST NOT send
  repository content to any other destination.
- **FR-020**: The AI usage consumed by producing the narrative MUST stay under a
  fixed ceiling that does not grow with the number of modules, subsystems or
  files in the repository.

#### The subsystems section (User Story 2)

- **FR-021**: The table pairing each subsystem with a count of its modules MUST
  be replaced by a table with one row per subsystem and three columns: the
  subsystem, linked to its page; its responsibility, which is the description
  the wiki already publishes for that subsystem; and its entry point or key
  module, linked to that module's page. A description that is model-written and
  fails FR-009, FR-011 or FR-013 MUST NOT appear in the table. Its cell shows a
  dash, exactly as for a subsystem with no description. The subsystem's own
  page, which this feature does not change, is unaffected.
- **FR-022**: The subsystems table MUST list every subsystem the wiki publishes a
  page for, exactly once, in the same order as the wiki's navigation.
- **FR-023**: The entry point or key module shown for a subsystem MUST be a
  module that belongs to that subsystem.
- **FR-024**: The subsystems table, with all its rows, columns and links, MUST
  appear whether or not an AI provider is available.
- **FR-025**: When an AI provider is available, the table MUST be followed by at
  most one paragraph, of at most three sentences, for each major subsystem, and
  by no more than eight such paragraphs in total. Each paragraph MUST end with a
  link to that subsystem's page and MUST satisfy FR-005a, FR-007's citation
  requirement, and FR-009 to FR-013.
- **FR-025a**: Per-subsystem paragraphs are published or withheld one at a time.
  Withholding one MUST NOT withhold the others, and MUST NOT remove that
  subsystem's table row. The paragraphs that are published MUST appear in the
  table's order, whatever order they were written in. A major subsystem without
  a paragraph shows nothing in its place.

#### Getting started (User Story 3 — deferred from the first release)

FR-026 to FR-028 bind the release that ships User Story 3. Until then, the
Overview has no getting-started section at all.

- **FR-026**: The Overview MUST include a "getting started" section only when the
  analysed repository contains evidence of how it is built, run or tested.
- **FR-027**: Every instruction in the "getting started" section MUST appear in a
  file of the analysed repository, and the section MUST name that file.
- **FR-028**: The section MUST show only the parts (build, run, test) that the
  evidence supports. When no part is supported, the section, including its
  heading, MUST NOT appear, and nothing MUST be shown in its place.

#### Module-list hygiene (User Story 4)

- **FR-029**: No row of the module list MUST contain unmatched or orphaned
  punctuation, whether or not the module has a description.
- **FR-030**: No two rows of the module list MUST carry the same visible label.
  Modules that share a name MUST be distinguished within the row itself.
- **FR-031**: Descriptions in the module list MUST be shown as plain readable
  text, free of raw markup characters.
- **FR-032**: A description shortened to fit its row MUST end at a sentence or
  word boundary and MUST visibly indicate that it has been shortened.
- **FR-033**: Every module row MUST keep a working link to its module page and a
  working link to its dependency view.
- **FR-034**: FR-029 to FR-033 MUST hold whether or not an AI provider is
  available.

### Key Entities

- **Overview page**: The wiki's landing page for one analysed repository. Holds,
  in order, the narrative lead when available, the repository facts, the
  subsystems section, the getting-started section when supported (once User
  Story 3 ships), the links to
  repository-wide diagrams, and the module list. Its address and identity never
  change.
- **Narrative lead**: Up to four paragraphs of generated explanation at the top
  of the Overview. It is derived from the analysis and the repository's own
  self-description, grounded in real names, marked as generated, and entirely
  optional: its absence changes nothing else on the page.
- **Subsystem**: The reader-facing name on the Overview for one of the capability
  groupings the wiki already derives and publishes as a page. It has a title, a
  responsibility, member modules, and an entry point or key module among them.
  It is not a second grouping alongside the existing one.
- **Evidence**: The facts generated text is allowed to draw on and cite. These
  are the repository's files, modules and symbols as analysed, its subsystems,
  where work enters it, and its own description of itself. Anything the text
  names must be found here.
- **Grounded reference**: A file, module or symbol named in generated text,
  together with its confirmation that it exists in the evidence. Text containing
  an unconfirmed reference is not published.
- **Generated marker**: The visible indication, already used across the wiki,
  that a passage was written by an AI model rather than derived directly from
  the analysis.
- **Build-and-run evidence**: The declarations in the analysed repository of how
  it is built, run and tested, each attributable to a file. It is the only
  source the getting-started section may draw on.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For each of two reference repositories (the project's sample
  repository and the tool's own repository), a reviewer who has not worked on
  that repository reads only its Overview page, for no more than five minutes,
  then correctly names at least three of its major subsystems (or all of them,
  if it has fewer) and correctly identifies where an operation begins.
  "Correctly" is judged against an answer key (the subsystems, and the places
  where operations begin) written from the code **before** the review, by
  someone other than the reviewer. The reviewer may be a person, or a fresh AI
  session given only the Overview page. Neither the person nor the session may
  have seen the repository, the key, or this feature's development.
- **SC-002**: Across every Overview page generated during verification, including
  runs fed deliberately fabricated provider output, 100% of the file paths,
  module names and symbols named in generated text resolve to something that
  exists in the analysed repository, and zero fabricated names are published.
- **SC-003**: 100% of links in generated text lead to a page that exists in the
  wiki. 100% of paragraphs in the narrative lead contain at least one such link,
  and 100% of generated paragraphs cite at least one file, module or symbol that
  resolves (FR-007).
- **SC-004**: For the same repository, pages produced under each of the four
  no-provider conditions (not configured, unreachable, refused, unusable output)
  all build successfully. For the same subsystem grouping, each has the same
  headings in the same order, the same link destinations outside generated text,
  and the same navigation as the page produced with a working provider.
- **SC-005**: Two consecutive analyses of an unchanged repository produce Overview
  pages whose content has zero differences, the shared footer's generation
  timestamp aside. Reopening that repository's documentation leaves the page
  untouched.
- **SC-006**: On every Overview page that has a narrative lead, the first content
  after the page title is explanatory prose. No list, table or diagram precedes
  it.
- **SC-007**: On every repository in the verification set, the narrative lead
  never exceeds four paragraphs, no per-subsystem paragraph exceeds three
  sentences, no more than eight subsystems receive a paragraph, and the page's
  generated prose totals fewer than 600 words. These are upper bounds the system
  enforces. The two-paragraph minimum of FR-005 is a request made of the
  generator, not a guarantee. It is checked in the SC-001 review, which records
  any lead of fewer than two paragraphs on a repository with at least two
  subsystems.
- **SC-008**: 100% of generated text on the Overview carries the generated
  marker, or sits in a table column whose heading says it is generated, and the marker is legible in both light and dark appearance at both a
  narrow and a wide window.
- **SC-009**: Across all generated text in the verification set, zero sentences
  address the reader in the second person and zero use an adjective from the
  project's list of banned promotional terms.
- **SC-010**: For each reference repository, the module list contains zero rows
  with orphaned punctuation, zero pairs of rows with identical labels, zero
  descriptions containing raw markup, and zero descriptions ending mid-word.
- **SC-011** *(applies to the release that ships User Story 3)*: For a
  repository that declares how it is built, run and tested,
  100% of getting-started instructions appear verbatim in the file they are
  attributed to. For a repository that declares none, the Overview contains no
  getting-started heading.
- **SC-012**: The AI usage attributable to the narrative stays below the same
  fixed ceiling (FR-020) on both reference repositories, although one is several
  times the size of the other; doubling the number of modules in a repository
  never pushes it past that ceiling.
- **SC-013**: For each reference repository, a reviewer reads every generated
  sentence on the Overview: the narrative and any generated table text. They
  find zero sentences outside declarative present tense. That rules out future
  forms ("will handle"), past narration ("was designed to"), imperatives, and
  questions. The review is recorded as a list of every sentence judged, so it
  can be repeated.

## Assumptions

- **"Subsystem" means the existing feature grouping.** The wiki already derives a
  set of capability groupings and publishes one page per grouping. The Overview
  calls them subsystems for the reader, but they are the same units, in the same
  order. This feature does not change how they are derived.
- **Generated text uses the providers already configured** for the wiki's other
  generated text, and follows the same configured fallback order. No new
  configuration is required to get a narrative. Local-only operation works
  exactly as it does for the rest of the wiki.
- **The Overview stays a static page.** Like the rest of the generated wiki, it is
  opened without fetching anything at runtime. Everything on it is decided when
  the analysis runs.
- **Existence is checkable; meaning is reviewed.** That a named file or symbol
  exists can be verified mechanically and must be. Whether a paragraph describes
  the repository well cannot, so the quality of the explanation is judged by
  human review of the reference repositories (SC-001), not by automated checks
  alone.
- **Generated text is in English**, matching the rest of the wiki, whatever the
  language of the repository's own documentation.
- **"Major" subsystems are a bounded subset of at most eight** (FR-025). On a
  repository with more subsystems, the lead and the per-subsystem paragraphs
  cover the most significant ones, while the subsystems table always lists all
  of them. How significance is judged is a planning decision.
- **The repository-wide diagrams are reached by link, not shown inline**
  (FR-003b). The class diagram's own page already exists and is zoomable. The
  inline copy is removed because at full page width its labels cannot be read,
  not because the diagram itself is being changed.
- **The house style's list of banned promotional adjectives** is maintained with
  the feature. The examples in FR-013 illustrate it; they are not the whole
  list.

## Out of Scope

- **The getting-started section, in the first release.** User Story 3 and
  FR-026 to FR-028 are specified but deferred. The first release covers User
  Stories 1, 2 and 4.
- **Changing subsystem or module pages.** Only the Overview page changes.
  Generated text on other pages, and how it is marked, stays as it is.
- **Changing how subsystems are derived.** The grouping and its names come from
  the existing feature derivation. The Overview explains that grouping; it does
  not redraw it.
- **Letting users edit or pin the Overview's prose.** The page is regenerated
  from the analysis; hand-written overrides are a separate concern.
- **Verifying the truth of the repository's own documentation.** The narrative
  may draw on what the repository says about itself, and never names anything
  that does not exist. Auditing every claim that documentation makes is not
  attempted.
- **Chat, search ranking, or any page other than the Overview.**
