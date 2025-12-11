provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

provider "aws" {
  alias  = "us_west_2"
  region = "us-west-2"
}

module "central_stack" {
  source = "./modules/regional-stack"
  providers = {
    aws = aws.us_east_1
  }

  aws_region     = "us-east-1"
  is_central     = true
  central_region = "us-east-1"
}

module "satellite_stack" {
  source = "./modules/regional-stack"
  providers = {
    aws = aws.us_west_2
  }

  aws_region     = "us-west-2"
  is_central     = false
  central_region = "us-east-1"
  # This relies on the default event bus in central region
  central_event_bus_arn = "arn:aws:events:us-east-1:${data.aws_caller_identity.current.account_id}:event-bus/default"
}

data "aws_caller_identity" "current" {}

output "central_orchestrator" {
  value = module.central_stack.regional_orchestrator_arn
}

output "satellite_orchestrator" {
  value = module.satellite_stack.regional_orchestrator_arn
}
