"""Make `python -m cli <command>` work.

The hub launches the real CLI as a child process (research.md §1), and it does
so through the interpreter rather than through the installed `codepedia`
console script: that script is a generated `exe` launcher with the interpreter's
absolute path baked in, so it stops working the moment the virtualenv is
renamed. `sys.executable -m cli` has no such dependency.

Purely additive - nothing that exists today changes behaviour because this file
appeared (contracts/home-command.md).
"""

from __future__ import annotations

from cli.main import app

if __name__ == "__main__":
    app()
