import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { captureHubOriginFromUrl, hubHomeUrl, installHubHomeLinks } from "../src/lib/hubLink";

/**
 * Getting back to the homepage from inside a wiki.
 *
 * The wiki is generated before any hub exists, so the link has to be told where
 * home is at runtime - or fall back to the documented default port.
 */

// A path, not an absolute URL: jsdom refuses a cross-origin replaceState,
// and only the query string matters to anything under test here.
const WIKI_URL = "/index.html";

function navigate(href: string): void {
  window.history.replaceState(null, "", href);
}

beforeEach(() => {
  window.sessionStorage.clear();
  navigate(WIKI_URL);
  document.body.innerHTML = "";
});

afterEach(() => {
  window.sessionStorage.clear();
});

describe("hubHomeUrl", () => {
  it("falls back to the documented default port when nothing was captured", () => {
    // A wiki opened by `codepedia serve` directly was never told where the hub
    // is. A link to the default beats no way back at all.
    expect(hubHomeUrl()).toBe("http://127.0.0.1:8100/");
  });

  it("uses the origin the hub sent, so a non-default port still works", () => {
    navigate(`${WIKI_URL}?hub=${encodeURIComponent("http://127.0.0.1:9321/")}`);

    captureHubOriginFromUrl();

    expect(hubHomeUrl()).toBe("http://127.0.0.1:9321/");
  });

  it("remembers it across pages of the same wiki", () => {
    navigate(`${WIKI_URL}?hub=${encodeURIComponent("http://127.0.0.1:9321/")}`);
    captureHubOriginFromUrl();

    navigate("/features/thing.html");

    expect(hubHomeUrl()).toBe("http://127.0.0.1:9321/");
  });
});

describe("captureHubOriginFromUrl", () => {
  it("strips the parameter from the address bar", () => {
    navigate(`${WIKI_URL}?hub=${encodeURIComponent("http://127.0.0.1:9321/")}`);

    captureHubOriginFromUrl();

    expect(window.location.search).not.toContain("hub=");
  });

  it("leaves other parameters alone", () => {
    navigate(`${WIKI_URL}?chatSession=abc&hub=${encodeURIComponent("http://127.0.0.1:9321/")}`);

    captureHubOriginFromUrl();

    expect(window.location.search).toContain("chatSession=abc");
    expect(window.location.search).not.toContain("hub=");
  });

  it("is safe to call more than once", () => {
    navigate(`${WIKI_URL}?hub=${encodeURIComponent("http://127.0.0.1:9321/")}`);

    captureHubOriginFromUrl();
    captureHubOriginFromUrl();

    expect(hubHomeUrl()).toBe("http://127.0.0.1:9321/");
  });

  it.each([
    ["javascript:alert(1)", "a script URL"],
    ["http://evil.example.com/", "a remote host"],
    ["https://192.168.1.50/", "another machine on the network"],
    ["file:///C:/Windows/", "a filesystem path"],
    ["not a url at all", "gibberish"],
  ])("refuses %s (%s) and keeps the default", (hostile) => {
    // The value arrives in a URL, and a wiki renders Markdown built from the
    // documented repository - so a crafted link must not be able to turn the
    // product's own brand into a jump somewhere else.
    navigate(`${WIKI_URL}?hub=${encodeURIComponent(hostile)}`);

    captureHubOriginFromUrl();

    expect(hubHomeUrl()).toBe("http://127.0.0.1:8100/");
  });

  it("accepts localhost as well as the loopback address", () => {
    navigate(`${WIKI_URL}?hub=${encodeURIComponent("http://localhost:8100/")}`);

    captureHubOriginFromUrl();

    expect(hubHomeUrl()).toBe("http://localhost:8100/");
  });
});

describe("installHubHomeLinks", () => {
  it("repoints every marked anchor at the homepage", () => {
    document.body.innerHTML = `
      <a id="brand" href="index.html" data-hub-home>codepedia</a>
      <a id="nav" href="index.html" data-hub-home>Home</a>
      <a id="overview" href="index.html">Overview</a>
    `;

    installHubHomeLinks();

    expect(document.querySelector<HTMLAnchorElement>("#brand")!.href).toBe("http://127.0.0.1:8100/");
    expect(document.querySelector<HTMLAnchorElement>("#nav")!.href).toBe("http://127.0.0.1:8100/");
  });

  it("leaves the wiki's own links alone", () => {
    // Repointing "Home" must not cost the overview page its place in the nav.
    document.body.innerHTML = `<a id="overview" href="index.html">Overview</a>`;

    installHubHomeLinks();

    expect(document.querySelector<HTMLAnchorElement>("#overview")!.href).toContain("index.html");
  });

  it("uses the captured origin when there is one", () => {
    navigate(`${WIKI_URL}?hub=${encodeURIComponent("http://127.0.0.1:9321/")}`);
    captureHubOriginFromUrl();
    document.body.innerHTML = `<a id="brand" href="index.html" data-hub-home>codepedia</a>`;

    installHubHomeLinks();

    expect(document.querySelector<HTMLAnchorElement>("#brand")!.href).toBe("http://127.0.0.1:9321/");
  });

  it("survives storage being unavailable", () => {
    const storage = window.sessionStorage;
    Object.defineProperty(window, "sessionStorage", {
      configurable: true,
      value: {
        getItem() {
          throw new Error("denied");
        },
        setItem() {
          throw new Error("denied");
        },
      },
    });

    try {
      document.body.innerHTML = `<a id="brand" href="index.html" data-hub-home>codepedia</a>`;
      expect(() => installHubHomeLinks()).not.toThrow();
      expect(document.querySelector<HTMLAnchorElement>("#brand")!.href).toBe("http://127.0.0.1:8100/");
    } finally {
      Object.defineProperty(window, "sessionStorage", { configurable: true, value: storage });
    }
  });
});
