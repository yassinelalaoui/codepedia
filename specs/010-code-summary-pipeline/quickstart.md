# Quickstart: Local Code Summary Pipeline

## Prerequisites

- Python 3.11 or later
- Local project dependencies installed
- Local LLM running on `http://localhost:11434`
- A local model available for summary generation
- A sample repository with modules and public functions

## Validate readiness

1. Start the local LLM service.
2. Confirm the configured model is available locally.
3. Call the pipeline readiness check.
4. Confirm the pipeline reports ready before processing any symbol.

## Validate full summary generation

1. Index a sample repository containing at least one module and one public
   function.
2. Run the summary pipeline against the indexed repository.
3. Load the persisted repository metadata.
4. Confirm each in-scope module has a non-empty generated summary.
5. Confirm each public significant function has a non-empty generated summary.
6. Confirm the summary content reflects the symbol's role in the sample code.

## Validate incremental regeneration

1. Change one source file in the sample repository.
2. Re-run the incremental summary pipeline.
3. Confirm only the impacted symbols receive new summaries.
4. Confirm unchanged symbols keep their previous summaries.

## Validate failure behavior

1. Stop the local LLM service.
2. Run the pipeline readiness check again.
3. Confirm the pipeline reports that the local model is unavailable.
4. Confirm the pipeline stops before processing any symbol.

## Expected result

The pipeline generates local summaries for in-scope modules and public
significant functions, updates only impacted summaries after a change, and
fails fast when the local model is not available.
