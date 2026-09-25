# Secure Parental Control Chat

# Requirements
- Should be a mix of web app + Ubuntu thick client (for student)
- Think AOL instant messenger chat (personal messages from one or more parents to child)
- Ubuntu desktop application that can be setup as startup running app
- Allow popup in Ubuntu UI for new message window from parent.
- Allow app to snap a screenshot when requested from parent app
- Child app registration should be via a reg code vs login
- Parent registration should be via username/password/cognito login
- Message from parent should override any open "full screen" applications (e.g. should show, even if they are playing a game)

# Backend/Web App/Server Component
- Host on AWS lambda + cognito + API gateway
- Use dynamodb for chat history


# Deployment
- Via terraform using an AWS Role assumed by a github runner.
- optimize for low cost
- use parentchat.ferguson.ninja as the domain
- AWS Role should have access to Route53


# Local Development
- Allow registration of child client to localhost
- Allow parent bypass auth for local development

