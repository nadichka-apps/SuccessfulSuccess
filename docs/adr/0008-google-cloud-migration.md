# ADR 0008: Google Cloud landing zone and core migration

- **Status:** accepted for the lab
- **Date:** 2026-11-18

## Context

SuccessfulSuccess currently serves a static Next.js export from S3/CloudFront,
FastAPI from a Lambda function URL, and PostgreSQL from Aurora Serverless v2.
The core needs to run on Google Cloud while Cognito sign-in, weekly reports and
agenda parsing remain on AWS. The application already validates Cognito access
tokens in FastAPI, so the GCP API can stay public at the transport layer while
continuing to require a valid token for protected routes.

## Decisions

| AWS component | GCP choice | Decision | Reason / trade-off |
|---|---|---|---|
| S3 + CloudFront static frontend | Firebase Hosting | Replace for the core | CDN and managed TLS with a free student-scale quota; `/api/**` rewrites to Cloud Run. Keep the current S3/CloudFront stack available on AWS. |
| Lambda + function URL, FastAPI | Cloud Run | Replace for the core | Runs the existing container and scales to zero; public invoker is needed for Firebase rewrites, and FastAPI still verifies Cognito tokens. |
| ECR | Artifact Registry | Replace for the GCP image | Native regional Docker registry, separate from ECR. |
| Aurora Serverless v2 | Cloud SQL for PostgreSQL `db-f1-micro` | Replace for the lab | Preserves SQLAlchemy, PostgreSQL schema and Alembic migrations. Adds an instance-hour bill while running; stop it between lab sessions or destroy it. |
| DynamoDB (not used by the app) | Firestore | Drop | The project uses relational meetings, users and ownership. Moving to Firestore would duplicate/restructure data and rewrite queries without a lab benefit. |
| Cognito user pool + Google | Identity Platform / Firebase Authentication | Keep on AWS | Stretch goal explicitly leaves sign-in on AWS. Existing UI and API already use Cognito tokens; migration is not needed to prove the core. |
| EventBridge Scheduler | Cloud Scheduler | Keep on AWS for now | Weekly reports stay on AWS; no GCP scheduler job is needed for the core. |
| SQS | Pub/Sub or Cloud Tasks | Keep on AWS for now | Existing queue/report pipeline remains on AWS. Cloud Tasks is the closer work-queue match if reports move later. |
| S3 event → Lambda | Cloud Storage + Eventarc → Cloud Run | Keep on AWS for now | Agenda and report flows stay on AWS, with no GCP event-driven storage requirement in the core. |
| SES | External email provider or SES | Keep SES on AWS | Weekly email reports stay on AWS. If moved later, keep the provider key in Secret Manager. |
| Bedrock (Nova) | Vertex AI | Keep on AWS for now | Agenda parser remains a stretch goal; no model migration is required for the core. |
| Secrets Manager / Parameter Store | Secret Manager | Replace for GCP resources | Terraform creates the DB password and secret version; Cloud Run and the migration job read it through their dedicated service account. |
| CloudWatch Logs | Cloud Logging | Replace for GCP resources | Cloud Run stdout/stderr is collected by the managed logging service. |
| IAM roles | Service accounts + IAM roles | Replace for GCP resources | Separate Terraform identity from the API runtime identity; grant only deployment, SQL and secret access roles. |
| Terraform AWS provider | Terraform Google provider | Add alongside AWS | `gcp/` has its own HCP Terraform workspace/state so plans are isolated by cloud. |

## Database alternatives

Cloud SQL is selected because it retains the current PostgreSQL models,
relationships and Alembic migrations. It is the smallest shared-core tier, but
does not pause itself when idle. At the lab's stated rate, 730 running hours
plus 10 GB SSD is about `$9.37/month`; after stopping the instance, the 10 GB
storage remains about `$1.70/month`. Stopping it during nights or between demos
reduces compute cost but adds a start/stop step and makes the API unavailable
while stopped. Requests to Cloud Run and Cloud SQL remain in `us-central1`.

Firestore would remove the idle instance charge and suit document-shaped data,
but meetings/users, ownership and relational queries would need a new schema,
access layer, migration path and tests. Keeping Aurora on AWS and calling it
from Cloud Run would retain SQL but add cross-cloud network latency, egress,
credential/network configuration, and two-cloud availability dependencies.
Neither is justified for this migration exercise.

## Other choices

- **Email:** keep SES with the weekly report stack on AWS. If an email component
  moves later, prefer its provider secret in AWS Secrets Manager or GCP Secret
  Manager according to where the sending workload runs; never bake it into the
  image or frontend.
- **Not moving:** Cognito sign-in, weekly CSV report, SES delivery, EventBridge,
  SQS, S3 report storage and the Bedrock agenda parser remain on AWS. Moving
  those would add migration work outside the required usable core.
- **Data transfer:** the existing AWS data is not automatically copied. The lab
  deployment uses Alembic migrations against a fresh Cloud SQL database; demo
  data can be seeded separately. No production user data is claimed to have
  been migrated.

## Cost comparison

Use the companion [`GCP cost table`](../../submission/gcp-costs.md). It lists the
free-tier assumptions, four profiles, and the database line that dominates the
comparison. These are planning estimates, not calculator exports.
