# Infrastructure (CloudFormation)

| Template | Stack name | Deployed by | Purpose |
| --- | --- | --- | --- |
| `bootstrap.yaml` | `globetrekker-bootstrap` | **You, once**, with admin credentials | GitHub OIDC provider, the CI roles (`github-actions-globetrekker-infra` and `-deploy`), and the permissions boundary for app roles |
| `app.yaml` | `globetrekker-app` | **`.github/workflows/infra.yml`** on every merge touching `infra/` | VPC, EC2 instance, data volume, Elastic IP, ECR repositories, release bucket, instance role |

Full setup steps, the security model and the reasoning are in
[`_docs/deployment.md`](../../_docs/deployment.md). The day-to-day process is in
[`_docs/release-process.md`](../../_docs/release-process.md).

## Validate locally

```bash
make lint-infra          # cfn-lint + actionlint + shellcheck
```

## Deploy the bootstrap stack (once)

```bash
aws cloudformation deploy --region us-east-1 \
  --template-file infra/cloudformation/bootstrap.yaml \
  --stack-name globetrekker-bootstrap \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides GitHubOrg=sushantmagoo GitHubRepo=globetrekker
```

## Deploy the app stack by hand (only if GitHub Actions is unavailable)

```bash
aws cloudformation deploy --region us-east-1 \
  --template-file infra/cloudformation/app.yaml \
  --stack-name globetrekker-app \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset
```

Then create the Parameter Store values the workflow would have created:
`/globetrekker/prod/POSTGRES_PASSWORD` and `/globetrekker/prod/JWT_SECRET` as SecureStrings with random values, and `/globetrekker/prod/ACME_EMAIL` as a String.

## Deleting everything

1. Delete the app stack (`aws cloudformation delete-stack --stack-name globetrekker-app`).
   - The data volume is **snapshotted** first.
   - The ECR repositories and the release bucket are **retained** on purpose. Empty and delete them by hand if you really want them gone.
2. Delete the bootstrap stack.
