# Lab 7 — AWS and Google Cloud cost estimate

**Region:** AWS `us-east-1`; GCP `us-central1`. **Currency:** USD. **Month:**
730 hours. On-demand list prices, before tax.

## Assumptions

- Traffic stays within the listed Cloud Run, Firebase Hosting, Lambda and
  CloudFront free allowances. Artifact Registry, Secret Manager, logs, and
  network egress are assumed to remain within small student usage.
- GCP uses Cloud SQL `db-f1-micro` at `$0.0105/hour` and 10 GB SSD at
  `$0.17/GB-month` (`$1.70/month`). The table assumes the instance is stopped
  outside the active lab hours shown. If left running all month, replace its
  compute line with `$7.67` and every GCP total becomes `$9.37`.
- AWS Aurora estimate assumes it pauses when idle, resumes at 0.5 ACU, and uses
  `$0.12/ACU-hour` (`$0.06/hour` at 0.5 ACU), plus the supplied approximate
  `$0.10/month` for 1 GB of storage. The AWS baseline also includes `$0.20` of
  estimated registry/secrets/logging cost to match the lab's idle reference of
  about `$0.30/month`. Actual usage depends on warm-up and scaling.
- The class and office-hours profiles are modeled as 20 and 176 database
  running hours. Real session spacing changes Aurora's pause/resume time.
- API requests are within the AWS Lambda and Cloud Run free quotas. Static site
  usage remains within the AWS CloudFront Free plan and Firebase Hosting free
  plan. No AI, data processing, email, backups, or paid egress is included.

## Monthly comparison

| Profile | DB hours | AWS: frontend + API + DB | GCP: frontend + API + DB | Cheaper / deciding line |
|---|---:|---:|---:|---|
| Nobody | 0 | ≈ `$0.30` | ≈ `$1.70` (stopped) | AWS; GCP retains Cloud SQL disk charge |
| Class demos (10 × 2 h) | 20 | ≈ `$1.50` | ≈ `$1.91` (20 h, then stopped) | AWS; GCP compute plus persistent disk |
| Office hours (8 h × 22 days) | 176 | ≈ `$10.86` | ≈ `$3.55` (176 h, then stopped) | GCP; Aurora compute becomes the largest line |
| Busy around the clock | 730 | ≈ `$44.10` | ≈ `$9.37` | GCP; Aurora's hourly capacity dominates |

Totals round to cents where useful: AWS = `$0.30 + 0.06 × DB hours`; GCP =
`$1.70 + 0.0105 × DB hours`. If Cloud SQL is **not stopped**, it is `$9.37` in
all four profiles. In that always-on case, AWS wins for nobody and class demos;
GCP wins for office hours and busy traffic.

## The traps

- **GCP:** Cloud SQL `db-f1-micro` is an instance, not a serverless database.
  It bills compute continuously while `ALWAYS`, even when Cloud Run has scaled
  to zero; stopping it still leaves the SSD storage charge. The Terraform
  instance is configured `ALWAYS`, so stop it for idle periods or run
  `terraform destroy` when finished.
- **AWS:** Aurora Serverless v2 can resume and remain awake after a request.
  Frequent traffic can keep it above zero; in this estimate, every active hour
  adds roughly `$0.06` at 0.5 ACU before I/O. Verify its actual ACU-hours in the
  AWS calculator / Cost Explorer.

## Calculator entries to reproduce

| Service | AWS model | GCP model |
|---|---|---|
| Static frontend/CDN | CloudFront Free plan `$0`, S3 small static site within free tier | Firebase Hosting free quota `$0` |
| API | Lambda requests and GB-seconds within free tier `$0` | Cloud Run request-based billing within free quota `$0` |
| Database compute | Aurora Serverless v2, 0–1 ACU, estimate 0.5 ACU when awake × profile DB hours | Cloud SQL PostgreSQL `db-f1-micro` × profile DB hours, `$0.0105/hour` |
| Database storage | Aurora approximately 1 GB, `$0.10/month` per the lab reference | 10 GB SSD × `$0.17/GB-month` = `$1.70/month` |
| Registry / secrets / logs | Small usage in free allowances | Small usage in free allowances |

Recheck prices and adjust these estimates in the [AWS Pricing Calculator](https://calculator.aws/#/) and
[Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator) before submission. The numbers above are lab estimates based on the given profile assumptions, not saved calculator quotes. The GCP SQL instance price and the AWS Aurora ACU price are on the providers' [Cloud SQL pricing](https://cloud.google.com/sql/pricing) and [Aurora pricing](https://aws.amazon.com/rds/aurora/pricing/) pages.
