# One-time privilege installation; subsequent wakes without human root

DESIGN + tested data admission boundary. NOT INSTALLED, no polkit/units modified.

Reuse exactly msp-reports995:985, msp-wb-pilot.service, existing archive/locks and Redis. Do not create another worker/financial queue. Existing report journals and discovery manifests remain the authoritative work state.

## Root-owned policy and one executor

1. One reviewed administrative package pins immutable worker/runtime and a root-owned readable policy: year2026, the3 WB and3 Ozon cabinets, allowed read-only methods, total/per-wake admission ceilings, approved credential sources, shared Redis requirement and the archived completed report exclusions. Ozon methods remain individually denied until schema+pagination+limit acceptance; no blanket approval of four methods from one successful probe.
2. The existing unit retains msp-reports User/Group, LoadCredential delivery by PID1 and root0600 source permissions. Finance-only filtered credentials are prepared once by that package, with source content/permissions unchanged. No credential directory is exposed to hermes. Unit reads only an immutable verified release; writable request data cannot specify commands, paths, URLs, environment, module names, tokens or budget resets.
3. A narrow Polkit rule may authorize only hermes to **start** precisely msp-wb-pilot.service. No stop/restart/enable, unit edits, manage-unit-files, other services, sudo or root shell. Start is a wake request, not scope approval. This rule is not installed here.
4. An immutable fixed systemd privileged preparation/closure helper validates root policy and a bounded request (campaign_id + max_entries only), snapshots the validated selection, constructs expiring scope approval and the unit's finance-only egress. It has no user-specified commands/paths or general file-write operation. Credentials remain PID1-delivered. Root actions are automatic fixed lifecycle steps, not root privileges granted to hermes or msp-reports. Helpers must be implemented/reviewed/tested before installing the rule; do NOT install a permission rule alone against the current blocked unit.
5. Worker obtains the existing standalone/wb_executor lock for every admitted step and shared Redis quota before HTTP; missing Redis blocks dispatch. Three fixed-pilot entries remain unchanged. A larger new historical admission needs a reviewed monotonic budget policy, not another digest/directory to reset a spent counter. Missing/corrupt journals with HTTP/page evidence HOLD. Completed reports are verified locally and skipped. A wake may lower, never raise root admission.
6. One campaign processes a bounded portion; durable cursors/delays determine continuation. Requested wake data is not a new Redis job queue. Units are oneshot, Restart=no, time bound, no overlap, and close temporary approval/egress in stop/failure cleanup. Unknown prior execution needs reconciliation; new wakes cannot erase it. Requests for daily activation remain disabled.

## Acceptance before one-time installation

Actual UID995 import/auth/credential test with no API; negative root policy/request tests; existing-unit serialization; provider method allowlist and finance-only network restrictions; cleanup after success/error/timeout/process kill; reboot with budget/cursor/cooldown preserved; two manual bounded wakes without administrator privileges; complete report terminal204 and published-value readback. Only after these: daily schedule proposal and separate approval.

The scope.admit_wake validator is implemented/tested. The privileged lifecycle helper, exact unit integration and polkit rule are not runtime-accepted or installed. No claim that autonomous waking already works. Current next-batch command remains one reviewed root operation while this acceptance is completed.
