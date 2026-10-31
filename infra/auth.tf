resource "aws_cognito_user_pool_domain" "main" {
  certificate_arn       = null
  domain                = "${var.project_name}-${data.aws_caller_identity.current.account_id}"
  managed_login_version = 1
  region                = "us-east-1"
  user_pool_id          = aws_cognito_user_pool.main.id
}

resource "aws_cognito_user_pool_client" "web" {
  access_token_validity                         = 1
  allowed_oauth_flows                           = ["code"]
  allowed_oauth_flows_user_pool_client          = true
  allowed_oauth_scopes                          = ["email", "openid", "profile"]
  auth_session_validity                         = 3
  callback_urls                                 = var.app_urls
  enable_propagate_additional_user_context_data = false
  enable_token_revocation                       = true
  explicit_auth_flows                           = ["ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_SRP_AUTH"]
  generate_secret                               = null
  id_token_validity                             = 1
  logout_urls                                   = var.app_urls
  name                                          = "${var.project_name}-web"
  prevent_user_existence_errors                 = "ENABLED"
  read_attributes                               = []
  refresh_token_validity                        = 30
  region                                        = "us-east-1"
  supported_identity_providers                  = ["COGNITO", "Google"]
  user_pool_id                                  = aws_cognito_user_pool.main.id
  write_attributes                              = []
}

resource "aws_cognito_user_pool" "main" {
  alias_attributes           = null
  auto_verified_attributes   = ["email"]
  deletion_protection        = "INACTIVE"
  mfa_configuration          = "OFF"
  name                       = "${var.project_name}-users"
  region                     = "us-east-1"
  sms_authentication_message = null
  tags = {
    PROJECT_NAME = var.project_name
  }
  tags_all = {
    PROJECT_NAME = var.project_name
  }
  user_pool_tier      = "ESSENTIALS"
  username_attributes = ["email"]
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
  admin_create_user_config {
    allow_admin_create_user_only = false
  }
  email_configuration {
    configuration_set      = null
    email_sending_account  = "COGNITO_DEFAULT"
    from_email_address     = null
    reply_to_email_address = null
    source_arn             = null
  }
  password_policy {
    minimum_length                   = 8
    password_history_size            = 0
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = false
    require_uppercase                = true
    temporary_password_validity_days = 7
  }
  schema {
    attribute_data_type      = "String"
    developer_only_attribute = false
    mutable                  = true
    name                     = "email"
    required                 = true
    string_attribute_constraints {
      max_length = "2048"
      min_length = "0"
    }
  }
  sign_in_policy {
    allowed_first_auth_factors = ["PASSWORD"]
  }
  username_configuration {
    case_sensitive = false
  }
  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
  }
}

resource "aws_cognito_identity_provider" "google" {
  attribute_mapping = {
    email          = "email"
    email_verified = "email_verified"
    name           = "name"
    username       = "sub"
  }
  idp_identifiers = []
  provider_details = {
    attributes_url                = "https://people.googleapis.com/v1/people/me?personFields="
    attributes_url_add_attributes = "true"
    authorize_scopes              = "openid email profile"
    authorize_url                 = "https://accounts.google.com/o/oauth2/v2/auth"
    client_id                     = var.google_client_id
    client_secret                 = var.google_client_secret
    oidc_issuer                   = "https://accounts.google.com"
    token_request_method          = "POST"
    token_url                     = "https://www.googleapis.com/oauth2/v4/token"
  }
  provider_name = "Google"
  provider_type = "Google"
  region        = "us-east-1"
  user_pool_id  = aws_cognito_user_pool.main.id
}
