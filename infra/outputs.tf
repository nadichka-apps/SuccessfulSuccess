data "aws_caller_identity" "current" {}

output "user_pool_id" {
  value       = aws_cognito_user_pool.main.id
  description = "Cognito user pool ID"
}

output "user_pool_client_id" {
  value       = aws_cognito_user_pool_client.web.id
  description = "Public Cognito browser client ID"
}

output "issuer" {
  value       = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
  description = "Cognito token issuer"
}

output "hosted_domain" {
  value       = "${aws_cognito_user_pool_domain.main.domain}.auth.${var.region}.amazoncognito.com"
  description = "Cognito hosted UI domain"
}

output "google_redirect_uri" {
  value       = "https://${aws_cognito_user_pool_domain.main.domain}.auth.${var.region}.amazoncognito.com/oauth2/idpresponse"
  description = "Google OAuth redirect URI"
}

output "google_enabled" {
  value       = var.google_client_id != ""
  description = "Whether Google sign-in is configured"
}

output "reports_bucket_name" {
  value       = aws_s3_bucket.reports.id
  description = "Private reports bucket"
}

output "weekly_report_queue_url" {
  value       = aws_sqs_queue.weekly.id
  description = "Weekly report SQS queue URL"
}

output "weekly_report_dlq_url" {
  value       = aws_sqs_queue.dlq.id
  description = "Weekly report dead-letter queue URL"
}

output "report_builder_function_name" {
  value       = aws_lambda_function.builder.function_name
  description = "Report Builder Lambda function name"
}

output "mailer_function_name" {
  value       = aws_lambda_function.mailer.function_name
  description = "Report Mailer Lambda function name"
}

output "dedup_table_name" {
  value       = aws_dynamodb_table.dedup.name
  description = "Email deduplication table"
}

output "schedule_name" {
  value       = aws_scheduler_schedule.weekly.name
  description = "Weekly report schedule name"
}

output "parser_url" {
  value       = aws_lambda_function_url.parser.function_url
  description = "Agenda parser Lambda Function URL"
}

output "parser_function_name" {
  value       = aws_lambda_function.parser.function_name
  description = "Agenda parser Lambda function name"
}
