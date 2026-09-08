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
        ucScan(["codepedia scan\n(file inventory only, no AI needed)"])
        ucIndex(["codepedia index\n(scan, parse, analyze, then serve)"])
        ucSummarize(["Generate symbol summaries\nvia the local LLM"])
        ucEmbed(["Build the searchable\nvector index"])
        ucDocs(["Generate the documentation wiki"])
        ucServe(["codepedia serve\n(resume an indexed repo, watcher active)"])
        ucConfig(["codepedia config\n(connection settings for local: entries)"])
        ucProvider(["codepedia provider\n(choose each stage's provider chain)"])
        ucHome(["codepedia home\n(open the launcher homepage)"])
        ucAnalyseFromPage(["Analyse a repository\nby typing its path"])
        ucWatchProgress(["Watch a run advance\nstage by stage"])
        ucStopRun(["Stop a run in progress"])
        ucHistory(["Browse previously\nanalysed repositories"])
        ucReopen(["Reopen an analysed repository"])
        ucForget(["Remove a stored analysis\n(never the repository)"])
        ucCheckModels(["Verify local LLM/embedding\nmodel availability"])
        ucCheckVersion(["codepedia --version\n(confirm the install worked)"])
        ucBrowse(["Browse documentation pages"])
        ucSearch(["Search for a symbol by name"])
        ucDiagram(["View & click through a module's\ndependency diagram"])
        ucAsk(["Ask a question and get a\ncited, grounded answer"])
        ucWatch(["Watch the repository for changes"])
        ucReindex(["Incrementally re-index\njust what changed"])
        ucFailover(["Fail over to the next provider\nin the configured chain"])
        ucFailClear(["Fail clearly when every provider\nin the chain is unavailable"])
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
    operator --> ucProvider
    operator --> ucCheckVersion
    operator --> ucHome
    ucHome -->|include| ucHistory
    ucHome -->|include| ucAnalyseFromPage
    ucAnalyseFromPage -->|include| ucIndex
    ucAnalyseFromPage -->|include| ucWatchProgress
    ucWatchProgress -->|extend| ucStopRun
    ucHistory -->|extend| ucReopen
    ucHistory -->|extend| ucForget
    ucReopen -->|include| ucServe

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

    ucSummarize -->|extend| ucFailover
    ucAsk -->|extend| ucFailover
    ucEmbed -->|extend| ucFailover
    ucFailover -->|extend| ucFailClear
    ucCheckModels -->|extend| ucFailClear
```
