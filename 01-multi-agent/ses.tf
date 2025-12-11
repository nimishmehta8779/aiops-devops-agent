# Optional: SES email identity verification
resource "aws_ses_email_identity" "sender" {
  count = var.enable_ses ? 1 : 0
  email = var.sender_email
}

resource "aws_ses_email_identity" "recipient" {
  count = var.enable_ses ? 1 : 0
  email = var.default_email
}

# SES configuration set (optional)
resource "aws_ses_configuration_set" "aiops" {
  count = var.enable_ses ? 1 : 0
  name  = "${var.project_name}-ses-config"
}
