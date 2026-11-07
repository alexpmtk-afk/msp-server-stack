# WB Laser Master seven-minute timeout recovery

Original nonce: 9e4d19223c0f447e885271edcc38698c. Root-provided read-only profile
shows report713724240/type1, sealed executor DONE,2119 rows,4 cumulative entries;
exact failed invocation made one HTTP204 and no unknown outcomes. No publication
verification was returned before the seven-minute service watchdog terminated
worker. CPU398.3s supports local processing rather than network wait; the exact
stack location at termination was not captured.

Repeated read_active/read_generation calls reparse identical full historical
CSV generations, including the complete descriptor ancestry. New per-operation
ContextVar cache reuses only successful semantic checks keyed by dataset,
cabinet, period and SHA256/length of EVERY actual file. It never caches reads,
CURRENT, descriptor ancestry, file hashes or parsed financial rows. Changes
are revalidated; proof values copied;256-entry cap; context always discarded.
Worker execution, root selection and read-only diagnostics delimit the scope.
No watchdog, provider quota, permissions, credentials or admission limit changed.

Synthetic10000-row/30-field benchmark,6 repeated byte-identical checks:
1.089s uncached vs0.212s cached (5.14x). This is not production timing evidence.
346 marketplace tests pass,2 skipped. New tests include mutation/identity
rejection, operation lifetime and timeout-resume negative controls.

The new diagnostic verifies the exact interrupted report and all-nonce ledger
read-only, and includes that evidence in its root-owned public receipt.
The dedicated unprivileged timeout launcher requires fresh exact root evidence,
fully verified2119-row publication, original four attempts200/200/200/204,
zero unknowns/no pending response, exact previous root receipt/current nonce,
known immutable controller hash and idle closed-network executors. It backs up
user state/wrapper, persists DISPATCHING before a single wake and restarts only
the existing scoped WB Laser Master user driver after PASS. Every other error
stays HOLD; no budgets reset. Root controller performs ordinary full integrity
and admission checks before selecting any next provider request.

Command: ROOT_TIMEOUT_REPAIR_AND_RESUME.txt. Unlike the prior discovery helper,
this targets the current timeout nonce only. runuser now explicitly receives
XDG_RUNTIME_DIR and DBUS_SESSION_BUS_ADDRESS for UID1001.

Prepared and offline-tested only; root install, production timing and subsequent
successful continuation are NOT yet verified. Background AI cron remains paused.
