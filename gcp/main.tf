locals {
  apis = toset([
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "compute.googleapis.com",
    "dataflow.googleapis.com",
    "documentai.googleapis.com",
    "firebase.googleapis.com",
    "firebasehosting.googleapis.com",
    "iam.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "serviceusage.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
    "vision.googleapis.com",
  ])

  service_name = "${var.project_name}-api"
  db_name      = "meetings"
  db_user      = "app"
}

resource "google_project_service" "enabled" {
  for_each           = local.apis
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_service_account" "api" {
  account_id   = "${var.project_name}-api"
  display_name = "SuccessfulSuccess Cloud Run API"
  depends_on   = [google_project_service.enabled]
}

resource "google_project_iam_member" "api_cloudsql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_secret_manager_secret_iam_member" "api_secret_access" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.database_password.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

resource "google_firebase_project" "app" {
  provider        = google-beta
  project         = var.project_id
  depends_on      = [google_project_service.enabled]
}

resource "google_artifact_registry_repository" "backend" {
  project       = var.project_id
  location      = var.region
  repository_id = "${var.project_name}-images"
  description   = "Backend container images for SuccessfulSuccess"
  format        = "DOCKER"
  depends_on    = [google_project_service.enabled]
}

resource "random_password" "database" {
  length  = var.db_password_length
  special = false
}

resource "google_secret_manager_secret" "database_password" {
  project   = var.project_id
  secret_id = "${var.project_name}-database-password"
  replication {
    auto {}
  }
  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_version" "database_password" {
  secret      = google_secret_manager_secret.database_password.id
  secret_data = random_password.database.result
}

resource "google_sql_database_instance" "postgres" {
  project             = var.project_id
  name                = "${var.project_name}-postgres"
  region              = var.region
  database_version    = "POSTGRES_17"
  deletion_protection = false

  settings {
    tier              = "db-f1-micro"
    availability_type = "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = 10
    disk_autoresize   = false
    activation_policy = "ALWAYS"
    backup_configuration {
      enabled = false
    }
    ip_configuration {
      ipv4_enabled = true
    }
    user_labels = {
      app = "successfulsuccess"
    }
  }

  depends_on = [google_project_service.enabled]
}

resource "google_sql_database" "meetings" {
  project  = var.project_id
  name     = local.db_name
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "app" {
  project  = var.project_id
  name     = local.db_user
  instance = google_sql_database_instance.postgres.name
  password = random_password.database.result
}

resource "google_cloud_run_v2_service" "api" {
  project             = var.project_id
  name                = local.service_name
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.api.email
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = var.api_image
      ports {
        container_port = 8000
      }
      env {
        name  = "APP_TIMEZONE"
        value = var.app_timezone
      }
      env {
        name  = "RUN_MIGRATIONS_ON_START"
        value = "false"
      }
      env {
        name  = "DB_POOL_SIZE"
        value = "3"
      }
      env {
        name  = "DB_HOST"
        value = "/cloudsql/${google_sql_database_instance.postgres.connection_name}"
      }
      env {
        name  = "DB_NAME"
        value = local.db_name
      }
      env {
        name  = "DB_USER"
        value = local.db_user
      }
      env {
        name = "DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_password.secret_id
            version = google_secret_manager_secret_version.database_password.version
          }
        }
      }
      env {
        name  = "COGNITO_REGION"
        value = var.cognito_region
      }
      env {
        name  = "COGNITO_USER_POOL_ID"
        value = var.cognito_user_pool_id
      }
      env {
        name  = "COGNITO_CLIENT_ID"
        value = var.cognito_client_id
      }
      env {
        name  = "CORS_ORIGINS"
        value = "https://${var.project_id}.web.app,https://${var.project_id}.firebaseapp.com"
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.postgres.connection_name]
      }
    }
  }

  depends_on = [
    google_project_service.enabled,
    google_project_iam_member.api_cloudsql,
    google_secret_manager_secret_iam_member.api_secret_access,
    google_secret_manager_secret_version.database_password,
    google_sql_database.meetings,
    google_sql_user.app,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_job" "migrate" {
  project             = var.project_id
  name                = "${var.project_name}-migrate"
  location            = var.region
  deletion_protection = false
  template {
    template {
      service_account = google_service_account.api.email
      max_retries     = 1
      containers {
        image   = var.api_image
        command = ["alembic"]
        args    = ["upgrade", "head"]
        env {
          name  = "DB_HOST"
          value = "/cloudsql/${google_sql_database_instance.postgres.connection_name}"
        }
        env {
          name  = "DB_NAME"
          value = local.db_name
        }
        env {
          name  = "DB_USER"
          value = local.db_user
        }
        env {
          name  = "RUN_MIGRATIONS_ON_START"
          value = "false"
        }
        env {
          name = "DB_PASSWORD"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.database_password.secret_id
              version = google_secret_manager_secret_version.database_password.version
            }
          }
        }
        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }
      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.postgres.connection_name]
        }
      }
    }
  }
  depends_on = [
    google_project_iam_member.api_cloudsql,
    google_secret_manager_secret_iam_member.api_secret_access,
    google_secret_manager_secret_version.database_password,
    google_sql_database.meetings,
    google_sql_user.app,
  ]
}

resource "google_firebase_hosting_site" "app" {
  provider = google-beta
  project  = var.project_id
  site_id  = var.project_id
  depends_on = [
    google_firebase_project.app,
    google_cloud_run_v2_service.api,
  ]
}
