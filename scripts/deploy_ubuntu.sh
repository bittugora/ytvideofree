#!/usr/bin/env bash
set -euo pipefail

APP_NAME="ytvideofree"
APP_USER="ytvideofree"
APP_DIR="/var/www/ytvideofree"
ENV_DIR="/etc/ytvideofree"
STATE_DIR="/var/lib/ytvideofree"
LOG_DIR="/var/log/ytvideofree"
SERVICE_FILE="/etc/systemd/system/ytvideofree.service"

if [[ "${EUID}" -ne 0 ]]; then
  exec sudo -E bash "$0" "$@"
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Installing operating system packages..."
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  ffmpeg \
  nodejs \
  python3 \
  python3-pip \
  python3-venv \
  rsync

if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi

mkdir -p "${APP_DIR}" "${ENV_DIR}" "${STATE_DIR}/tmp" "${LOG_DIR}"

echo "Syncing project into ${APP_DIR}..."
rsync -a --delete \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude ".docker-tmp" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  --exclude "downloads" \
  --exclude "ffmpeg" \
  --exclude "logs" \
  --exclude "staticfiles" \
  "${PROJECT_DIR}/" "${APP_DIR}/"

echo "Creating Python environment..."
python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip wheel
"${APP_DIR}/.venv/bin/python" -m pip install -r "${APP_DIR}/requirements.txt"

if [[ ! -f "${ENV_DIR}/ytvideofree.env" ]]; then
  cp "${APP_DIR}/deploy/ytvideofree.env.example" "${ENV_DIR}/ytvideofree.env"
fi

cp "${APP_DIR}/deploy/systemd/ytvideofree.service" "${SERVICE_FILE}"

chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}" "${STATE_DIR}" "${LOG_DIR}"
chown root:"${APP_USER}" "${ENV_DIR}/ytvideofree.env"
chmod 640 "${ENV_DIR}/ytvideofree.env"

echo "Collecting static files..."
(cd "${APP_DIR}" && "${APP_DIR}/.venv/bin/python" manage.py collectstatic --noinput)

echo "Starting ${APP_NAME}..."
systemctl daemon-reload
systemctl enable --now "${APP_NAME}"
systemctl restart "${APP_NAME}"

echo "Checking local health endpoint..."
curl -fsS http://127.0.0.1:8000/healthz
echo
systemctl --no-pager --lines=20 status "${APP_NAME}"
