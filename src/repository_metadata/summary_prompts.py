from __future__ import annotations

from local_llm import PromptEnvelope

from .summary_context import SummaryContext


SYSTEM_PROMPT = (
    "You summarize repository code locally. "
    "Return a concise natural-language description of the symbol's role. "
    "Do not mention unavailable context or external services. "
    "Whenever you name a specific class, function, method, or file from this repository, "
    "wrap it in backticks exactly as it appears (e.g. `ClassName`, `some_function`, "
    "`src/path/to/file.py`) so the wiki can link it to its own page."
)


def build_module_summary_prompt(context: SummaryContext) -> PromptEnvelope:
    return _build_summary_prompt(context, symbol_label="module")


def build_class_summary_prompt(context: SummaryContext) -> PromptEnvelope:
    return _build_summary_prompt(context, symbol_label="class")


def build_function_summary_prompt(context: SummaryContext) -> PromptEnvelope:
    return _build_summary_prompt(context, symbol_label="function")


# A documentation file's symbols are headings, so the code-shaped framing above
# ("Source code:", "Direct callers:") would ask the model to analyse prose as if
# it were an implementation. Same envelope, different words.
PROSE_LABELS = {"module": "documentation file", "class": "documentation section", "function": "documentation subsection"}


def build_prose_summary_prompt(context: SummaryContext) -> PromptEnvelope:
    return _build_summary_prompt(
        context, symbol_label=PROSE_LABELS.get(context.symbolKind, "documentation section"), is_prose=True
    )


def _build_summary_prompt(context: SummaryContext, *, symbol_label: str, is_prose: bool = False) -> PromptEnvelope:
    imports = "\n".join(f"- {item}" for item in context.imports) or "- none"
    callers = "\n".join(f"- {item}" for item in context.directCallers) or "- none"
    metadata_lines = "\n".join(f"- {key}: {value}" for key, value in sorted(context.metadata.items())) or "- none"
    if is_prose:
        prompt_text = (
            f"Write a concise summary for this {symbol_label}.\n"
            f"Say what the documentation covers and who it is for.\n"
            f"Summarize only what the text states; do not infer implementation details.\n\n"
            f"Heading: {context.symbolName}\n"
            f"Source file: {context.sourceFilePath}\n\n"
            f"Referenced by:\n{callers}\n\n"
            f"Content:\n{context.sourceText.strip()}\n"
        )
    else:
        prompt_text = (
            f"Write a concise summary for this {symbol_label}.\n"
            f"Focus on what the symbol does in the repository.\n"
            f"Avoid speculation.\n\n"
            f"Symbol name: {context.symbolName}\n"
            f"Source file: {context.sourceFilePath}\n"
            f"Docstring: {context.docstring or 'none'}\n\n"
            f"Imports:\n{imports}\n\n"
            f"Direct callers:\n{callers}\n\n"
            f"Metadata:\n{metadata_lines}\n\n"
            f"Source code:\n{context.sourceText.strip()}\n"
        )
    return PromptEnvelope(
        promptText=prompt_text.strip(),
        systemPrompt=SYSTEM_PROMPT,
        context=(
            f"symbolId={context.symbolId}",
            f"symbolKind={context.symbolKind}",
            f"sourceFileId={context.sourceFileId}",
        ),
    )
