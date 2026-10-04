# Lambda + API Gateway removed — replaced by EC2 instance behind ALB.
# See ec2.tf and alb.tf.
#
# The backend Python server (local_server.py) runs directly on the
# instance, serving both the API and the web/dist static files.
