# Hermes browser access

Current browser-access design on REMOTE:

~~~text
browser
  -> Tailscale HTTPS, tailnet only
  -> nginx on 127.0.0.1:9120
  -> Hermes dashboard on 127.0.0.1:9119
~~~

The live tailnet hostname is intentionally not stored in this public repository.

## nginx

The reverse proxy rewrites Host and Origin to `127.0.0.1:9119`, because direct Tailscale Serve -> Hermes access can fail Hermes host/origin validation.

Canonical nginx fragment: `config/nginx/hermes-dashboard.conf`.

## Tailscale Serve

Expected logical configuration:

~~~text
https://<tailnet-host>.ts.net/  (tailnet only)
  -> http://127.0.0.1:9120
~~~

Do not expose ports 9119 or 9120 publicly.

## Boot behavior

Required services are enabled at boot:

- `hermes-dashboard.service`
- `nginx.service`
- `tailscaled.service`

The live server also uses `Restart=always` for Hermes dashboard and gateway. nginx uses its package service behavior.

## Client requirement

A client PC must be logged into the same Tailscale tailnet. No manual TLS certificate installation is required on the client for the `.ts.net` HTTPS endpoint.
