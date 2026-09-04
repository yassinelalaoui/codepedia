# Feature Specification: Wiki Theming and Brand Identity

**Feature Branch**: `036-wiki-theming-brand`

**Created**: 2026-09-04

**Status**: Draft

**Input**: User description: "Wiki theming and brand identity. The generated static wiki needs two things that are currently missing. First, a reader-facing theme control: the wiki's stylesheet already defines light tokens, an OS-dark-preference state, and a pinned-dark state, but nothing in the shipped output ever selects between them, so a reader cannot override what their operating system dictates. Readers need to choose System, Light, or Dark, have that choice remembered across pages and across visits on the same machine, and have it applied before the page first paints so navigating between wiki pages never flashes the wrong theme. With scripting unavailable the page must still follow the operating system preference exactly as it does today. Second, the wiki must carry the real Codepedia brand instead of the hand-made two-letter placeholder currently sitting in the page shell's brand slot. The brand kit already exists under docs/brand/ with a documented usage policy: light and dark variants of the mark, a simplified icon for small sizes, a minimum size below which the full mark must not be used, and rules against recolouring, drop shadows, gradients, or crowding the clear space. The wiki's brand slot must show the correct brand asset for the active theme and switch with it, and the wiki must have a browser tab icon, which it currently lacks entirely. Every brand asset a generated wiki needs must travel with that wiki rather than being referenced from the repository it was generated from. Both must hold under the project's zero-network-exposure rule: a generated wiki is opened directly from the filesystem with no server and no network, so nothing may be fetched at runtime. The existing command-line flows must behave exactly as they do now."

## Clarifications

### Session 2026-09-04

- Q: Which brand asset should the wiki's top-left brand slot use, given the brand policy sets a 24 px floor for the full mark and the slot is 20 px today? → A: Grow the slot to 24 px and use the full mark, swapping the light/dark variant with the theme. The adjacent "codepedia" wordmark text stays.
- Q: What form should the theme control take — a three-way control, or a two-way toggle with System reachable another way? → A: A segmented three-way control (System / Light / Dark) in the sidebar, with the current state visibly selected and every state one click away.
- Q: On a theme switch, must already-rendered diagrams restyle immediately, or may they wait for the next page load? → A: Immediately — diagrams re-render on theme change so the page is never internally inconsistent, and the reader's existing zoom and pan position is preserved across that re-render.
- Q: Should a reader's theme choice be shared across every Codepedia wiki on the machine, or kept per wiki? → A: Per wiki, independent. Each generated wiki remembers its own choice; wikis do not coordinate, matching what browsers permit for pages opened from the filesystem.
- Q: Should printing be handled in this feature, or dropped from scope? → A: Kept, but minimal — printed output always uses the light palette regardless of the screen theme. A considered print layout (dropping the sidebar, chat panel and theme control) is explicitly out of scope.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Read the wiki in the theme I choose (Priority: P1)

A reader works in a bright room with their operating system pinned to dark
because everything else they use looks better that way. They open a generated
wiki and it is dark, which is exactly what they did not want for long-form
reading. Today they have no recourse: the wiki obeys the operating system and
offers nothing to override it. They want to pick Light, keep reading, and never
be asked again.

The mirror case is just as common: a reader whose operating system is light
wants the wiki dark for an evening session, without changing a global setting
that affects every other application.

**Why this priority**: This is the entire reason the feature exists. The
underlying visual work is already done and verified — three complete states are
defined and correct — but no reader can reach two of them. This story is what
turns existing, invisible capability into something a person can use.

**Independent Test**: Open any page of a generated wiki with the operating
system set to dark, choose Light, and confirm the page turns light and stays
light. Repeat with the operating system set to light, choosing Dark.

**Acceptance Scenarios**:

1. **Given** a reader on any page of a generated wiki, **When** they look at the
   page shell, **Then** a theme control is visible and its current state is
   identifiable without interacting with it.
2. **Given** an operating system set to dark and a reader who has expressed no
   preference, **When** they open the wiki, **Then** the wiki is dark.
3. **Given** that same reader, **When** they choose Light, **Then** the page
   becomes light immediately, without a page reload and without losing their
   scroll position.
4. **Given** a reader who has chosen Dark while their operating system is light,
   **When** they open the wiki, **Then** the wiki is dark.
5. **Given** a reader who has chosen System, **When** the operating system's
   preference changes while the wiki is open, **Then** the wiki follows the new
   operating system preference without a reload.
6. **Given** a reader using only a keyboard, **When** they move focus through
   the page shell, **Then** they can reach the theme control and change the
   theme with the keyboard alone.

