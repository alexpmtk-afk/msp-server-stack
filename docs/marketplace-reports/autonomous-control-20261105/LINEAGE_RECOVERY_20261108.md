# WB Laser Master lineage processing repair — 2026-11-08

## Observed production failure

After the previous installed recovery, 18 more verified reports / 19894 rows completed. Request82bf1ab2ecf94c79810d82f739232c84 returned PARTIAL/STOP_OR_UNCERTAIN; worker ran 03:31:47–03:38:47 MSK and hit its420s watchdog with378.66CPU seconds. Its following read-only diagnostic hit300s with284.77CPU seconds. These are CPU-heavy local-processing timeouts, not evidence of an API rejection. The previous diagnostic for nonce2bb9147b19af49748dad35ab348c38ee attested report812549574/type1:1434 rows/2 pages, terminal204,3 sealed requests, no unknowns. That older diagnostic does not authorize another wake. The new helper requires a fresh root diagnostic bound to the exact current failed claim before continuing.

## Cause and change

Every read_active re-parsed the complete historical annual snapshots in _lineage, so accumulated history multiplied CSV semantic work. A fresh process had no prior semantic cache. A profiler on a valid synthetic24-generation/6000-current-row chain attributes4.787s of5.245s to ancestry and24 semantic payload validations. This identifies a scaling defect in the live code path; no past terminating stack was available, so it is not proof of the exact instruction at watchdog termination.

WB ancestry now streams and hashes every historical payload against the CURRENT-anchored descriptor chain, checking identities, bytes, paths, missing files and parent hashes. Historical payloads are not retained or semantically re-parsed simply to prove ancestry. Current data still undergo full semantic validation; explicitly reading an old snapshot also fully validates the selected old payload. This deliberately separates ancestry integrity from requested-snapshot semantics; it is not a persisted cache or skipping ancestry hashes. Ozon ancestry behavior is unchanged. All budgets, pacing, credentials, network policy and watchdogs remain unchanged.

Same synthetic fixture after change:1.205s,4.35x faster, identical returned current CSV SHA256. This is not a measured production speedup. Full local marketplace suite:364 tests,2 skipped. Added tests prove ancestor-byte corruption, missing ancestor files, descriptor repack and selected-history semantic validation. Existing28 generation integrity/publication tests pass.

## Package and continuation

LINEAGE_MANIFEST.json pins the reviewed37-file installed baseline and every new payload hash. Only generation_store.py differs among installed app modules. The updater is the existing reviewed immutable wiring installer: root-owned staged snapshot, old-payload drift refusal, immutable new release, wiring backup, no archive/budget edits, no provider execution. It releases its controller lock before the read-only diagnostic.

Use only ROOT_LINEAGE_REPAIR_AND_RESUME.txt, not the historical memory/discovery commands. The helper is unprivileged and pins the new root controller and exact nonce82bf.../report812549574/type1. It checks fresh root terminal/publication evidence, known HTTP outcomes and original sealed budget through the same bounded recovery predicate; preserves state and wrapper backups, counters and budgets; writes a scoped pinned driver, recovers to cooldown, and starts only the existing WB Laser Master campaign. It does not perform provider requests or wait in the operator console for the whole campaign. A repeated invocation after admission is rejected. Unknown outcomes/corruption/different claims remain HOLD.

Status at packaging: NOT INSTALLED; no production resume attempted. After owner installation, verify exact next root receipt, confirmed local publication, unchanged original budget and advancement to a subsequent report before claiming recovery. Not all history is confirmed yet.


## Installed production verification

The owner installed control638be59c983a0b6769d149cc1d577799a6aec346dabb8e83ed6d9aa18c7ac508. Fresh read-only root proof for exact failed nonce82bf1ab2ecf94c79810d82f739232c84 verified report812549574/type1:1434 rows, publication/page hashes valid, original budget3/DONE, known200/200/204, no unknown outcomes. Handoff had not executed; Hermes ran the pinned unprivileged helper once after verifying idle units and the fresh proof. Original campaign resumed, retaining counters and budgets.

Next root receipt9df75b19c3224027a12db6d77e76577c is PASS: report812549544/type2,46 rows, one saved page,2 HTTP attempts200/204,unknown0,budget2,publication/page hashes verified. Original scoped driver active in normal COOLDOWN, wake93. This verifies genuine continuation beyond the interrupted report, not merely service startup. All historical reports remain unconfirmed pending final inventory reconciliation; no claim of measured whole-process4.35x production improvement or permanent absence of failures.
