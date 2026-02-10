# Artifact Registry for container images
resource "google_artifact_registry_repository" "docker" {
  location      = var.region
  repository_id = "${var.cluster_name}-images"
  description   = "Docker images for Reel to Recipe"
  format        = "DOCKER"

  labels = {
    environment = var.environment
  }
}

# Cloud Storage bucket for video processing
resource "google_storage_bucket" "videos" {
  name          = "${var.project_id}-reel-videos"
  location      = var.region
  force_destroy = var.environment != "prod"

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 7  # Delete videos after 7 days
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    environment = var.environment
  }
}

# Service Account for application
resource "google_service_account" "app" {
  account_id   = "${var.cluster_name}-app"
  display_name = "Reel to Recipe Application"
}

# IAM bindings for app service account
resource "google_project_iam_member" "app_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.app.email}"
}

resource "google_project_iam_member" "app_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.app.email}"
}

# Workload Identity binding for Kubernetes
resource "google_service_account_iam_member" "workload_identity" {
  service_account_id = google_service_account.app.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[default/reel-to-recipe-sa]"
}
