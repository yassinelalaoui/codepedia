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
