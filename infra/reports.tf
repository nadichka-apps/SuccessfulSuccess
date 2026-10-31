resource "aws_scheduler_schedule" "weekly" {
  action_after_completion      = "NONE"
  description                  = "Triggers weekly meetings report every Monday at 07:00 Europe/Kyiv"
  end_date                     = null
  group_name                   = "default"
  kms_key_arn                  = null
  name                         = "${var.project_name}-weekly-schedule"
  region                       = "us-east-1"
  schedule_expression          = "cron(0 7 ? * MON *)"
  schedule_expression_timezone = "Europe/Kyiv"
  start_date                   = null
  state                        = "ENABLED"
  flexible_time_window {
    mode = "OFF"
  }
  target {
    arn = "arn:aws:sqs:us-east-1:063280428772:successfulsuccess-weekly-report-queue"
    input = jsonencode({
      action = "weekly_report"
    })
    role_arn = "arn:aws:iam::063280428772:role/successfulsuccess-reports-SchedulerRole-s9lVUe0CkCw8"
    retry_policy {
      maximum_event_age_in_seconds = 86400
      maximum_retry_attempts       = 185
    }
  }
}

resource "aws_sqs_queue_policy" "weekly" {
  policy = jsonencode({
    Statement = [{
      Action = "sqs:SendMessage"
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = "arn:aws:scheduler:us-east-1:063280428772:schedule/*"
        }
      }
      Effect = "Allow"
      Principal = {
        Service = "scheduler.amazonaws.com"
      }
      Resource = "arn:aws:sqs:us-east-1:063280428772:successfulsuccess-weekly-report-queue"
      Sid      = "AllowSchedulerSendMessage"
    }]
    Version = "2012-10-17"
  })
  queue_url = "https://sqs.us-east-1.amazonaws.com/063280428772/successfulsuccess-weekly-report-queue"
  region    = "us-east-1"
}

resource "aws_lambda_function" "mailer" {
  architectures                      = ["x86_64"]
  code_sha256                        = "ef9faf8716b56f98d8ed3b0acdbd3458a6afe9cceebd86d0942d311527d41318"
  code_signing_config_arn            = null
  description                        = "Delivers weekly reports via Amazon SES upon S3 ObjectCreated"
  filename                           = null
  function_name                      = "${var.project_name}-report-mailer"
  handler                            = null
  image_uri                          = var.reports_image_uri
  kms_key_arn                        = null
  layers                             = []
  memory_size                        = 256
  package_type                       = "Image"
  publish                            = null
  publish_to                         = null
  region                             = "us-east-1"
  replace_security_groups_on_destroy = null
  replacement_security_group_ids     = null
  reserved_concurrent_executions     = -1
  role                               = "arn:aws:iam::063280428772:role/successfulsuccess-reports-MailerRole-WjBAykDHxXpK"
  runtime                            = null
  s3_bucket                          = null
  s3_key                             = null
  s3_object_version                  = null
  skip_destroy                       = false
  source_kms_key_arn                 = null
  tags = {
    PROJECT_NAME = var.project_name
  }
  tags_all = {
    PROJECT_NAME = var.project_name
  }
  timeout                              = 30
  use_resource_timeout_for_propagation = null
  environment {
    variables = {
      APP_TIMEZONE            = var.app_timezone
      LOG_LEVEL               = var.log_level
      REPORTS_BUCKET_NAME     = "${var.project_name}-reports-${data.aws_caller_identity.current.account_id}"
      REPORTS_DEDUP_TABLE     = "${var.project_name}-reports-dedup"
      REPORTS_RECIPIENT_EMAIL = var.recipient_email
      REPORTS_SENDER_EMAIL    = var.sender_email
    }
  }
  ephemeral_storage {
    size = 512
  }
  image_config {
    command           = ["app.reports.mailer.handler"]
    entry_point       = []
    working_directory = null
  }
  logging_config {
    application_log_level = null
    log_format            = "Text"
    log_group             = "/aws/lambda/${var.project_name}-report-mailer"
    system_log_level      = null
  }
  tracing_config {
    mode = "PassThrough"
  }
}

resource "aws_lambda_event_source_mapping" "builder" {
  batch_size                         = 1
  bisect_batch_on_function_error     = false
  enabled                            = true
  event_source_arn                   = "arn:aws:sqs:us-east-1:063280428772:successfulsuccess-weekly-report-queue"
  function_name                      = "arn:aws:lambda:us-east-1:063280428772:function:successfulsuccess-report-builder"
  function_response_types            = []
  kms_key_arn                        = null
  maximum_batching_window_in_seconds = 0
  maximum_retry_attempts             = 0
  queues                             = []
  region                             = "us-east-1"
  starting_position                  = null
  starting_position_timestamp        = null
  tags = {
    PROJECT_NAME = var.project_name
  }
  tags_all = {
    PROJECT_NAME = var.project_name
  }
  topics                               = []
  tumbling_window_in_seconds           = 0
  use_resource_timeout_for_propagation = null
}

