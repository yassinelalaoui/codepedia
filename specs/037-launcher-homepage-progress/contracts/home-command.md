# Contract: `codepedia home`

**Feature**: 037-launcher-homepage-progress
**Surface**: `src/cli/main.py` (registration), `src/cli/home_command.py`
(behaviour)

## Signature

```
codepedia home [--host TEXT] [--port INTEGER]
```

| Option | Default | Notes |
|---|---|---|
| `--host` | `127.0.0.1` | Same `DEFAULT_HOST` constant `index` and `serve` use |
| `--port` | `8100` | Deliberately **not** `serve`'s `8000`, so a hub and a directly-run `serve` do not collide by default |

No positional argument. That is the point of the command: it is the entry point
you reach for when you do not yet have a repository in mind (FR-001).

Help text: *"Start the Codepedia homepage: analyse a repository and reopen ones
you have analysed before."*

## Behaviour

1. Load configuration via `cli.config.load_config()`, as the other commands do.
2. The disclosure gate runs first. `home` is added to
   `_DISCLOSURE_GATED_COMMANDS` in `cli/main.py:41-43` alongside `index`,
   `serve` and `provider`, because it is an entry point to chain-consuming
   stages (constitution 2.1). Its children re-run the gate for themselves and
   find it already acknowledged.
3. Sweep the run log: any row with a NULL outcome becomes `interrupted`
   (FR-026d, `data-model.md` §2).
4. Build the app via `hub_server.create_hub_app(...)` with a fresh token from
   `chat_api.security.generate_token()` (FR-004).
5. Print the startup lines, then `uvicorn.run(app, host, port)`.
6. On shutdown, terminate every child server the hub started (FR-007).

## Startup output

```
Codepedia homepage available at http://127.0.0.1:8100/?token=<token>
Keep that URL private: the token authorizes starting and removing analyses on this machine.
```

The wording deliberately parallels `chat_api.security.startup_lines` and states
what this token authorises, which is more than the wiki's does — the hub can
start a long-running job against any path and delete stored analyses.

When `--host` is not loopback, a third line is printed, reusing
`is_loopback_host`:

```
WARNING: bound to <host>, so this server is reachable from other machines on the network. Anyone who obtains the token above can start and remove analyses on this machine.
```

The command does **not** open a browser by itself; it prints the address, as
`index` and `serve` do.

## Errors

| Condition | Behaviour |
|---|---|
| Port in use | `ServerBindError` through `report_and_exit`, exactly as `start_local_server` handles it (`cli/server.py:47-53`) — including uvicorn's `SystemExit`-on-bind-failure quirk |
| Disclosure not acknowledged | The existing gate's behaviour, unchanged |
| `Ctrl-C` | Clean shutdown: children terminated, current run's log row closed as `cancelled` |

## What this command does not do

- It does not analyse anything itself. It launches `python -m cli index` as a
  child (research §1).
- It does not serve any wiki. It launches `python -m cli serve` as a child and
  links to it (research §7).
- It does not read or write `~/.codepedia/config.json` (FR-025).

## Regression guarantee

`scan`, `index`, `serve`, `config` and `provider` are unchanged: same arguments,
same output, same exit codes, same effects (FR-002). The edits those commands
receive are additive and gated on `CODEPEDIA_PROGRESS_STREAM`
(`contracts/run-progress-stream.md`), which `home` sets only on its children.

`src/cli/__main__.py` is added so `python -m cli <command>` works. It contains
only `from cli.main import app; app()` and changes no existing behaviour. It is
preferred over the installed `codepedia` console script because that script is
an `exe` launcher with the interpreter path baked in, which breaks if the
virtualenv is renamed.
