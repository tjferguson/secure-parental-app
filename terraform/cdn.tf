# CloudFront removed — the EC2 instance behind the ALB serves both
# the API and static web files from web/dist.
#
# To re-add a CDN layer later, create a CloudFront distribution with
# the ALB as the origin.
