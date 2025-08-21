<h2 align="center">Manual Local Setup Guide</h2>

This guide is for users who prefer to set up the development environment manually on their local machine. This method requires careful installation of all tools and dependencies. Following the steps up to **Step 5** will result in a complete local development setup. The optional **Step 6** describes how to deploy the entire application to AWS ECS for a public-facing environment.

---

## Prerequisites

Before you begin, please ensure you have the following software and configurations set up on your **local machine**.

1.  **Required Tools**
    * [**Python**](https://www.python.org/) (3.12+)
    
    * [**Node.js**](https://nodejs.org/ko/download) (20+)
    
    * [**pnpm**](https://pnpm.io/installation)
    
    * **uv**: After installing Python, run 

      ```bash
      pip install uv
      ```
    
    * [**AWS CLI**](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
    
    * [**AWS CDK**](https://docs.aws.amazon.com/cdk/v2/guide/getting-started.html)
    
    *   **jq**
    
2.  **AWS Credentials**
    * You must have the [AWS CLI installed](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) and configured on your local machine. You can create a profile by running 
    
      ```bash
      aws configure --profile your-profile-name
      ```
    * Ensure you have a named profile set up in your `~/.aws/credentials` and `~/.aws/config` files. The Devcontainer will automatically mount this directory, making your profiles available inside the container.

---

## Setup Process

### Step 1: Installation & Verification

The installation commands for the prerequisite tools vary by operating system. After installation, run the following commands to ensure everything is working:

```bash
aws --version
node --version
pnpm --version
python3 --version
uv --version
cdk --version
jq --version
```

### Step 2: Install Project Dependencies

**From the project root directory**, run the following commands to install dependencies.

```bash
# Create a Python virtual environment
uv venv

# Activate the virtual environment (the command depends on your shell)
# On macOS/Linux: `source .venv/bin/activate`
# On Windows: `.venv\Scripts\activate.bat`
source .venv/bin/activate

# Install Python dependencies
uv sync

# Install Node.js dependencies
pnpm install
```

### Step 3: Deploy AWS Infrastructure

This step provisions the core cloud resources. It must be run from within the activated Python virtual environment.

1.  Navigate to the infrastructure package:
    ```bash
    cd packages/infra
    ```
2.  Run the deployment script with your AWS profile:
    ```bash
    ./deploy-infra.sh your-aws-profile-name
    ```

> **Deployment Time & Verification**
> *   The deployment can take **40 to 60 minutes**.
> *   After completion, go to the **AWS OpenSearch Console** to verify that the `nori` plugin is installed.

### Step 4: Run the Application Locally

This requires two separate terminals. Remember to activate the virtual environment in any new terminal you use for the backend.

**Terminal 1: Start the Backend**

```bash
# (If needed) Activate the virtual environment. On Windows, use `.venv\Scripts\activate.bat`

# Start the backend server
python packages/backend/main.py
```

**Terminal 2: Start the Frontend**

```bash
# Start the frontend development server
pnpm dev
```

### Step 5: Access the Local Application

With both servers running, open your browser to **[http://localhost:3000](http://localhost:3000)**.

---

### Step 6 (Optional): Deploy to AWS ECS

This step is for deploying the application to a public-facing environment on AWS using ECS and an Application Load Balancer (ALB). This is useful for sharing access with others or for staging.

**1. Configure IP Whitelist**

For security, access to the deployed application is restricted by an IP whitelist. You must add your own IP address to this list before deploying.

* **How to find your IP?** Run the following command in your **local machine's terminal** (not the dev container):

  ```bash
  curl ifconfig.me
  ```

* **Edit the configuration file:** Open `packages/infra/.toml`.

* **Add your IP address:** Find the `[security]` section and add your IP address to the `whitelist`. It must be in CIDR format. For a single IP, add `/32` at the end.

```toml
[security]
# IP Whitelist for ALB access control
# Add your authorized IP addresses or CIDR blocks here
whitelist = [
  "15.248.0.0/16",
  "219.250.0.0/16",
  "YOUR_IP_ADDRESS/32"  # <-- Add your IP here
]
```

**2. Deploy the Services**

Run the service deployment script from the terminal:

```bash
# Navigate to the infrastructure package if you are not already there
cd packages/infra

# Run the service deployment script with your AWS profile
./deploy-services.sh your-aws-profile-name
```

**3. Access Your Deployed Application**

* Once the script is finished, it will print the public URL for the frontend.

  ```
  Service URLs:
    Frontend:    http://your-alb-dns-name.amazonaws.com
  ```

* You can also find this URL in the auto-generated `.env` file at the project root, under the `FRONTEND_URL` key.

* Access the printed URL in your browser. If your IP address changes, you will need to add the new IP to the `.toml` file and re-run the `./deploy-services.sh` script.

---

**Deployment Complete!** Whether you are running locally or have deployed to ECS, your AWS IDP environment is now fully operational.
