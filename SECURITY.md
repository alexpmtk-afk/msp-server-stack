# Security policy

This is a public repository. Treat every committed byte as public information.

## Never commit

- passwords or API keys
- private SSH keys
- Telegram session files or bot tokens
- cookies or browser profiles
- OAuth client secrets or refresh tokens
- proxy, VPN or tunnel credentials
- private TLS certificates
- populated `.env` files
- production databases, dumps or backups
- live access URLs containing credentials

Use placeholders in tracked templates and inject real values only on the server or from a protected secret store.

## If a secret is exposed

1. Revoke or rotate the exposed credential immediately.
2. Do not assume deleting the file from the latest commit is sufficient.
3. Remove the secret from Git history where appropriate.
4. Audit access logs and dependent credentials.
5. Add a prevention rule so the same class of secret cannot be committed again.

## Repository checks

Pull requests and pushes are checked for common secret patterns. Automated scanning is an additional control, not a replacement for review.

## Reporting

Do not publish a discovered credential in a GitHub issue. Contact the repository maintainer through a private channel.
