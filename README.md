# AWS Cost to Slack

AWSの日毎のコストをSlackにPOSTするGitHub Actionです。

This GitHub Action analyzes AWS costs and posts the results to Slack. It creates graphs showing daily costs by service for each AWS account in your organization.

## Features

- Retrieves cost data from AWS Cost Explorer
- Creates graphs showing daily costs by service
- Posts results to Slack with cost summary
- Filters accounts by name
- Runs on a schedule or manually

## Prerequisites

1. AWS IAM role with the following permissions:
   - `organizations:ListAccounts`
   - `ce:GetCostAndUsage`

2. Slack application with the following permissions:
   - `files:write`
   - `chat:write`

## Setup

### 1. Create a Slack App

1. Go to [Slack API](https://api.slack.com/apps) and create a new app
2. Add the `files:write` and `chat:write` permissions
3. Install the app to your workspace
4. Copy the Bot User OAuth Token (starts with `xoxb-`)

### 2. Configure AWS IAM Role

Create an IAM role with the necessary permissions and configure it for GitHub Actions OIDC:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
            },
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Condition": {
                "StringEquals": {
                    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                },
                "StringLike": {
                    "token.actions.githubusercontent.com:sub": "repo:<GITHUB_USERNAME>/<REPO_NAME>:*"
                }
            }
        }
    ]
}
```

Attach a policy with the following permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "organizations:ListAccounts",
                "ce:GetCostAndUsage"
            ],
            "Resource": "*"
        }
    ]
}
```

### 3. Configure GitHub Secrets

Add the following secrets to your GitHub repository:

- `AWS_ROLE_TO_ASSUME`: The ARN of the IAM role created above
- `SLACK_APPLICATION_TOKEN`: The Slack Bot User OAuth Token
- `SLACK_CHANNEL_ID`: The ID of the Slack channel to post to

## Usage

Add the following to your GitHub workflow file:

```yaml
name: AWS Cost Analysis

on:
  schedule:
    # Run at 9:00 AM JST on weekdays (0:00 UTC)
    - cron: '0 0 * * 1-5'
  workflow_dispatch:

jobs:
  analyze-cost:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write

    steps:
    - name: Analyze AWS costs and post to Slack
      uses: gessy0129/AWSCostToSlack@v4
      with:
        aws-region: ap-northeast-1
        # AWS認証方法1: IAMロールを使用（推奨）
        aws-role-to-assume: ${{ secrets.AWS_ROLE_TO_ASSUME }}
        
        # AWS認証方法2: アクセスキーを使用（代替手段）
        # aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
        # aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        
        # Slack設定
        slack-application-token: ${{ secrets.SLACK_APPLICATION_TOKEN }}
        slack-channel-id: ${{ secrets.SLACK_CHANNEL_ID }}
        
        # オプション: アカウントフィルター（カンマ区切りリスト）
        account-filter: 'prod,stg,dev'
```

### 認証方法

このアクションでは、2つのAWS認証方法をサポートしています：

1. **IAMロールを使用（推奨）**: GitHub ActionsのOIDC連携を使用して、一時的な認証情報を取得します。
   ```yaml
   aws-role-to-assume: ${{ secrets.AWS_ROLE_TO_ASSUME }}
   ```

2. **アクセスキーを使用**: 直接AWSアクセスキーを指定します。
   ```yaml
   aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
   aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
   ```

## Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `aws-region` | AWS region to use | Yes | `ap-northeast-1` |
| `aws-role-to-assume` | AWS IAM role to assume for accessing AWS Cost Explorer | No* | |
| `aws-access-key-id` | AWS access key ID (alternative to role-to-assume) | No* | |
| `aws-secret-access-key` | AWS secret access key (alternative to role-to-assume) | No* | |
| `slack-application-token` | Slack application token for posting results | Yes | |
| `slack-channel-id` | Slack channel ID to post results to | Yes | |
| `account-filter` | Filter accounts by name (comma-separated list) | No | `prod,stg,dev` |

*注: AWS認証には`aws-role-to-assume`または`aws-access-key-id`と`aws-secret-access-key`のいずれかが必要です。

## License

[MIT](LICENSE)
