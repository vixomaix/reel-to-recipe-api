# Memorystore Redis instance
resource "google_redis_instance" "cache" {
  name           = "${var.cluster_name}-redis"
  tier           = "STANDARD_HA"
  memory_size_gb = var.redis_memory_gb
  region         = var.region

  redis_version     = "REDIS_7_0"
  display_name      = "Reel to Recipe Cache"
  authorized_network = google_compute_network.vpc.id

  maintenance_policy {
    weekly_maintenance_window {
      day = "TUESDAY"
      start_time {
        hours   = 3
        minutes = 0
      }
    }
  }

  labels = {
    environment = var.environment
  }
}

# Secret for Redis connection
resource "google_secret_manager_secret" "redis_url" {
  secret_id = "${var.cluster_name}-redis-url"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "redis_url" {
  secret      = google_secret_manager_secret.redis_url.id
  secret_data = "redis://${google_redis_instance.cache.host}:${google_redis_instance.cache.port}"
}

# Secrets for AI providers
resource "google_secret_manager_secret" "openai_key" {
  secret_id = "openai-api-key"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "anthropic_key" {
  secret_id = "anthropic-api-key"

  replication {
    auto {}
  }
}
