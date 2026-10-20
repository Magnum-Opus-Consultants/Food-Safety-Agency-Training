#!/usr/bin/env bash
# Deploy a release of the Training Hub from a git archive copied to the server, keeping the server's own
# .env, uploaded files and demo sign-in details. Backs up the database and the app folder first.
# Run as root: sudo bash deploy.sh /tmp/fsa-training-hub.tar.gz
set -euo pipefail
ARCHIVE=${1:?give the release archive}
APP=/var/www/fsa-training-hub
CONF=/etc/fsa-training-hub
STAMP=$(date +%Y%m%d-%H%M)

# Back up what is there before replacing it.
if [ -f "$APP/backend/manage.py" ]; then
  B=/var/backups/fsa-training-hub-$STAMP
  mkdir -p "$B"
  sudo -u postgres pg_dump --format=custom fsa_training > "$B/fsa_training.dump"
  tar -czf "$B/app.tar.gz" -C /var/www --exclude=fsa-training-hub/web/node_modules --exclude=fsa-training-hub/web/.next \
      --exclude=fsa-training-hub/backend/.venv --exclude=fsa-training-hub/.npm --exclude=fsa-training-hub/.cache fsa-training-hub
  chmod -R go-rwx "$B"
  echo "backup: $B"
fi

# Unpack and sync, keeping the server's own files.
REL=$(mktemp -d)
tar -xzf "$ARCHIVE" -C "$REL"
rsync -a --delete \
  --exclude backend/.env --exclude backend/private-files --exclude backend/.venv \
  --exclude web/node_modules --exclude web/.next --exclude demo-logins.txt --exclude .npm --exclude .cache \
  "$REL"/ "$APP"/
rm -rf "$REL"

# Settings for this server, written once with generated secrets (never in git or chat).
if [ ! -f "$APP/backend/.env" ]; then
  . "$CONF/db.env"
  HOSTS=${FSA_HOSTS:-127.0.0.1,localhost,10.0.0.131,fsa-training-hub.netbird.cloud}
  ORIGINS=${FSA_ORIGINS:-http://10.0.0.131,http://fsa-training-hub.netbird.cloud}
  KEY() { python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())'; }
  umask 077
  cat > "$APP/backend/.env" <<ENV
DJANGO_SECRET_KEY=$(openssl rand -hex 48)
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=$HOSTS
DJANGO_CSRF_TRUSTED_ORIGINS=$ORIGINS
FSA_SECURE_COOKIES=false
FSA_DEMO_MODE=true
PGDATABASE=fsa_training
PGUSER=fsa
PGPASSWORD=$PGPASSWORD
PGHOST=localhost
PGPORT=5432
FSA_PII_ENCRYPTION_KEY=$(KEY)
FSA_PII_INDEX_KEY=$(KEY)
FSA_FILE_ROOT=$APP/backend/private-files
ENV
  umask 022
fi
mkdir -p "$APP/backend/private-files"
chown -R fsahub:fsahub "$APP"
chmod 600 "$APP/backend/.env"

# Backend: virtualenv, packages, migrations.
cd "$APP/backend"
[ -d .venv ] || sudo -u fsahub python3 -m venv .venv
sudo -u fsahub .venv/bin/pip install -q --upgrade pip
sudo -u fsahub .venv/bin/pip install -q -r requirements.txt
sudo -u fsahub .venv/bin/python manage.py migrate --noinput

# Front end: exact dependencies from the lock file, then the production build.
cd "$APP/web"
sudo -u fsahub HOME="$APP" npm ci --no-audit --no-fund --loglevel=error
sudo -u fsahub HOME="$APP" npm run build

systemctl enable -q fsa-api fsa-web
systemctl restart fsa-api fsa-web
echo "deployed $STAMP"
