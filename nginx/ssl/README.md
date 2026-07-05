# SSL certificates (Let's Encrypt)

The edge `nginx` service terminates TLS using certificates issued by
[Let's Encrypt](https://letsencrypt.org/) via [certbot](https://certbot.eff.org/).
Certificates live in the `nginx_certs` Docker volume (mounted at
`/etc/letsencrypt`), and the ACME `http-01` challenge is served from the
`nginx_acme` volume (`/var/www/certbot`).

> Replace `example.com` with your real domain everywhere below, and make sure
> the domain's DNS `A`/`AAAA` records already point at the server.

## 1. First-time issuance

Bring the stack up so nginx is serving port 80 (the HTTP server block already
exposes `/.well-known/acme-challenge/`):

```bash
docker compose up -d nginx
```

Then request the certificate with a one-shot certbot container that shares the
same volumes as nginx:

```bash
docker run --rm \
  -v mudir_nginx_certs:/etc/letsencrypt \
  -v mudir_nginx_acme:/var/www/certbot \
  certbot/certbot certonly --webroot -w /var/www/certbot \
    -d example.com -d www.example.com \
    --email admin@example.com --agree-tos --no-eff-email
```

(The volume names are prefixed with the compose project name — `mudir` by
default. Adjust if you set `COMPOSE_PROJECT_NAME`.)

Reload nginx to pick up the new certificate:

```bash
docker compose exec nginx nginx -s reload
```

## 2. Auto-renewal

Let's Encrypt certificates are valid for 90 days. Renew them automatically with
the provided [`scripts/ssl-renew.sh`](../../scripts/ssl-renew.sh), which runs
`certbot renew` (a no-op until a cert is within 30 days of expiry) and reloads
nginx.

Add a cron job on the host (runs twice daily, the recommended cadence):

```cron
# /etc/cron.d/mudir-ssl-renew
0 3,15 * * * root cd /opt/mudir && /opt/mudir/scripts/ssl-renew.sh >> /var/log/mudir-ssl-renew.log 2>&1
```

Adjust `/opt/mudir` to wherever the repository is checked out on the server.

## 3. Files in this directory

This directory intentionally contains **no certificate material** — private
keys and certificates must never be committed to git. They are stored only in
the Docker volume at runtime.
