# Project Use Case Diagram

**Scope**: the whole system, one diagram — every primary way a human (or the system's
own automation) interacts with the tool.

> Maintenance: update this diagram whenever a new user-facing capability is added.
> Mermaid has no native UML use-case diagram type, so this is a `flowchart` that mimics
> one: actor nodes linked to oval "use case" nodes inside a system-boundary `subgraph`,
> with `-->|include|` / `-->|extend|` labeled arrows standing in for UML's
> `<<include>>` / `<<extend>>` relationships.

```mermaid
flowchart LR
    operator(["👤 Operator\n(runs the tool)"])
    developer(["👤 Developer\n(edits code)"])
    reader(["👤 Team member\n(browses / asks questions)"])
    watcherActor(["🤖 Repository Watcher\n(background automation)"])

    subgraph sys["Local Code Documentation Tool"]
        ucScan(["repo-scanner scan\n(file inventory only, no AI needed)"])
        ucIndex(["repo-scanner index\n(scan, parse, analyze, then serve)"])
        ucSummarize(["Generate symbol summaries\nvia the local LLM"])
        ucEmbed(["Build the searchable\nvector index"])
        ucDocs(["Generate the documentation wiki"])
        ucServe(["repo-scanner serve\n(resume an indexed repo, watcher active)"])
        ucConfig(["repo-scanner config\n(choose local LLM/embedding model)"])
        ucCheckModels(["Verify local LLM/embedding\nmodel availability"])
        ucCheckVersion(["repo-scanner --version\n(confirm the install worked)"])
        ucBrowse(["Browse documentation pages"])
        ucSearch(["Search for a symbol by name"])
        ucDiagram(["View & click through a module's\ndependency diagram"])
        ucAsk(["Ask a question and get a\ncited, grounded answer"])
        ucWatch(["Watch the repository for changes"])
        ucReindex(["Incrementally re-index\njust what changed"])
        ucFailClear(["Fail clearly instead of using\na remote/cloud service"])
    end

    operator --> ucScan
    operator --> ucIndex
    ucIndex -->|include| ucSummarize
    ucIndex -->|include| ucEmbed
    ucIndex -->|include| ucDocs
    ucIndex -->|include| ucCheckModels
    operator --> ucServe
    ucServe -->|include| ucCheckModels
    operator --> ucConfig
    operator --> ucCheckVersion

    reader --> ucBrowse
    reader --> ucSearch
    reader --> ucDiagram
    reader --> ucAsk
    ucAsk -->|include| ucSearch

    developer -.triggers.-> watcherActor
    watcherActor --> ucWatch
    ucWatch -->|include| ucReindex
    ucReindex -->|include| ucSummarize
    ucReindex -->|include| ucEmbed
    ucReindex -->|include| ucDocs

    ucSummarize -->|extend| ucFailClear
    ucAsk -->|extend| ucFailClear
    ucEmbed -->|extend| ucFailClear
    ucCheckModels -->|extend| ucFailClear
```
