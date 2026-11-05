# Financial archive and temporary daily layer — owner decision 2026-11-05

## Authoritative lifecycle

The permanent WB archive is complete weekly financial documents, reportType1
and2 stored separately. Daily WB financial documents are a temporary per-date
lookup layer for dates not yet covered by a verified weekly publication.

Accumulate closed available dates of the current week without overwriting
other dates. After the week ends, retain those daily documents while the
weekly report is absent, incomplete, invalid or still downloading. Calendar
rollover, discovery metadata and a successful first page are NOT replacement.

After all relevant weekly fragments for the same cabinet/type/date coverage
are fully downloaded (terminal204), checksummed and published with verified
business rows, switch canonical coverage to the weekly archive. Remove only
the temporary daily payloads now covered by that publication. Do not include
both weekly and daily rows in analytical totals. Retain current/uncovered days.
Reports split across month/year boundaries must cover the actual dates, not
an assumed seven-day numerical report identity.

Ozon permanent financial realization is monthly FINAL; the temporary CURRENT
layer is accumulated per date for the open month. Retain the previous month's
CURRENT during a delayed or unverified FINAL publication, alongside the new
month. Purge covered temporary financial payloads only after complete verified
monthly replacement. Do not treat orders as monthly financial realization;
assess dataset equivalence before declaring CURRENT components redundant.
Do not purge control data or business data still required outside this scope.

Do NOT hard-code calendar day5 as a cleanup trigger. Availability of the actual
complete monthly report is the trigger, regardless of whether it appears
before or after that date. Exact current publication deadlines are not yet
confirmed from a current primary source.

## Atomic replacement and recovery requirements

1. Same cabinet, marketplace, report family and exact covered date interval.
2. Final document complete, checksums valid, durable publication and canonical
   registry switch acknowledged; failure/unknown commit prevents cleanup.
3. An idempotent durable replacement receipt records the final document IDs,
   type/period, generation and digest plus removed temporary document IDs and
   per-date coverage. Never infer zero or absence from failed API calls.
4. Cleanup is confined to temporary daily payloads. Permanent weekly/monthly
   archives, their old generations, accepted report pages, quotas, send-entry
   budgets, HTTP journals, errors and recovery evidence are NOT deleted/reset.
5. Retain compact control/tombstone evidence for removed temporary documents so
   a later scan/restart cannot mistake them for missing reports and refetch them.
6. A restart between publication/registry switch/cleanup reconciles that same
   replacement; never delete first and fetch the final report afterwards.
7. Late correction checking of permanent documents remains required. A monthly
   or weekly publication is canonical, not a claim it can never change.

The owner's decision supersedes keeping daily copies forever after replacement;
it does NOT authorize purging permanent archive history/control evidence.
No production deletion has been performed by this documentation change. Daily
WB and Ozon execution/cleanup remain to be implemented and accepted; the running
WB weekly historical backfill is unchanged, and no daily timer is enabled.

## Primary-source findings (not complete method-contract acceptance)

- Ozon moderator confirms completed-month realization and methods
  /v2/finance/realization or /v1/finance/realization/posting:
  https://dev.ozon.ru/community/1809-API-metod-dlia-fakticheskikh-vykupov/
- Ozon official release announcement dated2024-05-02 describes monthly report
  generation after the fifth, not a current guarantee of availability by day5:
  https://dev.ozon.ru/news/333-Novaia-versiia-metoda-otcheta-o-realizatsii-v-Seller-API/
- The daily realization API's description lists a limited historical window
  and subscription requirement; these must be checked before selecting it as
  CURRENT, not silently substituted for the existing accrual/order adapters:
  https://dev.ozon.ru/community/1344-Metod-dlia-poluchenie-otcheta-o-realizatsii-za-den/

Official announcements/community method descriptions do not establish full
current request/response/pagination/quotas for unaccepted execution.
