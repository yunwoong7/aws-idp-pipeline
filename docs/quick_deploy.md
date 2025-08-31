# CloudShell & CodeBuild Quick Deployment Guide

The easiest way to deploy AWS IDP is to run a script in **AWS CloudShell** and automatically deploy it through **CodeBuild**.

---

## Prerequisites
- Target AWS account for deployment
  - Permissions: S3, DynamoDB, Lambda, Step Functions, OpenSearch, Bedrock, CodeBuild, IAM, (optional) CloudFront/Cognito
- **Recommended region: `us-west-2`**
  - Reason: This region supports both **BDA (Bedrock Data Automation)** and **Video Analysis Model (us.twelvelabs.pegasus)**.  
  - However, if you do not use specific features (BDA, video analysis, etc.) later, you can choose any preferred region.

---

## Deployment Steps

### 1) Launch CloudShell
- Launch **CloudShell** from the AWS Console. (Click the CloudShell icon at the top right)  
- _(Screenshot example placeholder)_

---

### 2) Clone source code and run script
```bash
~ $ git clone https://github.com/yunwoong7/aws-idp-pipeline.git
~ $ cd aws-idp-pipeline/
aws-idp-pipeline $ chmod +x ./bin.sh
aws-idp-pipeline $ ./bin.sh
```

---

### 3) Provide input during execution
You will be prompted for the following inputs during execution:

```
Enter admin user email address: admin@example.com
# The part before '@' in the entered email will be used as the initial admin username.
Do you want to use a custom domain? (y/N): N
Do you want to proceed with deployment? (y/N): y
```

- **Admin user email**: Enter your desired email (e.g., `admin@example.com`)  
  → The initial admin username will be created as `"admin"` in this example.  
- **Custom domain**: Choose `N` for test environments  
- **Proceed with deployment**: Choose `y`  
- **You must change the password after the first login.**

---

### 4) Monitor deployment
- After running the script, the **AWS CodeBuild** project will start automatically.
- You can check the progress in the console under **CodeBuild → Build projects → `aws-idp-ai-deploy-dev`**.  
- _(Screenshot example placeholder)_

---

### 5) After deployment completes
- Deployment results and initial login information will be shown in the CodeBuild output logs.
- For login:
  - Username: The admin user you entered earlier (e.g., `admin`)  
  - Password: The initial password provided during the process (You must change it after the first login)

---