resource "aws_sqs_queue" "dlq" {
  content_based_deduplication       = false
  delay_seconds                     = 0
  fifo_queue                        = false
  kms_data_key_reuse_period_seconds = 300
  kms_master_key_id                 = null
  max_message_size                  = 1048576
  message_retention_seconds         = 1209600
  name                              = "${var.project_name}-weekly-report-dlq"
  receive_wait_time_seconds         = 0
  region                            = "us-east-1"
  sqs_managed_sse_enabled           = true
  tags = {
    PROJECT_NAME = var.project_name
  }
  tags_all = {
    PROJECT_NAME = var.project_name
  }
  visibility_timeout_seconds = 30
}

resource "aws_cloudwatch_log_group" "mailer" {
  deletion_protection_enabled = false
  kms_key_id                  = null
  log_group_class             = "STANDARD"
  name                        = "/aws/lambda/${var.project_name}-report-mailer"
  region                      = "us-east-1"
  retention_in_days           = 7
  skip_destroy                = false
  tags = {
    PROJECT_NAME = var.project_name
  }
  tags_all = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_cloudwatch_log_group" "builder" {
  deletion_protection_enabled = false
  kms_key_id                  = null
  log_group_class             = "STANDARD"
  name                        = "/aws/lambda/${var.project_name}-report-builder"
  region                      = "us-east-1"
  retention_in_days           = 7
  skip_destroy                = false
  tags = {
    PROJECT_NAME = var.project_name
  }
  tags_all = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_lambda_function" "builder" {
  architectures                      = ["x86_64"]
  code_sha256                        = "ef9faf8716b56f98d8ed3b0acdbd3458a6afe9cceebd86d0942d311527d41318"
  code_signing_config_arn            = null
  description                        = "Builds weekly meetings CSV report and uploads to S3"
  filename                           = null
  function_name                      = "${var.project_name}-report-builder"
  handler                            = null
  image_uri                          = var.reports_image_uri
  kms_key_arn                        = null
  layers                             = []
  memory_size                        = 512
  package_type                       = "Image"
  publish                            = null
  publish_to                         = null
  region                             = "us-east-1"
  replace_security_groups_on_destroy = null
  replacement_security_group_ids     = null
  reserved_concurrent_executions     = -1
  role                               = "arn:aws:iam::063280428772:role/successfulsuccess-reports-ReportBuilderRole-pNI7yaHl2Cal"
  runtime                            = null
  s3_bucket                          = null
  s3_key                             = null
  s3_object_version                  = null
  skip_destroy                       = false
  source_kms_key_arn                 = null
  tags = {
    PROJECT_NAME = var.project_name
  }
  tags_all = {
    PROJECT_NAME = var.project_name
  }
  timeout                              = 60
  use_resource_timeout_for_propagation = null
  environment {
    variables = {
      APP_TIMEZONE        = var.app_timezone
      DATABASE_URL        = var.database_url
      LOG_LEVEL           = var.log_level
      REPORTS_BUCKET_NAME = "${var.project_name}-reports-${data.aws_caller_identity.current.account_id}"
    }
  }
  ephemeral_storage {
    size = 512
  }
  image_config {
    command           = ["app.reports.builder.handler"]
    entry_point       = []
    working_directory = null
  }
  logging_config {
    application_log_level = null
    log_format            = "Text"
    log_group             = "/aws/lambda/${var.project_name}-report-builder"
    system_log_level      = null
  }
  tracing_config {
    mode = "PassThrough"
  }
  vpc_config {
    ipv6_allowed_for_dual_stack = false
    security_group_ids          = [var.function_security_group_id]
    subnet_ids                  = var.subnet_ids
  }
}

resource "aws_iam_role" "mailer" {
  assume_role_policy = jsonencode({
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
    Version = "2012-10-17"
  })
  description           = null
  force_detach_policies = false
  max_session_duration  = 3600
  name                  = "successfulsuccess-reports-MailerRole-WjBAykDHxXpK"
  path                  = "/"
  permissions_boundary  = null
  tags = {
    PROJECT_NAME = var.project_name
  }
  tags_all = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_sqs_queue" "weekly" {
  content_based_deduplication       = false
  delay_seconds                     = 0
  fifo_queue                        = false
  kms_data_key_reuse_period_seconds = 300
  kms_master_key_id                 = null
  max_message_size                  = 1048576
  message_retention_seconds         = 345600
  name                              = "${var.project_name}-weekly-report-queue"
  policy = jsonencode({
    Statement = [{
      Action = "sqs:SendMessage"
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = "arn:aws:scheduler:us-east-1:063280428772:schedule/*"
        }
      }
      Effect = "Allow"
      Principal = {
        Service = "scheduler.amazonaws.com"
      }
      Resource = "arn:aws:sqs:us-east-1:063280428772:successfulsuccess-weekly-report-queue"
      Sid      = "AllowSchedulerSendMessage"
    }]
    Version = "2012-10-17"
  })
  receive_wait_time_seconds = 0
  redrive_policy = jsonencode({
    deadLetterTargetArn = "arn:aws:sqs:us-east-1:063280428772:successfulsuccess-weekly-report-dlq"
    maxReceiveCount     = 3
  })
  region                  = "us-east-1"
  sqs_managed_sse_enabled = true
  tags = {
    PROJECT_NAME = var.project_name
  }
  tags_all = {
    PROJECT_NAME = var.project_name
  }
  visibility_timeout_seconds = 360
}

