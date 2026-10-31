# ADR 0007: Manage the auth, reports, and agenda parser infrastructure with Terraform

- **Status:** Accepted
- **Date:** 2026-10-31

## Context

The Cognito sign-in, weekly reports, and AI agenda parser are currently defined in three CloudFormation stacks. The application code and deployment history are in Git, but changes to these infrastructure stacks are still made from a developer's machine. The project also depends on Google OAuth, GitHub, and multiple deployment environments, so infrastructure management is not confined to one AWS template or one environment. The Cognito user pool contains user accounts and the reports bucket contains durable reports; replacing either during a tool migration would cause data loss.

## Decision

Translate the resources formerly declared in `infra/auth.yml`, `infra/reports.yml`, and `infra/ai.yml` into one Terraform root module in `infra/`. Import all existing resources into the dedicated `successful-success` HCP Terraform workspace, then remove the CloudFormation stacks with resources retained and remove the old templates. HCP Terraform owns remote state and executes runs with short-lived AWS credentials. The intended steady-state workflow connects the workspace to GitHub with `infra` as its working directory, reviews plans on pull requests, and applies after merge. Keep the existing application deployment workflow separate.

Use Terraform because this project spans AWS and Google OAuth, needs separate environment states, and benefits from a single reviewed workflow for infrastructure. CloudFormation is a sound choice for AWS-only infrastructure, but does not provide this project's cross-provider configuration. CDK would add a programming-language synthesis layer without helping the required safe state handoff. OpenTofu is compatible with the HCL configuration, but the course uses HCP Terraform for hosted state, locking, and VCS-driven runs.

## Alternatives considered

- Keep CloudFormation: simplest for AWS-only resources, but leaves the infrastructure workflow separate from the project's other providers and environments.
- AWS CDK: offers imperative-language abstractions, but adds a synthesis step and does not simplify importing these existing resources.
- OpenTofu: viable compatible tooling, but does not replace the selected HCP Terraform hosted workflow in this lab.
- Recreate the stacks from Terraform: rejected because it could delete Cognito accounts and stored reports and would create duplicate resources.

## Consequences

- A change is proposed in Git, reviewed with a Terraform plan, and applied by HCP Terraform after merge once VCS is connected. Until then, a maintainer can submit a reviewed CLI-driven remote run; local state and local applies are not used.
- The HCP Terraform workspace holds the canonical, locked state. Mark sensitive inputs such as the Google client secret as sensitive workspace variables; never commit them in `.tfvars`. Terraform state can still contain secret values, so restrict workspace access and rely on HCP's state access controls and encryption. Never print or commit the state file.
- Keep a protected state version and a documented recovery procedure. If HCP Terraform is unavailable, infrastructure changes pause; the existing AWS resources continue running. Restore access to the HCP workspace/state before making changes. Do not recreate or delete resources as a workaround.
- Existing resources were imported with their actual IDs. The HCP run imported 31 resources, added none, changed three in place, and destroyed none. A subsequent plan reported no changes. Review every replacement carefully, especially the Cognito pool and reports bucket.
- The HCP Terraform AWS role should be restricted to this organization, project, workspace, and run phases, and to the permissions required by these resources. Do not use broad organization-wide trust or `AdministratorAccess` for a production workspace.
- Application deploys remain in GitHub Actions. Coordinate changes that require both infrastructure and application updates so infrastructure is applied before the application depends on it.
