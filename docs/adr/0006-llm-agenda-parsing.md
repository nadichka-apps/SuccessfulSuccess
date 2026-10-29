# ADR 0006: LLM agenda parsing

- Status: Accepted
- Date: 2026-10-29

## Context

Users paste agendas from email, chat, and notes. Text may contain mistakes or
prompt injection, each model call costs money, and the current application has
no NAT gateway. The existing meetings API is the trusted, validated write path.

## Decision

Use Claude Opus 5.5 through Amazon Bedrock (`anthropic.claude-opus-5-5`) and
request one `record_agenda` tool call matching a Pydantic schema. Keep the parser
as a separate Lambda outside the VPC: it needs no database, avoids a Bedrock
interface endpoint, and incurs no VPC networking cost while idle. Require a
Cognito access token, cap pasted text at 10,000 characters, validate the model
response, log model/prompt version/token counts/latency/cost, and preserve the
suggestion with the final meeting. A person reviews and edits the form; only the
existing meetings API writes data. Pasted text is untrusted data.

## Alternatives considered

- Call Bedrock from the API inside the VPC: rejected because it needs a paid
  interface endpoint (the lab estimate is $7.30/month) for a function that only
  parses text and does not need database access.
- Call Anthropic directly: rejected because Bedrock uses the AWS identity and
  billing controls already used by this deployment.
- Use regular expressions: rejected because emails and multilingual notes have
  variable structure, names, and relative dates that brittle patterns cannot
  reliably resolve.

## Consequences

At the lab's Opus 5.5 list rates, a parse costs
`input_tokens × $4/M + output_tokens × $20/M`; production logs record the
measured cost per request. Bedrock downtime leaves the user able to type meeting
details by hand and does not affect other Spry features. Suggestions and final
values can be compared to evaluate future prompt versions. The broad
`bedrock-mantle:CreateInference` resource scope is retained for this lab and
should be narrowed when AWS exposes a suitable model resource scope.
