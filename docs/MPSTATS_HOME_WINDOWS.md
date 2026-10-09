# HOME Windows: official MPSTATS MCP in Codex

## Architecture

HOME (Windows) runs the **Codex MCP client**, not a second MPSTATS server. It connects directly to the official provider's hosted Streamable HTTP MCP endpoint:

`https://mcp.mpstats.io/mcp` (authenticated query is stored privately on HOME).

This is independent from the already operational REMOTE Linux Codex/Hermes MPSTATS installation and from the separate HOME/WORK marketplace/forecast tools.

Official references:

- https://mpstats.io/instruments/ai/mcp
- https://developers.openai.com/learn/docs-mcp
- https://developers.openai.com/docs/config-file/config-basic

## Target and ownership

- PC: HOME / Windows
- Project root: `C:\MCP-HOME\`
- Codex per-user configuration: `%USERPROFILE%\.codex\config.toml`, unless `CODEX_HOME` is explicitly set.
- Installer source: `scripts/home/install_mpstats_codex.ps1`.
- The installer must run **interactively under the actual Windows Codex user**. Do not run from the `gpt-powershell-home` self-hosted GitHub runner service or under Network Service.
- No HOME installer action may modify the REMOTE server, its token file, its Codex configs, DevExec, Telegram or other skills.

## Procedure

1. Before touching the user's config, run the HOME read-only precheck through the private `gpt-powershell-bridge` on the HOME runner pool, or use the installer `-CheckOnly` locally in the user session. Verify the expected user/profile and whether `mpstats` already exists.
2. If `mpstats` is already present, stop and inspect the existing registration without displaying its authenticated URL. Do not append a duplicate TOML table.
3. Run the installer from the canonical repository in an **interactive PowerShell window** as the Codex user.
4. The user privately enters the **existing personal MPSTATS token** at the hidden prompt. Do not paste it in ChatGPT, GitHub issues, shell command arguments, scripts or transcripts.
5. The installer appends `[mcp_servers.mpstats]` to the user's TOML without editing any other MCP entry. An existing config gets a dated local `config.toml.pre-mpstats-home.*.bak` backup, stored in the same protected user directory.
6. The script checks for concurrent config modification before writing, writes via temporary file, verifies the table without printing the credential and tries a sanitized `codex mcp list --json` check.
7. Restart Codex Desktop / start a fresh Codex CLI session and independently test MCP initialization and `tools/list`. Do not call product/business tools until the connection is accepted.

## Installing from a trusted checked-out repository

From the interactive HOME PowerShell session:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\MCP-HOME\msp-server-stack\scripts\home\install_mpstats_codex.ps1" -CheckOnly
```

Run without `-CheckOnly` to request the token locally and install. The `msp-server-stack` checkout path above is an *example*: first verify that the actual source exists in that HOME folder. The command must not be run from a Windows service account.

If no checkout is present, obtain the verified script from the public canonical GitHub repository as a single file under `C:\MCP-HOME\tools\mpstats\`, inspect it, and run it from the interactive user session. Avoid unreviewed `Invoke-Expression` / web-pipe-to-shell commands.

## What the installer does NOT do

- No separate local MPSTATS server service, Docker, Python MCP daemon, port exposure or Tailscale configuration.
- Does not install the Hermes-specific skill into Windows Codex. This would require adapting a separate Codex skill if semantic guidance is desired.
- Does not print the authenticated URL or the token. Does not automatically generate/rotate a new MPSTATS token.
- Does not copy the protected REMOTE token or any REMOTE config. Do **not** rotate the REMOTE token just to make HOME work; token rotation would invalidate existing connections.
- Does not automatically alter Windows NTFS ACLs or erase existing backups.
- Does not prove live authentication unless a fresh Codex MCP session succeeds.

## Acceptance

- Both previous and newly installed Codex MCP entries appear in the user's normal Codex environment.
- `mpstats` uses the official `streamable_http` transport.
- A fresh Codex session can initialize the provider MCP and retrieve the tool list.
- No token/URL query appears in GitHub/ChatGPT logs or transcripts.
- REMOTE remains unaffected.
