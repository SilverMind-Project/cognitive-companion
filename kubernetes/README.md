# Kubernetes Deployment

Manifests for deploying Cognitive Companion v2 to a microk8s cluster.

## Architecture

```
Internet / LAN
       │
       ▼
┌──────────────────────────────────────────────┐
│  nginx ingress (192.168.1.69)                │
│  ├─ nanai.khoofia.com     → cc-ui-svc:80    │
│  ├─ api.nanai.khoofia.com → cc-backend:8000 │
│  ├─ :8000-8002 (TCP)      → vllm-svc        │
│  └─ :5432 (TCP)           → pgedge-n1-rw    │
└──────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│  default namespace                           │
│  ├─ ai-api-gateway (backend, port 8000)      │
│  ├─ cognitive-companion-ui (frontend, :80)   │
│  ├─ person-id (GPU, port 8100)               │
│  ├─ vllm-svc (GPU, ports 8000-8002)         │
│  └─ pgedge-n1-rw (postgres, port 5432)      │
├──────────────────────────────────────────────┤
│  minio-operator namespace                    │
│  └─ minio (S3, port 80)                     │
└──────────────────────────────────────────────┘
```

## Directory Structure

```
kubernetes/
├── base/                          # Environment-agnostic manifests
│   ├── deployment.yaml            # Backend deployment (IMAGE_PLACEHOLDER)
│   ├── service.yaml               # Backend ClusterIP service
│   ├── pvc.yaml                   # Backend persistent volume claim
│   ├── configmap.yaml             # Non-sensitive env vars (PLACEHOLDER)
│   ├── configmap-files.yaml       # YAML config files (settings, auth, notifications)
│   ├── secret.yaml                # Sensitive env vars (empty, fill before use)
│   ├── frontend-deployment.yaml   # Frontend deployment (IMAGE_PLACEHOLDER)
│   └── frontend-service.yaml      # Frontend ClusterIP service
├── local/                         # dgx-box cluster overlays
│   ├── deployment.yaml            # Backend with localhost:32000 image
│   ├── frontend-deployment.yaml   # Frontend with localhost:32000 image
│   ├── configmap.yaml             # Cluster-internal service URLs
│   ├── secret.yaml                # Fill with base64-encoded values
│   ├── ingress.yaml               # TLS ingress for nanai.khoofia.com
│   └── build-and-deploy.sh        # Build images + apply manifests
└── README.md
```

## Migration from v1

v2 replaces the v1 `cognitive-companion/` deployment:

| Change | v1 | v2 |
|--------|----|----|
| Backend port | 8100 | 8000 |
| Backend image | `ai-api-gateway:latest` (same name) | `ai-api-gateway:latest` (same name) |
| Frontend image | `cognitive-companion-ui:latest` | `cognitive-companion-ui:latest` (same name) |
| Service type | LoadBalancer | ClusterIP (behind ingress) |
| Person-ID | External | In-cluster GPU pod |
| Config | Inline env vars | ConfigMap + Secret |
| Probes | None | Readiness + liveness |

### Migration Steps

1. **Fill in secrets.** Edit `local/secret.yaml` with base64-encoded values.
2. **Build and push images.** Run `./local/build-and-deploy.sh all`.
3. **Verify.** Run `microk8s kubectl get pods` and confirm all 3 pods are Running.
4. **Delete v1 resources** once v2 is confirmed working:
   ```bash
   # The v1 deployment uses the same name, so applying v2 replaces it.
   # If v1 used different names, delete them manually.
   ```

## Quick Start (local cluster)

```bash
# 1. Fill in secrets
cp local/secret.yaml local/secret-filled.yaml
# Edit local/secret-filled.yaml with base64-encoded values

# 2. Build and deploy everything
./local/build-and-deploy.sh all

# 3. Check status
microk8s kubectl get pods
microk8s kubectl get svc
microk8s kubectl get ingress
```

## Updating

After code changes:

```bash
# Rebuild and redeploy just the backend
./local/build-and-deploy.sh backend

# Or just the frontend
./local/build-and-deploy.sh frontend

# Or just person-id
./local/build-and-deploy.sh person-id
```
