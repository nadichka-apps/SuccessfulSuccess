resource "aws_lambda_function" "parser" {
  architectures                      = ["x86_64"]
  code_sha256                        = "cffee049dff2903d829a75f0cd9b85fb9bb7c74cfa49f9e9d11b3a9ac75b097b"
  code_signing_config_arn            = null
  description                        = "Parse pasted agenda text with Amazon Nova on Amazon Bedrock"
  filename                           = null
  function_name                      = "${var.project_name}-agenda-parser"
  handler                            = null
  image_uri                          = var.parser_image_uri
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
  role                               = "arn:aws:iam::063280428772:role/successfulsuccess-ai-ParserRole-gAkYZpgpzp9K"
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
      COGNITO_CLIENT_ID    = aws_cognito_user_pool_client.web.id
      COGNITO_REGION       = "us-east-1"
      COGNITO_USER_POOL_ID = aws_cognito_user_pool.main.id
      PARSER_MODEL         = var.parser_model
      PARSER_REGION        = "us-east-1"
    }
  }
  ephemeral_storage {
    size = 512
  }
  image_config {
    command           = ["app.ai.agenda.handler"]
    entry_point       = []
    working_directory = null
  }
  logging_config {
    application_log_level = null
    log_format            = "Text"
    log_group             = "/aws/lambda/${var.project_name}-agenda-parser"
    system_log_level      = null
  }
  tracing_config {
    mode = "PassThrough"
  }
}

resource "aws_lambda_permission" "parser_url" {
  action                   = "lambda:InvokeFunctionUrl"
  event_source_token       = null
  function_name            = "${var.project_name}-agenda-parser"
  function_url_auth_type   = "NONE"
  invoked_via_function_url = null
  principal                = "*"
  principal_org_id         = null
  qualifier                = null
  region                   = "us-east-1"
  source_account           = null
  source_arn               = null
  statement_id             = "successfulsuccess-ai-ParserUrlPermission-xyopWtCYAG0U"
}

resource "aws_cloudwatch_log_group" "parser" {
  deletion_protection_enabled = false
  kms_key_id                  = null
  log_group_class             = "STANDARD"
  name                        = "/aws/lambda/${var.project_name}-agenda-parser"
  region                      = "us-east-1"
  retention_in_days           = 30
  skip_destroy                = false
  tags = {
    PROJECT_NAME = var.project_name
  }
  tags_all = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_lambda_permission" "parser_invoke" {
  action                   = "lambda:InvokeFunction"
  event_source_token       = null
  function_name            = "${var.project_name}-agenda-parser"
  function_url_auth_type   = null
  invoked_via_function_url = true
  principal                = "*"
  principal_org_id         = null
  qualifier                = null
  region                   = "us-east-1"
  source_account           = null
  source_arn               = null
  statement_id             = "successfulsuccess-ai-ParserInvokePermission-p191vDCpvRPI"
}

resource "aws_lambda_function_url" "parser" {
  authorization_type = "NONE"
  function_name      = "${var.project_name}-agenda-parser"
  invoke_mode        = "BUFFERED"
  qualifier          = null
  region             = "us-east-1"
  cors {
    allow_credentials = false
    allow_headers     = ["authorization", "content-type"]
    allow_methods     = ["POST"]
    allow_origins     = [var.allowed_origin]
    expose_headers    = []
    max_age           = 600
  }
}

resource "aws_iam_role" "parser" {
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
  name                  = "successfulsuccess-ai-ParserRole-gAkYZpgpzp9K"
  path                  = "/"
  permissions_boundary  = null
  tags = {
    PROJECT_NAME = var.project_name
  }
  tags_all = {
    PROJECT_NAME = var.project_name
  }
}
