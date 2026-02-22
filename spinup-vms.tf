terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "6.8.0"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
  zone    = var.gcp_zone
}

variable "gcp_project_id" {
  description = "GCP project ID"
  type        = string
}

variable "gcp_region" {
  description = "GCP region"
  type        = string
  default     = "europe-west3"
}

variable "gcp_zone" {
  description = "GCP zone"
  type        = string
  default     = "europe-west3-a"
}

variable "ssh_user" {
  description = "SSH username for the VMs"
  type        = string
}

variable "ssh_key_path" {
  description = "Path to the public SSH key"
  type        = string
}

locals {
  vm_names = ["vm1", "vm2", "vm3"]
}

resource "google_compute_firewall" "allow_all" {
  name    = "allow-all-tcp-icmp"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "icmp"
  }

  allow {
    protocol = "udp"
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["cc"]
}

resource "google_compute_instance" "vm" {
  for_each     = toset(local.vm_names)
  name         = each.key
  machine_type = "n2-standard-2"
  zone         = var.gcp_zone

  tags = ["cc"]

  boot_disk {
    initialize_params {
      image = "projects/ubuntu-os-cloud/global/images/family/ubuntu-2204-lts"
      size  = 50
    }
  }

  network_interface {
    network = "default"
    access_config {}
  }

  metadata = {
    ssh-keys = "${var.ssh_user}:${file(var.ssh_key_path)}"
  }

  metadata_startup_script = <<-EOF
    #!/bin/bash
    set -e

    apt-get update
    apt-get install -y python3-pip sudo

    echo "${var.ssh_user} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/${var.ssh_user}
    chmod 440 /etc/sudoers.d/${var.ssh_user}
  EOF
}