---

### User Story 2 - The choice sticks, and never flashes (Priority: P1)

Having chosen Light, the reader clicks through to a module page, then a feature
page, then follows a cross-reference to a diagram. They expect every one of
those pages to be light from the instant it appears. They close the browser,
come back tomorrow, and expect it to still be light.

**Why this priority**: A theme control that forgets the choice on the next page
is worse than no control at all — the reader re-chooses on every navigation. A
control that remembers but repaints after the page has already appeared produces
a white flash on every single navigation for a dark-theme reader, which reads as
a broken wiki. The two together are the difference between a usable feature and
an irritating one, which is why they sit at the same priority as the control
itself.

**Independent Test**: Choose Dark, then navigate across at least five pages of
the wiki, watching for any frame that renders light. Then close the browser
entirely, reopen the wiki, and confirm it is still dark.

**Acceptance Scenarios**:

1. **Given** a reader who has chosen a theme, **When** they navigate to any
   other page in the same wiki, **Then** that page uses the chosen theme.
2. **Given** a reader who has chosen Dark, **When** any page of the wiki loads,
   **Then** no part of the page is ever painted in the light theme, at any point
   during loading.
3. **Given** a reader who has chosen a theme, **When** they close the browser
   and reopen the wiki later, **Then** their choice is still in effect.
4. **Given** a reader who has chosen Light or Dark, **When** they choose System,
   **Then** the wiki returns to following the operating system and continues to
   do so on subsequent visits.
5. **Given** a browser that refuses to store the preference, **When** the reader
   chooses a theme, **Then** the theme still applies for the current page and
   the reader sees no error.

---

### User Story 3 - The wiki looks like Codepedia produced it (Priority: P2)

Someone opens a generated wiki, or sees a tab of one among twenty other tabs.
Today the top-left corner carries a hand-drawn two-letter placeholder and the
browser tab carries the browser's blank-document icon, so nothing identifies the
wiki as a Codepedia artifact or distinguishes it from any other local HTML file.

**Why this priority**: This is presentation, not capability — every reading task
still succeeds without it. It ranks below the theme work but belongs in the same
feature because the brand needs a light and a dark variant, which only means
something once a reader can pick a theme.

**Independent Test**: Open a generated wiki and confirm the real Codepedia mark
is in the top-left brand slot and a Codepedia icon is on the browser tab. Switch
the theme and confirm the mark switches with it.

**Acceptance Scenarios**:

1. **Given** any page of a generated wiki, **When** it is displayed, **Then** the
   page shell's brand slot shows the official Codepedia mark rather than a text
   placeholder.
2. **Given** any page of a generated wiki, **When** it is open in a browser,
   **Then** the browser tab shows a Codepedia icon.
3. **Given** a wiki displayed in the light theme, **When** the reader switches to
   the dark theme, **Then** the brand mark switches to the variant intended for
   dark backgrounds, and back again on switching to light.
4. **Given** the full mark rendered in the page shell's brand slot, **When** its
   displayed size is measured, **Then** it is at least 24 px, the minimum the
   brand policy sets for the full mark.
5. **Given** a reader using a screen reader, **When** they reach the brand slot,
   **Then** the wiki's identity is announced once, without a redundant duplicate
   reading of an adjacent title.

---

### User Story 4 - It still works with no network and no server (Priority: P2)

A reader receives a generated wiki as a folder — on a memory stick, in an
archive, on a machine with no internet connection — and opens a page by
double-clicking it. Everything must work: the theme control, the brand, the tab
icon, the diagrams.

**Why this priority**: A regression guard on a property the project already
guarantees and treats as non-negotiable. It is not new capability, but this
feature adds visual assets and a script that runs before paint, which are exactly
the two things most likely to break it.

**Independent Test**: Disconnect from the network, copy a generated wiki to a
directory outside the repository it was generated from, open it directly from the
filesystem, and exercise the theme control and the brand.

**Acceptance Scenarios**:

1. **Given** a generated wiki copied away from the repository that produced it,
   **When** any page is opened directly from the filesystem, **Then** the brand
   mark and tab icon display correctly.
2. **Given** a page open with no network connection, **When** the reader uses the
   wiki, **Then** no request to any network address is attempted at any point.
3. **Given** a reader with scripting unavailable or blocked, **When** they open
   the wiki, **Then** the page renders completely and follows the operating
   system's light or dark preference.
4. **Given** a reader who switches theme, **When** diagrams and code blocks are
   on the page, **Then** the diagrams are redrawn in the new theme at the
   reader's current zoom and pan position, and the code blocks remain legible.

