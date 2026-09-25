resource "aws_dynamodb_table" "children" {
  name         = "${var.project_name}-children"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "childId"

  attribute {
    name = "childId"
    type = "S"
  }

  attribute {
    name = "parentId"
    type = "S"
  }

  global_secondary_index {
    name            = "parentId-index"
    hash_key        = "parentId"
    projection_type = "ALL"
  }

  tags = {
    Name = "${var.project_name}-children"
  }
}

resource "aws_dynamodb_table" "registration_codes" {
  name         = "${var.project_name}-registration-codes"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "code"

  attribute {
    name = "code"
    type = "S"
  }

  tags = {
    Name = "${var.project_name}-registration-codes"
  }
}

resource "aws_dynamodb_table" "messages" {
  name         = "${var.project_name}-messages"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "conversationId"
  range_key    = "timestamp"

  attribute {
    name = "conversationId"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  tags = {
    Name = "${var.project_name}-messages"
  }
}

resource "aws_dynamodb_table" "screenshot_requests" {
  name         = "${var.project_name}-screenshot-requests"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "childId"
  range_key    = "requestId"

  attribute {
    name = "childId"
    type = "S"
  }

  attribute {
    name = "requestId"
    type = "S"
  }

  tags = {
    Name = "${var.project_name}-screenshot-requests"
  }
}
