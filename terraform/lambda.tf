############################
# Lambda IAM Role
############################

resource "aws_iam_role" "lambda" {
  name = "${var.project_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-lambda-role"
  }
}

resource "aws_iam_role_policy" "lambda_dynamodb" {
  name = "${var.project_name}-lambda-dynamodb"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem",
        ]
        Resource = [
          aws_dynamodb_table.children.arn,
          "${aws_dynamodb_table.children.arn}/index/*",
          aws_dynamodb_table.registration_codes.arn,
          "${aws_dynamodb_table.registration_codes.arn}/index/*",
          aws_dynamodb_table.messages.arn,
          "${aws_dynamodb_table.messages.arn}/index/*",
          aws_dynamodb_table.screenshot_requests.arn,
          "${aws_dynamodb_table.screenshot_requests.arn}/index/*",
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_s3" {
  name = "${var.project_name}-lambda-s3"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
        ]
        Resource = [
          aws_s3_bucket.screenshots.arn,
          "${aws_s3_bucket.screenshots.arn}/*",
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

############################
# Lambda Function
############################

data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../backend"
  output_path = "${path.module}/files/lambda.zip"
}

resource "aws_lambda_function" "api" {
  function_name    = "${var.project_name}-api"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  handler          = "handler.handler"
  runtime          = "python3.12"
  role             = aws_iam_role.lambda.arn
  memory_size      = 256
  timeout          = 30

  environment {
    variables = {
      TABLE_CHILDREN            = aws_dynamodb_table.children.name
      TABLE_REGISTRATION_CODES  = aws_dynamodb_table.registration_codes.name
      TABLE_MESSAGES            = aws_dynamodb_table.messages.name
      TABLE_SCREENSHOT_REQUESTS = aws_dynamodb_table.screenshot_requests.name
      S3_SCREENSHOTS_BUCKET     = aws_s3_bucket.screenshots.id
      AWS_REGION_NAME           = var.aws_region
      COGNITO_USER_POOL_ID      = aws_cognito_user_pool.main.id
      COGNITO_CLIENT_ID         = aws_cognito_user_pool_client.web.id
    }
  }

  tags = {
    Name = "${var.project_name}-api"
  }
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}