---

### Edge Cases

- **Stored preference is unreadable or nonsensical.** A value left by an older
  version, hand-edited, or corrupted must not break the page; the wiki falls back
  to following the operating system.
- **The browser refuses to store anything.** Private browsing, a locked-down
  profile, or a browser that disallows storage for filesystem-opened pages. The
  theme control must still work for the current page and must not surface an
  error to the reader.
- **Scripting is unavailable.** The theme control may be absent or inert, but the
  page must render fully and follow the operating system preference — the
  behaviour readers get today.
- **The operating system preference changes while the wiki is open** — a
  scheduled day/night switch, for example — while the reader has chosen System.
- **The theme is switched while a diagram is zoomed in and panned.** The diagram
  has to be redrawn in the new theme without throwing away where the reader was
  looking.
- **A wiki page is printed.** Printing a dark-themed page wastes ink and can
  render text illegibly.
- **The brand slot is displayed at a small size**, where the brand policy forbids
  the full mark and requires the simplified icon instead.
- **A wiki generated by an older version is opened**, or an existing wiki is
  regenerated — the new assets must arrive and stale ones must not linger.
- **Two different generated wikis are open at once** on the same machine.

## Requirements *(mandatory)*

### Functional Requirements

#### Theme selection

- **FR-001**: Every generated wiki page MUST present, in the sidebar, a segmented
  theme control offering exactly three choices — System, Light, and Dark — each
  selectable in a single interaction from any state.
- **FR-002**: The theme control MUST show which of the three is currently in
  effect without the reader having to open, hover, or otherwise interact with it.
- **FR-003**: For a reader who has never expressed a preference, the wiki MUST
  default to System.
- **FR-004**: Selecting a theme MUST take effect immediately on the current page,
  without a page reload and without disturbing the reader's scroll position.
- **FR-005**: When System is in effect, the wiki MUST follow the operating
  system's light/dark preference, including changes made while the page is open.
- **FR-006**: When Light or Dark is in effect, the wiki MUST use that theme
  regardless of the operating system's preference.
- **FR-007**: The wiki MUST remember the reader's choice and apply it to every
  other page of that same wiki and to later visits on the same machine and
  browser. The choice is scoped to one wiki: separate generated wikis remember
  their own choices independently and MUST NOT overwrite one another.
- **FR-008**: The chosen theme MUST be applied before the page is first painted,
  so that no page ever displays in one theme and then changes to another.
- **FR-009**: If the stored preference is missing, unreadable, or not one of the
  three recognised values, the wiki MUST behave as though System were chosen.
- **FR-010**: If storing or reading the preference fails for any reason, the wiki
  MUST continue to render and the theme control MUST continue to work for the
  current page, with no error shown to the reader.
- **FR-011**: With scripting unavailable, the wiki MUST render completely and
  follow the operating system's preference, matching the behaviour readers get
  before this feature.
- **FR-012**: The theme control MUST be reachable and operable by keyboard alone
  and MUST carry an accessible name describing its purpose.
- **FR-013**: Content whose colours are fixed at the moment it is drawn — diagrams
  in particular — MUST be redrawn in the newly selected theme when the theme
  changes, so no part of the page is left showing the previous theme's colours.
- **FR-013a**: Redrawing a diagram on a theme change MUST preserve the reader's
  current zoom level and pan position for that diagram.
- **FR-013b**: Code blocks MUST remain legible in both themes after a theme
  change, without a page reload. (This is satisfied by the existing token-based
  styling and needs no new work — see Assumptions. The wiki ships no syntax
  highlighter, so there are no highlighter colours to re-theme.)

#### Brand identity

- **FR-014**: The page shell's brand slot MUST display the official Codepedia
  full mark in place of the current text placeholder, alongside the existing
  visible "codepedia" wordmark text, which is retained.
- **FR-015**: The brand asset MUST match the active theme — the light-background
  variant in the light theme, the dark-background variant in the dark theme — and
  MUST change when the theme changes, without a page reload.
- **FR-016**: Every generated wiki page MUST declare a browser tab icon.
- **FR-017**: The brand slot MUST render the full mark at no less than 24 px, the
  minimum the brand policy sets for it — which requires enlarging the slot from
  its current 20 px. Any other brand asset used elsewhere in the wiki MUST
  likewise be displayed at or above the minimum its own policy entry defines.
- **FR-018**: Brand assets MUST be presented as published — no recolouring, drop
  shadow, gradient, or added outline — and MUST retain the clear space the brand
  policy requires.
- **FR-019**: The brand MUST be conveyed to assistive technology exactly once,
  without duplicating an adjacent visible title.

