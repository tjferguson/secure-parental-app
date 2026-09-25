variable "aws_region" {
  description = "AWS region for resource deployment"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "parentchat"
}

variable "domain_name" {
  description = "Primary domain name for the application"
  type        = string
  default     = "parentchat.ferguson.ninja"
}

variable "route53_zone_name" {
  description = "Route53 hosted zone name"
  type        = string
  default     = "ferguson.ninja"
}

variable "github_repo" {
  description = "GitHub repository in format owner/repo for OIDC trust policy"
  type        = string
  default     = "tferguson1028/parent-sec-chat"
}
