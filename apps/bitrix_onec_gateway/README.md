# Bitrix24 to SRV: isolated command gateway, Phase B

**Status: source implementation only. No deployment and no 1C calls.**

The module is at apps/bitrix_onec_gateway/gateway.py. Python 3.11+,
standard library only. Binds ONLY to 127.0.0.1. No Hermes, nginx or
1C changes. Target is strictly TEST_NEWBASE.

## Responsibility split

1. Trusted server backend of Bitrix24 local app #37 first verifies the
   installation, actual user and read permissions on the specific deal via
   user-context REST. Only then it signs the command. Never sign in JS/browser.
2. Gateway verifies HMAC, timestamp, unique nonce, exact schema and configured
   portal member ID. It stores minimal identifiers in its own SQLite.
3. SRV worker polls over outbound HTTPS using an independent bearer token,
   durably stores request ID and lease locally, and ACKs receipt.
4. Trusted app backend reads status with a fresh HMAC signature.

Do not include buyers' names, INNs, phones, line items, prices, 1C GUIDs or
credentials in this queue. SRV independently reads the deal from Bitrix24.

## Application signature

For signed POST and GET requests send headers:
- X-B24-Timestamp: Unix seconds, within 300 seconds of server time.
- X-B24-Nonce: fresh random URL-safe string, length 20 to 90.
- X-B24-Signature: lowercase hex HMAC-SHA256 with B24_GW_APP_HMAC_KEY.

Canonical signed bytes = METHOD + newline + PATH + newline + TIMESTAMP +
newline + NONCE + newline + SHA256_HEX(RAW_BODY). GET uses empty body.
Never reuse a nonce. All external access MUST use HTTPS termination.

## HTTP API v1

### POST /api/v1/onec-order-requests

Example request JSON (synthetic):
    {"schema_version":1,"request_id":"78189412-5fb7-4e11-ac12-cf33fb7a0b2a","action":"CUSTOMER_ORDER_REQUEST","portal":"b24-uwmjda.bitrix24.ru","portal_member_id":"test_member_0123456789","entity_type_id":2,"deal_id":3,"requested_by_user_id":1,"target":"TEST_NEWBASE","created_at_utc":"2026-10-29T10:00:00Z"}

The example member_id must be replaced with the verified real portal member ID.

Successful initial insert: HTTP 202 with request_id, status QUEUED and
duplicate false. Same request ID or another request for the same logical
(portal, member_id, deal_id, action, target): HTTP 200 with the existing
request_id, status EXISTING, duplicate true. Same request ID but changed
body: HTTP 409. Reused HMAC nonce: HTTP 409.
Invalid signature, timestamp or nonce: 401.
Invalid portal, member, target, action, IDs or schema: 400.

Phase B intentionally permits only one lifetime logical operation per deal,
including a previously acknowledged one. A later controlled revision protocol
must be separately designed before supporting multiple orders per deal.

### POST /api/v1/onec-order-requests/claim

SRV authentication is Authorization: Bearer [B24_GW_SRV_BEARER].
Body: {"worker_id":"SRV","max_jobs":1}.

Response: HTTP 200, job null if none, otherwise job includes request_id,
deal_id, portal, portal_member_id, action, target, a random lease_token, and
lease_until_epoch. Lease is 120 seconds. After 3 expired leases status becomes
FAILED_DELIVERY for manual review. Worker MUST persist receipt locally before
ACK. No 1C calls on this phase.

### POST /api/v1/onec-order-requests/{request_id}/ack

SRV Bearer authentication; JSON body {"lease_token":"claim_token"}.
Successful acknowledgement changes status to RECEIVED_BY_SRV.
Duplicate ACK with same token is safe. Wrong/expired lease is HTTP 409.

### GET /api/v1/onec-order-requests/{request_id}

Trusted app backend signed GET with empty body. Returns current status and
attempt counter. There is no public status or health endpoint.

## Security boundaries and deployment gates

- No public listener: the service binds to loopback only.
- Two separate random secrets of length >=48; never stored in GitHub or JS.
- Configured exact portal/member; actual member ID supplied by server app.
- No command execution, no 1C code and no customer fields in the gateway.
- Use an independent service identity and restrictive file permissions.
- Database directory must already exist before gateway starts.
- Do not open an endpoint until public HTTPS path, TLS termination, proxy limits,
  signatures, status polling, duplicate behavior and persistence are tested.
- Do not alter existing Hermes 9119/9120 and existing 1C 9786/9787 paths.
- Source does not set up nginx, systemd, Tailscale or firewall automatically.
- Never automatically redeliver a completed operation with a new request ID.

Environment:
  B24_GW_APP_HMAC_KEY, B24_GW_SRV_BEARER, B24_GW_MEMBER_ID, B24_GW_DB
  optional B24_GW_PORT (default 9794; check free port before deployment).

The expected private database directory on VPS is
/opt/mcp/data/bitrix-onec-gateway. Actual configuration is not committed.
Existing read-only VPS survey: msp-server-bridge issue #721.

## Offline acceptance

Run from apps/bitrix_onec_gateway:
    python3 -m unittest -v test_gateway.py

Tests use synthetic data, ephemeral local ports and temporary SQLite only.
No Bitrix API calls, no 1C calls, no real secrets.
