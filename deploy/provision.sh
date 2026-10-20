#!/usr/bin/env bash
# One-off setup of a Training Hub server (Ubuntu 26.04): runtime packages, the service user, the
# PostgreSQL database, Apache's proxy modules and the systemd units. Safe to run again.
# Run as root: sudo bash provision.sh
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

APP=/var/www/fsa-training-hub
CONF=/etc/fsa-training-hub

apt-get update -q
apt-get install -y -q postgresql apache2 nodejs npm python3-venv python3-dev build-essential libpq-dev rsync openssl

# The app runs as its own system user, never as root.
id fsahub >/dev/null 2>&1 || useradd --system --home-dir "$APP" --shell /usr/sbin/nologin fsahub
mkdir -p "$APP" "$CONF"
chmod 750 "$CONF"

# Database: role and database, with a generated password kept only on this server.
if ! sudo -u postgres psql -tAc "select 1 from pg_roles where rolname='fsa'" | grep -q 1; then
  PW=$(openssl rand -hex 24)
  sudo -u postgres psql -q -c "create role fsa login password '$PW'"
  sudo -u postgres psql -q -c "create database fsa_training owner fsa encoding 'UTF8' template template0"
  umask 077; printf 'PGPASSWORD=%s\n' "$PW" > "$CONF/db.env"
fi
sudo -u postgres psql -q -d fsa_training -c "create extension if not exists btree_gist"

# Apache on port 80 only; TLS is done by the edge proxy.
a2enmod -q proxy proxy_http headers rewrite
a2dissite -q 000-default 2>/dev/null || true

cat > /etc/systemd/system/fsa-api.service <<'UNIT'
[Unit]
Description=FSA Training Hub API (Django, gunicorn)
After=network.target postgresql.service

[Service]
User=fsahub
Group=fsahub
WorkingDirectory=/var/www/fsa-training-hub/backend
ExecStart=/var/www/fsa-training-hub/backend/.venv/bin/gunicorn fsa.wsgi:application --bind 127.0.0.1:8210 --workers 3 --timeout 120 --access-logfile -
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/fsa-web.service <<'UNIT'
[Unit]
Description=FSA Training Hub web (Next.js)
After=network.target fsa-api.service

[Service]
User=fsahub
Group=fsahub
WorkingDirectory=/var/www/fsa-training-hub/web
Environment=NODE_ENV=production
Environment=FSA_API_ORIGIN=http://127.0.0.1:8210
ExecStart=/var/www/fsa-training-hub/web/node_modules/.bin/next start -H 127.0.0.1 -p 3210
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
echo "provisioned"
