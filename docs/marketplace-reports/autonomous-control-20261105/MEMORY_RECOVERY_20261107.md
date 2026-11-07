# Repeated WB timeout: bounded-memory validation/publication and local recovery

Observed current nonce0983f5a05a704fdebc8579ec9aa48bd1; original report743994450/type1
resolved from original prior plan digest7970e28702cdfbce64fbe0fd78b591c6051273df092aa488e13caf0b0c42a239.
User driver stopped at wake60 with TimeoutExpired after1100s, while root service
allows1000s plus150s cleanup (actual root exit1104s after start). Thus the client
could abandon a still-finishing protected operation. Root peak2417758208bytes on
a4GB host; current swap use3247MB supports memory-pressure investigation, but
exact historical per-stage stack/HTTP results remain unavailable to Hermes.
Existing installed diagnostic returned HOLD at SELECT_REPORT_READ_ONLY, not a
provider rejection. No new provider request or ledger reset was made in repair.

Changes:
- WB generation schema validation streams CSV cells, retaining stable keys only;
  complete shape/identity/count/hash/lineage checks remain. Ozon unchanged.
- Receipt snapshots retain compressed per-report CSV, not annual dictionaries;
  full-byte verification and all selected staged financial values remain checked.
- WB annual merge streams existing records, retaining only incoming report;
  stable-key conflicts refused; row order retained, new keys appended deterministically.
- Publication and coverage verification retain only selected report rows.
- Valid terminal stages missing publication are STAGED_PUBLICATION_PENDING only
  if original sealed budget is not DONE and no conflicting published report
  exists. Already-DONE missing publication and all other corruption remain HOLD.
- Worker finalizes that stage with a factory that unconditionally refuses network;
  original cumulative admission unchanged. Verified terminal HOLDs preserve prior
  error/seal provenance and use the same local-only path, not a new download.
- Client outer wait1800s covers root1000s plus stop/post-stop cleanup. Inner service
  watchdogs and provider pacing/budgets unchanged.
- Upgrader releases its controller lock before invoking shared-lock diagnostics.
- Read-only diagnostics export the exact current claim, budget/all-nonce HTTP,
  pages and detailed receipt, even if normal selection is held.
- Dedicated resume requires root fresh exact evidence, valid terminal pages,
  known200*/204 with matching original attempts/counters and zero unknowns, exact
  previous normal-pause receipt/current nonce, pinned installed code and idle
  closed-network units. Unknown or corrupt outcomes remain blocked, never reset.

Offline acceptance:357 tests,2 skipped. Actual overlay harness kills publication
after terminal204, proves pending classification, negative corrupted-page HOLD,
then local replay with a forbidden sender factory and unchanged spent count.
Synthetic20000row/50field index benchmark:161451642bytes old vs72247362bytes new
peak allocation (55.3% lower),2.395s vs1.745s. This is not production acceptance.

Root command: ROOT_MEMORY_REPAIR_AND_RESUME.txt. Prepared only; install and
exact following runtime receipt remain required. Background model jobs stay paused.

Additional deterministic recovery (no model): one STOP_OR_UNCERTAIN result with
an existing exact root summary may invoke the allowed read-only diagnostic.
Only root-attested complete terminal pages, original matching counters and
known200*/204 with no unknown outcomes permit a70s cooldown and local finalization.
Proof digest, original root summary and wake/budget counters are preserved;
proof is rechecked at admission. At most2 such local recoveries per plan;
corruption, nonterminal/unknown transport, stale/foreign proof or absent root
summary remain HOLD. No LLM, secret access or direct HTTP added to the driver.


## Installed continuation: cross-nonce journal ordering

Owner installed control-b7b70bfa6b745a8e7c75e0e886c13f554b60d3649032d293c63e346fdef4b598. Fresh root diagnostic for 0983f5a05a704fdebc8579ec9aa48bd1 passed: report 743994450/type1 has 3 validated pages, 2587 staged rows, 4 sealed requests and known responses [204,200,200,200], unknown=0, pending_response=false, publication pending. This response order is lexical random-nonce filename order, not chronology. The old client wrongly required terminal 204 at list end and rejected continuation after successful installation.

The unprivileged recovery and future driver now require exactly one 204 and otherwise only 200, preserving exact sealed counters, validated terminal stage and all original plan/publication/hash requirements. Regression reproduces the old failure and covers all permutations, repeated terminal, missing terminal, 429 and unknown outcomes. No root reinstall is needed for this client-only fix. Exact recovery launched once as user service msp-wb-memory-resume-20261107; original state/counters backed up by existing helper, new request e2a2558bf80940e1a90023af94a1b0a0. Production completion must be verified from that root receipt before claiming recovery success. Original ROOT_MEMORY_REPAIR_AND_RESUME.txt is a historical installation command; do not repeat against the already installed release.