resource "aws_lambda_permission" "mailer" {
  action                   = "lambda:InvokeFunction"
  event_source_token       = null
  function_name            = "${var.project_name}-report-mailer"
  function_url_auth_type   = null
  invoked_via_function_url = null
  principal                = "s3.amazonaws.com"
  principal_org_id         = null
  qualifier                = null
  region                   = "us-east-1"
  source_account           = "063280428772"
  source_arn               = "arn:aws:s3:::successfulsuccess-reports-063280428772"
  statement_id             = "successfulsuccess-reports-MailerLambdaPermission-1NYE9ZflHjBd"
}

resource "aws_vpc_endpoint" "s3_gateway" {
  auto_accept     = null
  ip_address_type = "ipv4"
  policy = jsonencode({
    Statement = [{
      Action    = "*"
      Effect    = "Allow"
      Principal = "*"
      Resource  = "*"
    }]
    Version = "2008-10-17"
  })
  private_dns_enabled        = false
  region                     = "us-east-1"
  resource_configuration_arn = null
  route_table_ids            = var.route_table_ids
  security_group_ids         = []
  service_name               = "com.amazonaws.us-east-1.s3"
  service_network_arn        = null
  service_region             = "us-east-1"
  subnet_ids                 = []
  tags = {
    PROJECT_NAME = var.project_name
  }
  tags_all = {
    PROJECT_NAME = var.project_name
  }
  vpc_endpoint_type = "Gateway"
  vpc_id            = var.vpc_id
  dns_options {
    dns_record_ip_type                             = "service-defined"
    private_dns_only_for_inbound_resolver_endpoint = false
  }
}

resource "aws_iam_role" "builder" {
  assume_role_policy = jsonencode({
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
    Version = "2012-10-17"
  })
  description           = null
  force_detach_policies = false
  max_session_duration  = 3600
  name                  = "successfulsuccess-reports-ReportBuilderRole-pNI7yaHl2Cal"
  path                  = "/"
  permissions_boundary  = null
  tags = {
    PROJECT_NAME = var.project_name
  }
  tags_all = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_iam_role" "scheduler" {
  assume_role_policy = jsonencode({
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "scheduler.amazonaws.com"
      }
    }]
    Version = "2012-10-17"
  })
  description           = null
  force_detach_policies = false
  max_session_duration  = 3600
  name                  = "successfulsuccess-reports-SchedulerRole-s9lVUe0CkCw8"
  path                  = "/"
  permissions_boundary  = null
  tags = {
    PROJECT_NAME = var.project_name
  }
  tags_all = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_dynamodb_table" "dedup" {
  billing_mode                = "PAY_PER_REQUEST"
  deletion_protection_enabled = false
  hash_key                    = "report_key"
  name                        = "${var.project_name}-reports-dedup"
  range_key                   = null
  read_capacity               = 0
  region                      = "us-east-1"
  restore_backup_arn          = null
  restore_date_time           = null
  restore_source_name         = null
  restore_source_table_arn    = null
  restore_to_latest_time      = null
  stream_enabled              = false
  table_class                 = "STANDARD"
  tags = {
    PROJECT_NAME = var.project_name
  }
  tags_all = {
    PROJECT_NAME = var.project_name
  }
  write_capacity = 0
  attribute {
    name = "report_key"
    type = "S"
  }
  point_in_time_recovery {
    enabled = false
  }
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}

resource "aws_s3_bucket" "reports" {
  bucket              = "${var.project_name}-reports-${data.aws_caller_identity.current.account_id}"
  bucket_namespace    = "global"
  force_destroy       = false
  object_lock_enabled = false
  region              = "us-east-1"
  tags = {
    PROJECT_NAME = var.project_name
  }
  tags_all = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_s3_bucket_public_access_block" "reports" {
  bucket                  = aws_s3_bucket.reports.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "reports" {
  bucket = aws_s3_bucket.reports.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id
  rule {
    id     = "ExpireReportsAfter90Days"
    status = "Enabled"
    filter {}
    expiration {
      days = 90
    }
  }
}

resource "aws_s3_bucket_notification" "reports" {
  bucket = aws_s3_bucket.reports.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.mailer.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "reports/"
    filter_suffix       = ".csv"
  }
  depends_on = [aws_lambda_permission.mailer]
}
