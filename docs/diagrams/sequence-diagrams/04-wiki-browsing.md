# Major Function: Browse the Wiki, Search, and Navigate a Dependency Diagram

**Specs**: 012, 013, 015, 016

The everyday reading experience: open the wiki, find a symbol by name, or explore how
modules connect to each other by clicking through a live diagram.

```mermaid
sequenceDiagram
    actor Reader as "Team member (browser)"
    participant Server as "Local Web Server (015)"
    participant WikiUI as "Wiki UI\n(SearchWidget / diagram, 013/016)"
    participant SearchIndex as "search-index.json (012)"

    Reader->>Server: GET / (wiki home page)
    Server-->>Reader: home.html (architecture overview,\nmodule links)
    Reader->>WikiUI: loads wiki-ui.js

    par Search for a symbol
        Reader->>WikiUI: type a query into SearchWidget
        WikiUI->>SearchIndex: fetch + query assets/search-index.json
        SearchIndex-->>WikiUI: matching entries (name, kind, page url)
        WikiUI-->>Reader: results list (or "no results")
        Reader->>Server: click a result -> GET <symbol's page>.html
        Server-->>Reader: module page
    and Explore a dependency diagram
        Reader->>Server: GET <module>/diagram.html
        Server-->>Reader: page embedding a Mermaid flowchart\n(nodes = related modules, click targets set)
        Reader->>WikiUI: click a node in the diagram
        WikiUI->>Server: navigate to that node's href
        Server-->>Reader: the related module's page
    end
```
