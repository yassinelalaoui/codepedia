# Project Class Diagram

**Scope**: the whole system, one diagram. Each `namespace` below is one package under
`src/`; only the classes and relationships that matter for understanding how data
flows from a raw repository to a browsable, self-updating wiki are shown — not every
field or method (see each package's own module docstrings/tests for full detail).

> Maintenance: update this diagram whenever a class is added, removed, or its
> cross-package relationships change.

```mermaid
classDiagram
    namespace Scanner {
        class ScanResult {
            +str root_path
            +list~SourceFileEntry~ entries
        }
        class SourceFileEntry {
            +str relative_path
            +str language
        }
    }

    namespace ParserEngine {
        class FileSymbolInventory {
            +str sourceFile
            +ModuleSymbol module
            +list~ClassSymbol~ classes
            +list~FunctionSymbol~ functions
        }
        class Symbol {
            <<abstract>>
            +str id
            +str name
            +str generatedSummary
        }
        class ModuleSymbol
        class ClassSymbol
        class FunctionSymbol
    }
    Symbol <|-- ModuleSymbol
    Symbol <|-- ClassSymbol
    Symbol <|-- FunctionSymbol
    FileSymbolInventory *-- Symbol

    namespace DependencyGraphPackage {
        class DependencyGraph {
            +dict~str,DependencyNode~ nodes
            +ingest_inventory(inventory)
            +remove_source_file(source_file)
            +dependents(focus) list~DependencyNode~
            +exportDiagram(root) DiagramExport
        }
        class DependencyNode {
            +str id
            +str kind
            +str sourceFile
        }
        class DependencyEdge {
            +str sourceId
            +str targetId
            +str type
        }
    }
    DependencyGraph *-- DependencyNode
    DependencyGraph *-- DependencyEdge

    namespace RepositoryMetadata {
        class RepositoryMetadataStore {
            +store_inventory(root, file, inventory, hash)
            +has_file_changed(root, path, hash) bool
            +delete_source_file(root, path)
            +load_repository(root) RepositoryBundle
        }
        class RepositoryBundle {
            +Repository repository
            +tuple~SourceFileBundle~ files
        }
        class Repository {
            +str id
            +str rootPath
        }
    }
    RepositoryMetadataStore ..> RepositoryBundle : loads
    RepositoryBundle *-- Repository

    namespace VectorIndexAndEmbeddings {
        class EmbeddingEngine {
            +embed(text) Vector
            +providerId str
            +isAvailableLocally() bool
            +isAvailable() bool
        }
        class VectorIndex {
            +reindexFile(path, chunks)
            +removeChunksForFile(path)
            +search(query, k) list~SearchResult~
        }
        class CodeChunk {
            +str id
            +tuple~float~ embedding
            +str sourceSymbolId
            +str embeddingModelId
        }
    }
    VectorIndex *-- CodeChunk
    VectorIndex ..> EmbeddingEngine : embeds query text via

    namespace LocalLLM {
        class LocalLLMEngine {
            +generate(prompt) str
            +generateStream(prompt) AsyncIterator
            +providerId str
            +isAvailableLocally() bool
            +isAvailable() bool
        }
    }

    namespace CodeSummaryPipelinePackage {
        class CodeSummaryPipeline {
            +summarizeRepository(root, incremental, changed_paths) list~SummaryResult~
            +isReady() bool
        }
        class SummaryResult {
            +str symbolId
            +str generatedSummary
        }
    }
    CodeSummaryPipeline ..> SummaryResult : produces
    CodeSummaryPipeline ..> LocalLLMEngine : llmEngine.generate()

    namespace ChatRAG {
        class ChatSession {
            +str id
            +list~ChatMessage~ messages
            +askStream(question) AsyncIterator
        }
        class ChatMessage {
            +str role
            +str content
            +tuple~str~ citedSymbolIds
            +str generatedBy
        }
    }
    ChatSession *-- ChatMessage
    ChatSession ..> LocalLLMEngine : llmEngine.generateStream()

    namespace DocGeneratorPackage {
        class DocGenerator {
            +generateRepositoryDocumentation(root, incremental, changedPaths, changedSymbolIds, changedDependencyEdgeIds) DocumentationSet
            +generateClassDiagramPage() DocPage
            +generateEntryPointSequenceDiagramPages() tuple~DocPage~
            +generateUseCaseDiagramPage() DocPage
            +generateDiagramsIndexPage() DocPage
        }
        class DocPage {
            +str id
            +str kind
            +str contentMarkdown
        }
        class DocumentationSet {
            +tuple~DocPage~ pages
        }
        class ClassDiagramSelection {
            +tuple~SelectedClass~ includedClasses
            +tuple~tuple~str,str~~ inheritanceEdges
            +int omittedClassCount
        }
        class SelectedClass {
            +str classId
            +str name
            +tuple~SelectedMethod~ methods
        }
        class SelectedMethod {
            +str name
        }
        class ClassDiagramSource {
            +str sourceText
            +tuple~str~ includedClassIds
            +int omittedClassCount
        }
        class EntryPoint {
            +str symbolId
            +str stableKey
            +str name
            +str moduleKey
            +str className
            +str kind
        }
        class CallStep {
            +int depth
            +str callerSymbolId
            +str calleeSymbolId
            +str calleeName
            +int order
        }
        class SequenceDiagramSelection {
            +EntryPoint entryPoint
            +tuple~CallStep~ steps
            +bool truncatedAtMaxDepth
        }
        class SequenceDiagramSource {
            +str sourceText
            +tuple~str~ participantIds
            +int stepCount
        }
        class Actor {
            +str kind
            +str label
        }
        class UseCase {
            +str entryPointStableKey
            +str label
            +str actorKind
        }
        class UseCaseDiagramSelection {
            +tuple~Actor~ actors
            +tuple~UseCase~ useCases
        }
        class UseCaseDiagramSource {
            +str sourceText
            +tuple~str~ actorNodeIds
            +tuple~str~ useCaseNodeIds
        }
        class DocPageManifestStore {
            <<doc-manifest.sqlite>>
            +load_overview_narrative(repositoryId, narrativeKey)
            +load_latest_overview_narrative(repositoryId)
            +save_overview_narrative(repositoryId, narrativeKey, replyText, handleMap, repositoryFingerprint)
        }
        class FeaturePlanner {
            <<features/planner.py, 033>>
            +plan(candidates, evidence) FeaturePlan
        }
        class RepositoryEvidence {
            <<features/evidence.py, 033 + 039, no engine>>
            +tuple~str~ seedModuleKeys
            +tuple~str~ entryModuleKeys
            +frozenset~str~ testModuleKeys
            +str readmeLead
        }
        class resolve_repository_imports {
            <<function, features/imports.py, 039, no engine>>
            +Java and JS/TS import names to module keys
        }
        class Candidate {
            <<features/candidates.py, no engine>>
            +str seedModuleKey
            +str seedTitle
            +tuple~str~ memberKeys
        }
        class Feature {
            <<features/validate.py, repair>>
            +str key
            +str title
            +tuple~FeatureMember~ members
        }
        class OverviewEvidence {
            <<overview/evidence.py, 038, no engine>>
            +tuple~FeatureBrief~ features
            +tuple~EntryFlow~ entryFlows
            +tuple~str~ majorFeatureKeys
            +str repositoryFingerprint
        }
        class OverviewNarrator {
            <<overview/narrator.py, 038, the only engine-taker>>
            +narrate(evidence) NarrationOutcome
        }
        class GroundedNarrative {
            <<overview/grounding.py, 038, no engine>>
            +tuple~GroundedParagraph~ lead
            +tuple subsystems
            +bool leadWithheld
            +int unwrittenCount
        }
    }
    DocGenerator ..> DocumentationSet : produces
    DocumentationSet *-- DocPage
    ClassDiagramSelection *-- SelectedClass
    SelectedClass *-- SelectedMethod
    DocGenerator ..> ClassDiagramSelection : select_major_classes()
    ClassDiagramSelection ..> ClassDiagramSource : build_class_diagram_mermaid_source()
    SequenceDiagramSelection *-- EntryPoint
    SequenceDiagramSelection *-- CallStep
    DocGenerator ..> SequenceDiagramSelection : identify_entry_points() + build_entry_point_call_sequence()
    SequenceDiagramSelection ..> SequenceDiagramSource : build_sequence_diagram_mermaid_source()
    UseCaseDiagramSelection *-- Actor
    UseCaseDiagramSelection *-- UseCase
    DocGenerator ..> UseCaseDiagramSelection : select_use_cases()
    UseCaseDiagramSelection ..> UseCaseDiagramSource : build_use_case_diagram_mermaid_source()
    DocGenerator --> DocPageManifestStore : page manifest
    DocGenerator ..> RepositoryEvidence : build_repository_evidence()
    DocGenerator ..> resolve_repository_imports : build_import_adjacency()
    resolve_repository_imports ..> DependencyGraph : import node names
    RepositoryEvidence ..> Candidate : build_candidates(evidence, adjacency)
    DocGenerator --> FeaturePlanner : subsystems (repaired features)
    FeaturePlanner ..> Candidate : one call names and combines them
    FeaturePlanner ..> DocPageManifestStore : doc_feature_plans cache, keyed on the grouping
    Feature *-- Candidate : repair
    DocGenerator ..> OverviewEvidence : build_overview_evidence(features, bundle, graph)
    DocGenerator --> OverviewNarrator : overviewNarrator
    OverviewNarrator ..> OverviewEvidence : one prompt
    OverviewNarrator ..> LocalLLMEngine : one call per repository
    OverviewNarrator ..> DocPageManifestStore : doc_overview_narratives cache
    DocGenerator ..> GroundedNarrative : ground(reply, evidence, lookup)

    namespace WebServer {
        class ChatApiApp {
            <<FastAPI app, chat_api/app.py>>
            +POST /sessions
            +POST /sessions/:session_id/messages
            +serves the wiki as static files
        }
    }

    namespace RepoWatcher {
        class RepositoryWatcher {
            +start()
            +stop()
        }
        class ChangeBatch {
            +tuple~FileChange~ changes
            +str origin
        }
        class FileChange {
            +str relative_path
            +ChangeType change_type
        }
    }
    RepositoryWatcher ..> ChangeBatch : on_batch(batch)
    ChangeBatch *-- FileChange

    namespace ReindexPipeline {
        class IncrementalReindexPipeline {
            +run(batch) ReindexOutcome
        }
        class ReindexOutcome {
            +tuple~str~ reprocessedPaths
            +tuple~str~ skippedPaths
            +tuple~str~ removedPaths
            +tuple~str~ regeneratedSymbolIds
            +tuple~str~ failedPaths
            +str summaryFailure
        }
    }
    IncrementalReindexPipeline ..> ReindexOutcome : returns

    namespace Cli {
        class CLIConfiguration {
            +str llmModel
            +str llmEndpointUrl
            +str embeddingModel
            +str embeddingEndpointUrl
            +int summaryConcurrency
            +int embeddingConcurrency
            +model_for_stage(stage) str
        }
        class IndexRunResult {
            +Path docsRoot
            +VectorIndex vectorIndex
            +RepositoryWatcher watcher
        }
        class run_index {
            <<function, index_command.py>>
            +run_index(repo_path, config) IndexRunResult
        }
        class run_serve {
            <<function, serve_command.py>>
            +run_serve(repo_path, config) IndexRunResult
        }
        class run_home {
            <<function, home_command.py>>
            +run_home(host, port)
        }
        class progress_stream {
            <<module, progress_stream.py>>
            +enabled() bool
            +emit(event_type, **fields)
        }
        class run_config {
            <<function, config_command.py>>
            +run_config(llm_model, llm_endpoint, llm_generate_timeout, embedding_model, embedding_endpoint, embedding_generate_timeout, show)
        }
        class scan {
            <<function, main.py>>
            +scan(repo_path) ScanResult
        }
    }
    run_index ..> CLIConfiguration : reads
    run_serve ..> CLIConfiguration : reads
    run_config ..> CLIConfiguration : reads/writes
    run_index ..> IndexRunResult : returns
    run_serve ..> IndexRunResult : returns
    scan ..> ScanResult : scan_repository()

    %% Cross-package data flow
    CLIConfiguration ..> LocalLLMEngine : llmModel/llmEndpointUrl
    CLIConfiguration ..> EmbeddingEngine : embeddingModel/embeddingEndpointUrl
    namespace hub_server {
        class HubState {
            <<app.py>>
            +currentRun RunState
            +servers dict
            +start_run(kind, repository_path, args) RunState
            +cancel_current() RunState
            +shutdown()
        }
        class RunState {
            <<runs.py>>
            +runId str
            +kind str
            +stages list~StageState~
            +outcome str
            +version int
            +apply(event)
            +finish(outcome)
            +snapshot() dict
        }
        class StageState {
            <<runs.py>>
            +name str
            +status str
            +completed int
            +total int
        }
        class ProgressEvent {
            <<progress_parse.py>>
            +seq int
            +type str
            +stage str
            +payload dict
        }
        class ChildProcess {
            <<children.py>>
            +pid int
            +url str
            +start_reader()
            +terminate()
        }
        class RunLog {
            <<run_log.py>>
            +append(run_id, repository_path, kind)
            +close(run_id, outcome)
            +prune(keep)
            +sweep_interrupted() int
            +recent(limit) list~RunRecord~
        }
        class RunRecord {
            <<run_log.py>>
            +runId str
            +outcome str
            +failedStage str
            +failureMessage str
        }
        class HistoryEntry {
            <<history.py>>
            +stateId str
            +repositoryPath str
            +lastIndexedAt str
            +available bool
        }
    }

    run_index ..> LocalLLMEngine : builds the summary and chat engines
    run_index ..> ScanResult : scan_repository()
    run_index ..> DocGenerator : structure + content passes
    run_index ..> CodeSummaryPipeline : summarizeRepository()
    run_index ..> VectorIndex : update_embeddings() per file
    run_serve ..> RepositoryWatcher : on_batch=pipeline.run
    run_serve ..> IncrementalReindexPipeline : constructs
    ScanResult ..> FileSymbolInventory : each file is parsed into
    FileSymbolInventory ..> DependencyGraph : ingest_inventory()
    FileSymbolInventory ..> RepositoryMetadataStore : store_inventory()
    RepositoryBundle ..> CodeSummaryPipeline : symbol source + context
    DependencyGraph ..> CodeSummaryPipeline : dependents() for impact
    CodeSummaryPipeline ..> LocalLLMEngine : generate()
    CodeSummaryPipeline ..> RepositoryMetadataStore : writes summary back
    RepositoryMetadataStore ..> CodeChunk : symbol source text to embed
    EmbeddingEngine ..> CodeChunk : embed()
    VectorIndex ..> ChatSession : search() evidence
    LocalLLMEngine ..> ChatSession : generate() answer
    RepositoryBundle ..> DocGenerator : pages source
    DependencyGraph ..> DocGenerator : diagram pages
    DocumentationSet ..> ChatApiApp : served as static files
    ChatSession ..> ChatApiApp : POST /messages
    ChangeBatch ..> IncrementalReindexPipeline : run(batch)
    IncrementalReindexPipeline ..> FileSymbolInventory : re-parses changed files
    IncrementalReindexPipeline ..> DependencyGraph : targeted update
    IncrementalReindexPipeline ..> RepositoryMetadataStore : targeted update
    IncrementalReindexPipeline ..> CodeSummaryPipeline : targeted regeneration
    IncrementalReindexPipeline ..> VectorIndex : targeted re-embed
    IncrementalReindexPipeline ..> DocGenerator : targeted regeneration
    run_home ..> HubState : creates via create_hub_app()
    HubState ..> RunState : one non-terminal run at a time
    HubState ..> RunLog : records every terminal outcome
    HubState ..> ChildProcess : launches python -m cli index / serve
    ChildProcess ..> run_index : as a child process, never in-process
    ChildProcess ..> run_serve : as a child process, never in-process
    ChildProcess ..> ProgressEvent : parses child stdout
    ProgressEvent ..> RunState : apply(event)
    RunState *-- StageState : ten, in pipeline order
    RunLog ..> RunRecord : returns
    HubState ..> HistoryEntry : scans ~/.codepedia/repos/
    run_index ..> progress_stream : emit() beside every echo
    run_serve ..> progress_stream : emit() beside every echo
```
