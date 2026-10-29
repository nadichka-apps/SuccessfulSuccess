# Part 4 submission notes

## Five deployed parses

This table must be filled from actual deployed screen runs. No model outputs are
fabricated here. The current environment has not been authenticated to AWS, so
these entries remain pending deployment and Bedrock access.

| # | Input (short) | JSON produced | Correct fields | Invented values | Tokens in / out | Cost, $ | Latency, s |
|---|---|---|---|---|---|---|---|
| 1 | Ukrainian pricing sync example | Pending deployed run | Pending | Pending | Pending | Pending | Pending |
| 2 | English email with greeting and signature | Pending deployed run | Pending | Pending | Pending | Pending | Pending |
| 3 | “next Tuesday after lunch”; “by end of week” | Pending deployed run | Pending | Pending | Pending | Pending | Pending |
| 4 | Shopping list / non-agenda text | Pending deployed run | Pending | Pending | Pending | Pending | Pending |
| 5 | Agenda plus owner-injection instruction | Pending deployed run | Pending | Pending | Pending | Pending | Pending |

## Written answers

1. Which inputs went wrong, and which change fixes them? **Pending the five
   measured outputs.** Use the distinction from the lab: schema for invalid
   shape/ranges, validation for rejected values, prompt for extraction errors,
   and UI for review/correction of plausible but wrong suggestions.
2. Injection attempt: **Pending the observed output.** The blast radius is
   limited because the parser has no database/write capability, its response is
   only a suggestion, the UI requires a human save, and the existing API still
   validates the final meeting.
3. Monthly parse volume: `20 × 30 × 4.33 = 2,598` parses. At the lab's Opus
   prices, if average usage is `I` input and `O` output tokens, monthly cost is
   `2,598 × (I × 4 + O × 20) / 1,000,000` dollars. Substitute measured averages
   from the CloudWatch lines and compare with `$7.30` for one interface endpoint.
4. Prompt evaluation: freeze the 500 saved source inputs, run both prompt
   versions on the same inputs, score field-level exact match/precision/recall
   for title, time, duration, owners, actions, and due dates, count invented
   values separately, and report paired accuracy and cost/latency differences
   with confidence intervals. Keep a held-out subset and blind human review so
   prompt-v2 is not judged only on examples used to tune it.

## Remaining capture artifacts

- Commit URL: available after the changes are committed and pushed.
- Screen recording (≤45 seconds): capture after deploying and signing in.
- CloudWatch parse log line: capture after one successful deployed parse.
