# REMOTE MPSTATS semantic skill deployment — 2026-10-08

## Purpose

Record the non-secret deployment state of the Hermes MPSTATS semantic skill.

## Canonical source

- repository: `alexpmtk-afk/msp-server-stack`
- commit: `64e0d20c4e48c269a5545acb4956e3106dab5714`
- source skill: `apps/hermes/mpstats_skill/SKILL.md`
- installer: `scripts/deploy/install-mpstats-skill.sh`

## REMOTE target

```text
/home/hermes/.hermes/skills/productivity/mpstats/
├── SKILL.md
└── references/
    ├── catalog.json
    ├── deployment.json
    ├── live-tools.md
    ├── response_shapes.json
    ├── routing.json
    ├── semantic-layer.md
    └── tool_policy.json
```

## Acceptance

Deployment workflow result: **PASS**.

Verified:

- runner user: `hermes`;
- semantic JSON parse: PASS;
- installed skill contract: PASS;
- skill owner: `hermes:hermes`;
- skill/reference files: mode 0644;
- deployment metadata records no secrets;
- `hermes-gateway.service`: active after deployment;
- `hermes-dashboard.service`: active after deployment.

No service restart was required.

## Meaning

The semantic layer is no longer GitHub-only. It is installed in the same Hermes custom-skill tree pattern used by the existing QRsite skill.

This proves deployment/availability on disk. It does not yet prove behavioral use in a real model turn. Behavioral acceptance should verify that a fresh agent task:

1. recognizes MPSTATS as an analytical source;
2. applies internal product/self-purchase/price-history precedence;
3. does not treat stateful or creative tools as passive reads;
4. respects date/freshness rules;
5. does not use analytical evidence as execution proof.
