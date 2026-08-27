import { useEffect } from "react";

/**
 * Highlights the section the reader is currently in, inside the server-rendered
 * "On this page" rail.
 *
 * The rail itself is emitted by `doc_generator`'s Jinja layout, not by React:
 * it is plain navigation markup that works with no JavaScript and over
 * `file://`, matching how the sidebar's module list is already rendered. This
 * component owns nothing visible - it renders `null` and only toggles an
 * `active` class - so the rail is never blanked or re-rendered underneath it.
 *
 * Anchors come from python-markdown's `toc` extension, which assigns an id to
 * every heading, so every rail link resolves to a real element.
 */
export function TocHighlighter(): null {
  useEffect(() => {
    const rail = document.querySelector(".page-toc");
    if (!rail) return;

    const links = Array.from(rail.querySelectorAll<HTMLAnchorElement>("a.page-toc-link"));
    const linkById = new Map<string, HTMLAnchorElement>();
    const headings: HTMLElement[] = [];

    for (const link of links) {
      const href = link.getAttribute("href") ?? "";
      if (!href.startsWith("#")) continue;
      const id = decodeURIComponent(href.slice(1));
      const heading = id ? document.getElementById(id) : null;
      if (!heading) continue;
      linkById.set(id, link);
      headings.push(heading);
    }

    // No rail entries resolved, or a runtime without IntersectionObserver (jsdom
    // under test, or a very old browser): the rail still navigates, it just
    // won't track scrolling.
    if (headings.length === 0 || typeof IntersectionObserver === "undefined") return;

    const visible = new Set<string>();

    const applyActive = (): void => {
      // Document order decides: the first heading currently inside the
      // detection band is the section the reader is in.
      const active = headings.find((heading) => visible.has(heading.id));
      if (!active) return;
      for (const [id, link] of linkById) {
        link.classList.toggle("active", id === active.id);
      }
    };

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = (entry.target as HTMLElement).id;
          if (entry.isIntersecting) visible.add(id);
          else visible.delete(id);
        }
        applyActive();
      },
      // Narrows the viewport to a band near the top, so the active entry
      // changes as a heading reaches the top rather than when it merely enters
      // the screen.
      { rootMargin: "0px 0px -70% 0px" },
    );

    for (const heading of headings) observer.observe(heading);

    // StrictMode runs effects twice in development and under Vitest; without
    // this the second run would leave the first observer attached.
    return () => observer.disconnect();
  }, []);

  return null;
}
