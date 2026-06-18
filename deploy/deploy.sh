#!/usr/bin/env bash
# Build Docker image, push to registry, deploy to EC2, verify /health.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

DOCKER_USERNAME="${DOCKER_USERNAME:-}"
DOCKER_PASSWORD="${DOCKER_PASSWORD:-}"
DOCKER_IMAGE_NAME="${DOCKER_IMAGE_NAME:-mlops-project}"
DOCKER_IMAGE_TAG="${DOCKER_IMAGE_TAG:-latest}"
GIT_SHA="${GITHUB_SHA:-$(git rev-parse --short HEAD 2>/dev/null || echo local)}"
EC2_HOST="${EC2_HOST:-}"
EC2_USER="${EC2_USER:-ubuntu}"
EC2_SSH_KEY_PATH="${EC2_SSH_KEY_PATH:-$HOME/.ssh/ec2_key.pem}"
APP_PORT="${APP_PORT:-8000}"
CONTAINER_NAME="${CONTAINER_NAME:-mlops-inference}"
DOCKERFILE="${DOCKERFILE:-Dockerfile}"
SKIP_PUSH="${SKIP_PUSH:-0}"
SKIP_DEPLOY="${SKIP_DEPLOY:-0}"

if [[ -z "${DOCKER_USERNAME}" ]]; then
  echo "ERROR: DOCKER_USERNAME is not set. Add it to .env or export it."
  exit 1
fi

IMAGE_BASE="${DOCKER_USERNAME}/${DOCKER_IMAGE_NAME}"
IMAGE_LATEST="${IMAGE_BASE}:${DOCKER_IMAGE_TAG}"
IMAGE_SHA="${IMAGE_BASE}:${GIT_SHA}"

echo "==> Building image ${IMAGE_LATEST}"
docker build -f "${DOCKERFILE}" -t "${IMAGE_LATEST}" -t "${IMAGE_SHA}" .

if [[ "${SKIP_PUSH}" != "1" ]]; then
  if [[ -z "${DOCKER_PASSWORD}" ]]; then
    echo "ERROR: DOCKER_PASSWORD is required to push (or set SKIP_PUSH=1)."
    exit 1
  fi
  echo "==> Logging in to Docker Hub"
  echo "${DOCKER_PASSWORD}" | docker login -u "${DOCKER_USERNAME}" --password-stdin
  echo "==> Pushing ${IMAGE_LATEST} and ${IMAGE_SHA}"
  docker push "${IMAGE_LATEST}"
  docker push "${IMAGE_SHA}"
fi

if [[ "${SKIP_DEPLOY}" == "1" ]]; then
  echo "SKIP_DEPLOY=1 — build/push complete."
  exit 0
fi

if [[ -z "${EC2_HOST}" ]]; then
  echo "WARN: EC2_HOST not set — skipping remote deploy."
  exit 0
fi

if [[ ! -f "${EC2_SSH_KEY_PATH}" ]]; then
  echo "ERROR: SSH key not found at ${EC2_SSH_KEY_PATH}"
  exit 1
fi

echo "==> Deploying to ${EC2_USER}@${EC2_HOST}"
ssh -i "${EC2_SSH_KEY_PATH}" -o StrictHostKeyChecking=accept-new "${EC2_USER}@${EC2_HOST}" bash -s <<EOF
set -euo pipefail
IMAGE="${IMAGE_LATEST}"
CONTAINER="${CONTAINER_NAME}"
PORT="${APP_PORT}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not installed on EC2. Run deploy/ec2_setup.sh on the instance first."
  exit 1
fi

docker pull "\${IMAGE}"
docker stop "\${CONTAINER}" 2>/dev/null || true
docker rm "\${CONTAINER}" 2>/dev/null || true
docker run -d \\
  --name "\${CONTAINER}" \\
  --restart unless-stopped \\
  -p "\${PORT}:8000" \\
  "\${IMAGE}"

sleep 3
curl -fsS "http://127.0.0.1:\${PORT}/health"
echo ""
EOF

HEALTH_URL="http://${EC2_HOST}:${APP_PORT}/health"
PREDICT_URL="http://${EC2_HOST}:${APP_PORT}/predict"
echo "==> Verifying ${HEALTH_URL}"
curl -fsS "${HEALTH_URL}"
echo ""
echo "Deployment complete."
echo "  Health:   ${HEALTH_URL}"
echo "  Predict:  ${PREDICT_URL}"
echo "  Metrics:  http://${EC2_HOST}:${APP_PORT}/metrics"
