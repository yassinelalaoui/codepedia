# T037: SC-006 mapping, stranger test (SC-007), checks, 2026-09-15

Pages: the wikis after round 2 and the round-3 repair (model-named features,
reach tie-break). Keys: 038's `sc001-key-{sample,nextgen}.md`, written from the
code before any page was read. Features and members: `t037-features-*.txt`.

## SC-006 (a feature corresponds to a key subsystem when most of its production modules belong to it)

**Nextgen: 7 of 9, pass.** It includes all four that SC-006 requires.

| Feature | Corresponds to |
| --- | --- |
| Wallet Management | wallets and ledger (27 of 38 modules are wallet, ledger or wallet-UI code) |
| Authentication and Authorization | security (about 21 of 31) |
| Client Management | clients (10 of 19) |
| Chatbot Assistant | chatbot (9 of 9) |
| Dashboard Overview | dashboard (4 of 4) |
| User Profile | frontend (2 of 2) |
| Ledger Persistence | persistence (3 of 3) |

Controllers and services have no feature of their own, as research Decision
12 expected. Application Core (`DigitalBankingApplication`, `README`,
`refactor.py`) is supporting.

**Sample: 3 of 8, fail.**

| Feature | Majority subsystem |
| --- | --- |
| Storage Implementations | Storage (4 of 4) |
| Catalog Management Service | Core/utils (3 of 5) |
| Developer Tools | Web client (4 of 6) |

- The model merged vertical slices. "Public API Endpoints" is routes plus
  domain plus services (domain is 5 of 14), and "Lending" is the service plus
  the email integration (2 and 2). The key lists layers, so no feature is
  mostly one layer.
- Research Decision 12 amended SC-006 for nextgen's controllers for the same
  reason, but not for the sample.
- The CLI is a minority in "Developer Tools": 2 of its 6 modules, with 4
  web-client files.
- Without a model, the sample's groups map to 6 of 8: Domain, Storage (twice),
  Integrations, Core/utils, Web client and CLI. The CLI group is `cli.py` plus
  the package `__init__`, so it is borderline under a strict majority.

## SC-007 stranger test

One fresh general-purpose subagent per repository, Read once on
`<state>\docs\index.md`. Both notifications: `tool_uses: 1`.

| | Sample | Nextgen |
| --- | --- | --- |
| Key subsystems named from the table or prose | API, Services (lending, catalog), Storage, Core, CLI (in Developer Tools): at least 5, pass | wallets, security, clients, chatbot, dashboard, persistence: 6, pass |
| Named only from module names | domain, members, integrations, web UI, tests | controllers, JWT classes, accounts, error handling |
| Entry | `routes_loans.py`, `routes_books.py`, `cli.py`, `api/app.py` | `DigitalBankingApplication.main`; "never names where an operation begins" |
| Subsystems flagged | 7, fail (limit 1) | 5, fail (limit 1) |
| Newcomer understands | PARTLY | PARTLY |

**Sample flags, sorted by cause:**

- **3: the table's "Start with" disagrees with the prose's start file.**
  `policies`, `email_gateway` and `book` against `routes_loans`,
  `lending_service` and `catalog_service`. 038's `_start_with_member` picks
  the member with the most entry points, ties by name. It is its own rule,
  not FR-010's anchor, which the prose cites.
- **3: relation claims in the paragraphs.** For example "Storage ... stores
  results for Time Management Core" and "Application Bootstrap integrates
  Documentation & Guides". These are 038's narrative, whose prompt this spec
  does not change.
- **1: the model's "Developer Tools"**, which puts the CLI with the API client.

**Nextgen flags:**

- **2: the table and prose disagree** (`account.service` against
  `clients.component.ts`; `WalletService` against `WalletServiceImpl`).
- **1: an anchor choice.** Authentication starts at the frontend
  `auth.service.ts`, while backend security appears only in the module list.
- **1: "Application Core" is a catch-all** (`main`, the README, `refactor.py`).
- **1: a relation claim** (the dashboard component "accesses" the ledger repository).

**Against 038 Decision 19:** the reviewers now take the subsystems from the
table and prose, where before they took them from module names. The flags have
moved from wrong grouping (033's "Tests" and "Scripts", helper anchors) to the
table/prose disagreement, the prose's relation sentences and two naming choices
made by the model.

## Re-test after T037a ("Start with" = anchor), same protocol and prompt

Pages regenerated with no model call (plan and narrative `generated_at`
unchanged). Two fresh reviewers; both notifications: `tool_uses: 1`.

| | Sample | Nextgen |
| --- | --- | --- |
| Key subsystems from the table or prose | at least 5, pass | 6, pass |
| Subsystems flagged | 5 (was 7), fail | 8 (was 5), fail |
| Newcomer understands | PARTLY | PARTLY |

**Sample flags:**

- The table/prose contradiction is gone (was 3 flags).
- **2: 038 relation sentences** ("Application Bootstrap integrates Documentation
  & Guides"; Storage "stores results for" Time Management Core).
- **2: the model's names** ("Time Management Core" also holds config;
  "Developer Tools" mixes the CLI with the web client).
- **1: an anchor among equals** (`routes_loans` among three route files).

**Nextgen flags:**

- **6: cross-stack features start at one layer.** Authentication starts at the
  frontend `auth.service.ts`; Client, Chatbot, Dashboard and Profile start at
  frontend components; Wallet starts at `WalletServiceImpl`, not
  `WalletController`. The model merged each backend slice with its frontend
  slice. The anchor is the seed with the most entry points, often an Angular
  component, because Spring controllers are ordinary seeds, not routes (Java
  annotations are out of scope).
- **1: Ledger Persistence** is a single repository promoted to a subsystem.
- **1: Application Core** "interacts with" everything.
- The reviewer also asked where an operation begins beyond `main`.

## Checks

- `why3.py`, sample: lead kept (3 paragraphs); 9 of 9 offered paragraphs kept,
  2 unasked; 6 subsystem paragraphs (tooling and overview kinds get none).
- `why3.py`, nextgen: lead kept; 11 of 11 kept; 8 subsystem paragraphs.
- `lead_links.py`: sample 0 problems (47 links, 12 code spans); nextgen 0
  problems (48 links, 15 code spans).
- Screenshots in the session scratchpad (`t037-*-700-dark.png`,
  `t037-*-wide-light.png`): both pages render; at 700 px the table's "Start
  with" column is clipped (the wiki shell's known lack of a narrow layout).