#### Self-containment and compatibility

- **FR-020**: Every asset a generated wiki needs MUST be written into that wiki's
  own output, so the wiki remains complete when moved away from the machine or
  the repository that produced it.
- **FR-021**: A generated wiki MUST NOT reference the Codepedia source repository
  or any other location outside its own output directory.
- **FR-022**: A generated wiki MUST NOT attempt any network request at any point,
  under any theme, on any page.
- **FR-023**: Regenerating an existing wiki MUST bring its assets up to date.
- **FR-024**: The existing command-line flows MUST behave exactly as they do
  today; this feature adds no new required step, prompt, or argument to them.
- **FR-025**: Generation MUST continue to write only to the generated
  documentation output location, never into the repository being analysed.

#### Printing

- **FR-026**: A wiki page sent to a printer MUST print using the light palette —
  dark text on a light background — whatever theme is in effect on screen.
  Rearranging the page for print (dropping the sidebar, chat panel or theme
  control) is out of scope for this feature.

### Key Entities

- **Theme Preference**: One reader's choice for one wiki — System, Light, or
  Dark. Held on the reader's own machine, per browser. Never leaves the machine
  and is never part of the generated output.
- **Effective Theme**: What the reader actually sees — light or dark. Derived
  from the Theme Preference, falling through to the operating system's preference
  when that preference is System.
- **Brand Asset Set**: The published Codepedia marks and icons, each with a
  documented purpose, a background it is intended for, and a minimum display
  size. Owned by the brand kit; copied into each generated wiki.
- **Page Shell**: The frame every generated page shares — the brand slot, the
  navigation, and the tab icon. The single place both the theme control and the
  brand appear.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reader can change the wiki's theme from any page in one
  interaction, without leaving the page they are reading.
- **SC-002**: With Dark chosen, navigating across ten wiki pages produces zero
  frames rendered in the light theme.
- **SC-003**: A theme choice survives closing and reopening the browser in 100%
  of attempts on a browser that permits storage.
- **SC-004**: 100% of generated wiki pages display the official brand mark and
  declare a browser tab icon.
- **SC-005**: Opening a generated wiki with no network available produces zero
  attempted network requests.
- **SC-006**: A generated wiki copied to an unrelated directory on a machine that
  has never held the Codepedia source repository renders identically to one
  opened in place, including the brand and tab icon.
- **SC-007**: With scripting disabled, a wiki page renders completely and matches
  the operating system preference under both a light and a dark operating system
  setting.
- **SC-008**: Every brand asset in the wiki renders at or above its documented
  minimum size.
- **SC-009**: All three theme states are reachable by keyboard alone.
- **SC-010**: Existing command-line flows produce the same observable behaviour
  before and after this feature.
- **SC-011**: Switching theme on a page containing a diagram leaves no diagram
  showing the previous theme's colours, and a diagram the reader had zoomed and
  panned is still at that same zoom and position afterwards.

## Assumptions

- **The three visual states already exist and are correct.** The wiki's styling
  already defines a light state, an operating-system-dark state, and a pinned
  state that overrides the operating system in both directions. This feature adds
  the means of selecting between them and does not redesign the palette.
- **The brand kit is final.** The published assets, their intended backgrounds,
  and their minimum sizes are taken as given. No new brand artwork is drawn, and
  no existing asset is edited.
- **The theme control belongs in the page shell**, alongside the brand, so it
  appears identically on every generated page rather than only on some.
- **The preference is per reader, per browser, and per wiki**, stored locally —
  confirmed in clarification, not merely assumed. It is not shared between
  different generated wikis, not synchronised between machines or browsers, and
  not shared with the Codepedia application's other surfaces. Two wikis open at
  once are independent.
- **A reader who has expressed no preference is treated as System**, which
  preserves exactly what readers experience today.
- **Printing is expected to produce a legible page.** A dark-themed page sent to
  a printer should not print a dark background.
- **The wiki is read by one person at a time in their own browser.** No aspect of
  the preference is shared, transmitted, or persisted into the generated output.
- **Existing wikis will be regenerated** rather than migrated in place; there is
  no requirement to upgrade an already-generated wiki without regenerating it.
- **No syntax highlighter ships with the wiki.** Code blocks are styled entirely
  from the theme's own colour tokens, so they follow a theme change with no work
  at all. FR-013b is therefore a regression guard, not a build item — it was
  written during clarification on the assumption that a highlighter existed, and
  cross-artifact analysis found none. If a highlighter is ever added, its colours
  become a genuine re-theming concern and FR-013b gains real weight.
