output "project_id" {
  value = var.project_id
}

output "region" {
  value = var.region
}

output "artifact_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.backend.repository_id}"
}

output "api_url" {
  value = google_cloud_run_v2_service.api.uri
}

output "api_health_url" {
  value = "${google_cloud_run_v2_service.api.uri}/health"
}

output "firebase_site_url" {
  value = "https://${google_firebase_hosting_site.app.site_id}.web.app"
}

output "cloud_sql_connection_name" {
  value = google_sql_database_instance.postgres.connection_name
}

output "migration_job" {
  value = google_cloud_run_v2_job.migrate.name
}
