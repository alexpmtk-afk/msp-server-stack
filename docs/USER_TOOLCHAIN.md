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
