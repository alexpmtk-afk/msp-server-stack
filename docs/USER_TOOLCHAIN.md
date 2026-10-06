# REMOTE user-level admin toolchain

This stack intentionally keeps Hermes' production Python environment separate from ordinary administration and tests.

The user-level toolchain installer exposes already bundled Hermes tools through `/home/hermes/.local/bin` and creates a dedicated test virtual environment.

Installed/exposed commands:

- `pip`, `pip3` — Hermes bundled Python package installer;
- `uv`, `uvx` — Hermes bundled uv;
- `rg` — Hermes bundled ripgrep;
- `sqlite3` — Python 3.14 sqlite3 CLI wrapper;
- `pytest` — dedicated isolated test environment.

The installer does not modify system Python, does not use sudo, and does not install Docker or compiler toolchains.

System packages such as `build-essential` should be installed separately by an authorized root/admin path only when a project actually requires native compilation.

Install:

~~~bash
bash scripts/bootstrap/install-user-toolchain.sh
~~~


## Installed state — 2026-10-06

Verified on REMOTE under user `hermes`:

- `pip` / `pip3`: 26.2.1
- `uv` / `uvx`: 0.12.3
- `rg`: ripgrep 15.2.0
- `sqlite3`: Python 3.14 sqlite CLI, SQLite library 3.53.1
- `pytest`: 9.1.1 in dedicated isolated venv

Independent smoke tests:

- SQLite create/insert/select: PASS
- pytest one-test run: PASS

The commands are exposed through `/home/hermes/.local/bin`, which is already part of the Hermes service PATH.

System-level compiler packages (`build-essential`, native `gcc/g++/make`) remain intentionally uninstalled because the REMOTE runner has no non-interactive sudo. They are not required for the current Hermes/Codex/Telegram workflow.
