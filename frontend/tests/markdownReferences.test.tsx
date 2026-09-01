import { describe, expect, it } from "vitest";
import { parseReference } from "../src/lib/markdownReferences";
import { findByCitation, type SearchIndexEntry } from "../src/lib/searchIndex";

const ENTRIES: SearchIndexEntry[] = [
  {
    name: "authenticate_user",
    kind: "function",
    symbolId: "auth.authenticate_user",
    filePath: "src/auth/login.py",
    pageUrl: "modules/login-a1.html#function_a1",
  },
];

describe("parseReference", () => {
  it("splits a well-formed `path :: symbolId` reference on the first ' :: '", () => {
    expect(parseReference("src/auth/login.py :: auth.authenticate_user")).toEqual({
      filePath: "src/auth/login.py",
      symbolId: "auth.authenticate_user",
    });
  });

  it("returns null for text with no ' :: ' separator", () => {
    expect(parseReference("just some plain inline code")).toBeNull();
  });

  it("returns null when the file-path side is empty", () => {
    expect(parseReference(" :: auth.authenticate_user")).toBeNull();
  });

  it("returns null when the symbol-id side is empty", () => {
    expect(parseReference("src/auth/login.py :: ")).toBeNull();
  });

  it("splits on the first ' :: ' only, leaving any further occurrence on the symbol-id side", () => {
    expect(parseReference("src/auth/login.py :: Class :: method")).toEqual({
      filePath: "src/auth/login.py",
      symbolId: "Class :: method",
    });
  });

  it("resolves a parsed reference through the existing findByCitation lookup, symbol id first", () => {
    const parsed = parseReference("src/auth/login.py :: auth.authenticate_user");
    expect(parsed).not.toBeNull();
    const resolved = findByCitation(ENTRIES, { symbolId: parsed!.symbolId, filePath: parsed!.filePath });
    expect(resolved?.pageUrl).toBe("modules/login-a1.html#function_a1");
  });

  it("leaves an unresolvable parsed reference unresolved rather than guessing", () => {
    const parsed = parseReference("src/unknown.py :: Unknown.thing");
    expect(parsed).not.toBeNull();
    const resolved = findByCitation(ENTRIES, { symbolId: parsed!.symbolId, filePath: parsed!.filePath });
    expect(resolved).toBeUndefined();
  });
});

describe("findByCitation across documentation entries", () => {
  const DOC_ENTRIES: SearchIndexEntry[] = [
    {
      name: "docs/architecture",
      kind: "document",
      symbolId: "module_d1",
      filePath: "docs/architecture.md",
      pageUrl: "modules/architecture-d1.html",
    },
    {
      name: "Storage",
      kind: "section",
      symbolId: "class_d2",
      filePath: "docs/architecture.md",
      pageUrl: "modules/architecture-d1.html#class_d2",
    },
  ];

  it("resolves a file-only citation to a documentation page", () => {
    // The file-path fallback used to match `kind === "module"` alone, so once
    // prose stopped being published as a module every citation pointing at a
    // documentation file silently stopped resolving to a link.
    const resolved = findByCitation(DOC_ENTRIES, { filePath: "docs/architecture.md" });
    expect(resolved?.pageUrl).toBe("modules/architecture-d1.html");
  });

  it("still prefers a symbol id over the file-level entry", () => {
    const resolved = findByCitation(DOC_ENTRIES, { symbolId: "class_d2", filePath: "docs/architecture.md" });
    expect(resolved?.pageUrl).toBe("modules/architecture-d1.html#class_d2");
  });
});
