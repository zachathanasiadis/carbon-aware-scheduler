# Carbon-Aware Pod Scheduler

A Kubernetes operator that schedules workloads on the node with the lowest average carbon intensity, reducing the carbon footprint of compute workloads. Built with Kopf, deployed on a self-provisioned 3-node Kubernetes cluster on Google Cloud Platform.

## Overview

Cloud computing has a measurable carbon footprint that varies depending on which data center, and therefore which energy grid, your workloads run on. This project implements a custom Kubernetes scheduler that fetches real-time average carbon intensity data for each node's region and uses Kubernetes Node Affinity to direct workloads to the cleanest available node.

The scheduler was evaluated over 600 simulated workloads and achieved a **~16% reduction in average carbon emissions per workload** (247 gCO₂ → 207.9 gCO₂) compared to default Kubernetes scheduling.

## Architecture

The system runs as a Kubernetes operator on a 3-node cluster provisioned on Google Cloud Platform. Each node is mapped to a real-world energy grid region — Germany (DE), Texas (ERCOT), and the Netherlands (NL). On a fixed interval, the operator fetches average carbon intensity data for each region from an external API, identifies the node with the lowest emissions footprint, and schedules the incoming workload there using Kubernetes Node Affinity. A Kopf-based event watcher then logs where each pod actually lands, allowing the scheduled recommendation to be compared against the real placement.

**Scheduling flow:**

1. The operator starts and launches a scheduling loop
2. Every 10 seconds, it fetches average carbon intensity for each node's region (DE, ERCOT, NL) from an external API
3. The node with the lowest carbon intensity is selected as the target
4. A pod is created with a Node Affinity rule requiring it to land on that node
5. Kubernetes schedules the pod accordingly
6. The operator watches the placement and logs the actual node assignment for analysis

**Components:**
- `scheduler.py` — Kopf operator that fetches carbon intensity data and creates pods with Node Affinity rules pointing to the lowest-carbon node
- `deployment.yaml` — Deploys the operator to the cluster
- `rbac.yaml` — Service account and RBAC rules granting the operator access to pods, nodes, and events
- `workload.yaml` — Pod template for sysbench CPU workloads used in experiments
- `spinup-vms.tf` — Terraform configuration for provisioning the 3-node GCP cluster
- `Dockerfile` — Builds the operator container image

## Infrastructure

The cluster was provisioned on Google Compute Engine using Terraform for VM deployment and [Kubespray](https://github.com/kubernetes-sigs/kubespray) for Kubernetes bootstrapping.

- 3x `n2-standard-2` VMs running Ubuntu 22.04 LTS
- vm1 acts as the control plane and runs the operator

> **Note:** The Terraform firewall rule opens all ports for convenience. This is not appropriate for production and should be locked down to specific required ports in a real deployment.

### Prerequisites

- A Kubernetes cluster with at least 3 nodes
  - If you already have one, skip to the **Deployment** section
  - If not, you can provision one using the instructions below, which requires:
    - [Terraform](https://developer.hashicorp.com/terraform/install) installed
    - A GCP project with billing enabled
    - A GCP service account with Compute Engine permissions
    - [Kubespray](https://github.com/kubernetes-sigs/kubespray) for cluster bootstrapping
- A carbon intensity API endpoint that returns average carbon intensity per region (set via `CARBON_API_URL` environment variable)

### Provisioning the Cluster

1. Create a `terraform.tfvars` file and fill in your values:
```hcl
gcp_project_id = "your-gcp-project-id"
gcp_region     = "europe-west3"
gcp_zone       = "europe-west3-a"
ssh_user       = "your-username"
ssh_key_path   = "~/.ssh/your-key.pub"
```
2. Run:
```bash
terraform init
terraform apply
```
3. Follow the Kubespray documentation to bootstrap Kubernetes on the provisioned VMs

## Deployment

### Build and push the operator image

```bash
docker build -t <your-dockerhub-username>/carbon-aware-scheduler .
docker push <your-dockerhub-username>/carbon-aware-scheduler
```

Before deploying, update `deployment.yaml`:
- Set the image name to match your pushed image
- Add the `CARBON_API_URL` environment variable to the container spec, pointing to your carbon intensity API
- The operator runs on vm1 by default (see nodeSelector). If your control plane node has a different name, update accordingly.

### Deploy to the cluster

```bash
kubectl apply -f rbac.yaml
kubectl apply -f deployment.yaml
```

The operator will start automatically and begin the scheduling loop.

## How It Works

1. On startup, the operator launches an async scheduling loop
2. Every `SCHEDULING_PERIOD` seconds (default: 10), it fetches average carbon intensity for each node's mapped region (DE, ERCOT, NL) from an external API
3. The node with the lowest carbon intensity is selected
4. A pod is created with a Node Affinity rule that requires it to be scheduled on that node
5. The operator also watches pod placements to log where each workload actually lands

## Experiment & Results

To evaluate the scheduler, 600 sysbench CPU workloads were submitted sequentially:
- **First 300** scheduled with carbon-aware logic (Node Affinity to lowest-carbon node)
- **Next 300** scheduled with default Kubernetes scheduling (no affinity rules)

Since this is an artificial scenario, you we can assume that each active pod consumes 200W of electricity. As workloads run 40s on average and we have 300 workloads per strategy in total, the expected overall energy usage is 40s * 300 * 200W = 667 Wh per strategy. Total carbon emissions is calculated as carbon intensity (gCO2/kWh) * energy (Wh) / 1000.

| Strategy | Total Carbon Emissions |
|---|---|
| Carbon-Aware | 207.55 gCO₂ |
| Default | 247.28 gCO₂ |
| **Reduction** | **~16%** |

Experiment logs and charts are available in the `/experiments` directory.

> **Note:** This experiment was conducted in a simulated environment with fixed node-to-region mappings, fixed energy consumption values and artificial average carbon intensity values. Real-world results would depend on actual carbon intensity variance across regions and workload characteristics.
