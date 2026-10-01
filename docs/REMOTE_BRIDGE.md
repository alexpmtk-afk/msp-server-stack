# REMOTE BRIDGE

## Purpose

The standard ChatGPT-to-REMOTE execution transport is a dedicated private GitHub bridge:

```text
ChatGPT
  |
  v
private repository: msp-server-bridge
  |
  v
GitHub Actions
  |
  v
self-hosted Linux runner on REMOTE
  |
  v
approved local scripts / services
  |
  v
REMOTE verification result
```

The bridge is transport only. Application logic and reproducible server configuration stay in the public `msp-server-stack` repository.

## Repository split

### Public: `msp-server-stack`

Contains:

- architecture and recovery documentation;
- safe configuration templates;
- service inventory;
- versioned server-side scripts;
- health-check and deployment logic;
- no live credentials.

### Private: `msp-server-bridge`

Contains:

- GitHub Actions workflows used to request REMOTE operations;
- runner labels and routing logic;
- minimal execution wrappers;
- no production application secrets.

The private repository is not a secret store. Runner registration tokens, application credentials, SSH keys and service secrets remain outside Git.

## Runner location

The self-hosted runner is installed on the REMOTE Linux server and registered only to `msp-server-bridge`.

Recommended logical label:

`msp-remote`

Jobs should target the generic label instead of a specific runner identity.

## Initial acceptance test

The first bridge test is read-only and returns only non-secret system information:

```text
whoami
hostname
uname -a
test -d /opt/mcp
```

PASS requires all of the following:

1. GitHub schedules the job to the REMOTE runner.
2. The runner executes on the intended server.
3. The output is returned to GitHub Actions.
4. `/opt/mcp` is visible.
5. No secret value is printed.

## Safety model

Read-only diagnostics are the default.

State-changing actions must:

1. name the target service/project explicitly;
2. use version-controlled scripts from `msp-server-stack` where practical;
3. avoid arbitrary secret output;
4. serialize writes to the same production target;
5. run an independent acceptance check after the change.

## Secret handling

Never commit or print:

- runner registration tokens;
- API keys;
- application `.env` contents;
- private keys;
- Telegram sessions;
- proxy/VPN/tunnel credentials;
- credential-bearing URLs.

The GitHub runner authentication state stays on REMOTE in the runner installation directory and GitHub account configuration.

## Recovery

If REMOTE is replaced:

1. prepare the new Linux server;
2. restore `/opt/mcp` structure and required protected data;
3. install a fresh self-hosted runner;
4. register it to private `msp-server-bridge` with label `msp-remote`;
5. run the read-only bridge acceptance test;
6. only then enable state-changing workflows.
