import type { ComponentPropsWithoutRef, ReactNode } from "react";
import type { ExtraProps } from "react-markdown";
import type { Options as RehypeHighlightOptions } from "rehype-highlight";
import go from "highlight.js/lib/languages/go";
import java from "highlight.js/lib/languages/java";
import javascript from "highlight.js/lib/languages/javascript";
import kotlin from "highlight.js/lib/languages/kotlin";
import python from "highlight.js/lib/languages/python";
import rust from "highlight.js/lib/languages/rust";
import typescript from "highlight.js/lib/languages/typescript";
import { findByCitation, type SearchIndexEntry } from "./searchIndex";

export interface ParsedReference {
  filePath: string;
  symbolId: string;
}

const REFERENCE_SEPARATOR = " :: ";

/**
 * Recognizes the `<filePath> :: <symbolId>` inline-reference shape the
 * system prompt (`chat/prompting.py`) already asks the model to produce
 * (contracts/inline-symbol-reference-rendering.md). Splits on the first
 * literal " :: " only, so a symbol id that itself contains "::" (e.g.
 * `Class :: method`) stays intact on the symbol-id side. Either side being
 * empty (or no separator at all) means this isn't a reference.
 */
export function parseReference(text: string): ParsedReference | null {
  const separatorIndex = text.indexOf(REFERENCE_SEPARATOR);
  if (separatorIndex === -1) return null;

  const filePath = text.slice(0, separatorIndex).trim();
  const symbolId = text.slice(separatorIndex + REFERENCE_SEPARATOR.length).trim();
  if (!filePath || !symbolId) return null;

  return { filePath, symbolId };
}

/**
 * Curated highlight.js language subset (research.md Decision 2) matching
 * what this project's own parser actually detects
 * (`repo_scanner/language.py` `COMMON_LANGUAGE_MAP`), instead of bundling
 * highlight.js's full ~190-language registry into the client bundle.
 * `detect: true` also highlights fenced blocks with no language tag, using
 * only this subset - see rehype-highlight's `subset`/`detect` semantics.
 */
export const rehypeHighlightOptions: RehypeHighlightOptions = {
  detect: true,
  languages: { python, javascript, typescript, java, kotlin, go, rust },
};

type CodeProps = ComponentPropsWithoutRef<"code"> & ExtraProps;

function textContentOf(children: ReactNode): string {
  if (typeof children === "string") return children;
  if (typeof children === "number") return String(children);
  if (Array.isArray(children)) return children.map(textContentOf).join("");
  return "";
}

/**
 * react-markdown `code` component override. Block code - inside a `<pre>` -
 * is always marked with an `hljs` class by rehype-highlight (it only ever
 * touches `code` elements whose parent is `pre`; inline code never gets
 * that class), so that's a reliable signal to leave the highlighter's own
 * markup as-is. Inline code is checked against the inline-reference format
 * and resolved through the exact same `findByCitation` lookup the separate
 * citation list already uses (contracts/inline-symbol-reference-rendering.md):
 * resolved -> a link to the documentation page; anything else (no match, or
 * a match that doesn't resolve, including one still incomplete mid-stream)
 * -> plain inline code, never a broken link or dropped content.
 */
export function createSymbolAwareCodeRenderer(entries: SearchIndexEntry[]) {
  return function SymbolAwareCode({ className, children, node: _node, ...rest }: CodeProps) {
    const isBlockCode = typeof className === "string" && /\bhljs\b/.test(className);
    if (isBlockCode) {
      return (
        <code className={className} {...rest}>
          {children}
        </code>
      );
    }

    const parsed = parseReference(textContentOf(children));
    const resolved = parsed
      ? findByCitation(entries, { symbolId: parsed.symbolId, filePath: parsed.filePath })
      : undefined;

    if (parsed && resolved) {
      return <a href={resolved.pageUrl}>{resolved.name}</a>;
    }

    return (
      <code className={className} {...rest}>
        {children}
      </code>
    );
  };
}
