# Fixed report identifier profile (no HTTP)

This read-only helper closes a visibility defect: PR124 retained the anomalous
response but only exported a generic sequence error, not which IDs caused it.
Hermes cannot read msp-reports root0700 archive directly and has no sudo password.

Run ROOT_READ_ONLY.txt once in the existing authorized root console. It verifies
a root-owned snapshot before executing, verifies the installed immutable release,
locks against execution, checks the exact held budget3 and sealed response, and
exports only row IDs/indexes/hashes and anomaly counts. No financial amounts,
credentials, services, archive files, budget counters or provider calls are changed.
The metadata result is /var/lib/msp-finance-control/results/wb-601780521-rrd-profile.json.

Actual anomaly shape is not established until this receipt exists. Do not claim
that the root problem is an inclusive cursor or a harmless ordering difference.
Do not consume another sender entry while waiting for this evidence.

The source analyzer is also integrated in the next diagnostic payload so future
selected-report investigations do not need another root read command. Source
changes alone are not an installed diagnostic upgrade or a completed report repair.
