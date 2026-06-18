# End-to-End MLOps Pipeline

Course project: ingestion, training, auto-retraining, AWS deployment, Prometheus/Grafana/Alertmanager, Slack alerts, and GitHub Actions CI/CD.

## Team Information

| Name | Roll Number |
|------|-------------|
| _Your Name_ | _Roll No_ |

## EC2 Public IP

```
EC2_PUBLIC_IP=54.152.150.62
```

Replace the placeholder above after launching your instance.

---

## Local Setup

```powershell
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` with your Docker Hub and (optionally) EC2 values.

### Run pipeline locally

```powershell
python -m ingestion.ingestion --once
python -m model.train
python -m model.retrain_trigger
uvicorn serving.app:app --host 0.0.0.0 --port 8000
```

### Test endpoints (PowerShell)

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod -Uri http://127.0.0.1:8000/predict -Method POST -ContentType "application/json" -Body '{"f0": 0.5, "f1": -0.2}'
Invoke-RestMethod http://127.0.0.1:8000/metrics
```

---

## Phase 3 — AWS Deployment (EC2 + Docker)

### Prerequisites

1. **Train a model** so `model/model_v*.pkl` and `model/latest_model.json` exist:
   ```powershell
   python -m model.train
   ```
2. **Docker Hub** account and access token (`DOCKER_PASSWORD`).
3. **EC2** Ubuntu 22.04 (`t2.micro` / `t3.micro`), security group inbound:
   - **22** (SSH)
   - **8000** (inference API)
   - **9090**, **3000**, **9093** (if running observability stack locally or on same host)

### One-time EC2 setup

SSH into the instance and run:

```bash
curl -fsSL https://raw.githubusercontent.com/<your-org>/<your-repo>/main/deploy/ec2_setup.sh | bash
# Or copy deploy/ec2_setup.sh to the instance and run it.
sudo usermod -aG docker ubuntu
# Log out and back in
```

### Configure `.env`

```env
DOCKER_USERNAME=your_dockerhub_username
DOCKER_PASSWORD=your_dockerhub_access_token
DOCKER_IMAGE_NAME=mlops-project
DOCKER_IMAGE_TAG=latest
EC2_HOST=ec2-xx-xx-xx-xx.compute.amazonaws.com
EC2_PUBLIC_IP=xx.xx.xx.xx
EC2_USER=ubuntu
EC2_SSH_KEY_PATH=C:\Users\You\.ssh\ec2_key.pem
APP_PORT=8000
```

### Build, push, and deploy

**Git Bash / WSL / Linux / macOS:**

```bash
chmod +x deploy/deploy.sh deploy/ec2_setup.sh
./deploy/deploy.sh
```

**Build only (no push/deploy):**

```bash
SKIP_PUSH=1 SKIP_DEPLOY=1 ./deploy/deploy.sh
```

**PowerShell (build image locally):**

```powershell
.\deploy\deploy.ps1 -BuildOnly
```

### Verify on EC2

```powershell
$ip = "<EC2_PUBLIC_IP>"
Invoke-RestMethod "http://${ip}:8000/health"
Invoke-RestMethod -Uri "http://${ip}:8000/predict" -Method POST -ContentType "application/json" -Body '{"f0": 0.5, "f1": -0.2}'
Invoke-RestMethod "http://${ip}:8000/metrics"
```

Expected health response:::

```json
{"status": "ok", "model_loaded": true}
```

### Docker (manual)

```bash
docker build -t youruser/mlops-project:latest .
docker run -d -p 8000:8000 --name mlops-inference youruser/mlops-project:latest
```

---

## Prometheus scrape target

After EC2 is live, set Prometheus to scrape `http://<EC2_PUBLIC_IP>:8000/metrics` (update `prometheus/prometheus.yml` or use `host.docker.internal` for local API during development).

---

## GitHub Actions secrets

| Secret | Purpose |
|--------|---------|
| `DOCKER_USERNAME` | Docker Hub user |
| `DOCKER_PASSWORD` | Docker Hub token |
| `EC2_HOST` | EC2 public DNS or IP |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_KEY` | Private key contents |
| `SLACK_WEBHOOK_URL` | Alerting (Phase 6) |

---

## Project status

| Phase | Status |
|-------|--------|
| 0 — Setup | Done |
| 1 — Ingestion & drift | Done |
| 2 — Training & retraining | Done |
| 3 — AWS Docker deploy | Done (scripts + Dockerfile) |
| 4–7 — Metrics stack, alerts, full CI | In progress |

---

## Video demo

_Add unlisted YouTube / Drive link here after recording._
