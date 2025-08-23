<h2 align="center">Devcontainer Setup Guide</h2>

This guide provides a detailed, step-by-step walkthrough for setting up your development environment. This is the **highly recommended** method as it ensures a consistent, isolated, and fully configured environment. Following the steps up to **Step 6** will result in a complete local development setup. The optional **Step 7** describes how to deploy the entire application to AWS ECS for an externally accessible runtime environment.

---

## Prerequisites

Before you begin, please ensure you have the following software and configurations set up on your **local machine**.

1.  **An IDE that supports Devcontainers:**
    *   [**Visual Studio Code**](https://code.visualstudio.com/download) or [**Cursor**](https://cursor.sh/)

2.  **Docker Desktop:**
    *   The engine that powers the container. It must be **installed and running**.
    *   Download from the [official Docker website](https://www.docker.com/products/docker-desktop/).

3.  **AWS Credentials:**
    
    * You must have the [AWS CLI installed](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) and configured on your local machine. You can create a profile by running 
    
      ```bash
      aws configure --profile your-profile-name
      ```
    
    *   Ensure you have a named profile set up in your `~/.aws/credentials` and `~/.aws/config` files. The Devcontainer will automatically mount this directory, making your profiles available inside the container.

---

## Setup Process

### Step 1: Install and Run Docker Desktop

Download and install Docker Desktop for your operating system. After installation, **make sure you start the application** so it runs in the background.

<div align="center">   
  <img src="assets/devcontainer-running.png" alt="Devcontainer Docker Running" width="900"/> 
</div>

### Step 2: Open the Project in VS Code

1.  Clone this repository to your local machine.
2.  In VS Code, go to `File > Open Folder...` and select the cloned project's root directory.

### Step 3: Launch the Devcontainer

1.  Open the **Command Palette** (`Ctrl+Shift+P` or `Cmd+Shift+P` on macOS).
2.  In the palette, type `Reopen` and select **"Dev Containers: Reopen in Container"**.

<div align="center">   
  <img src="assets/devcontainer-remote-window-button.png" alt="Devcontainer remote window" width="900"/> 
</div>

> **What Happens Next? (Fully Automated)**
> Once you click "Reopen in Container", the process is fully automated. VS Code and Docker work together to build your environment as defined in `devcontainer.json`:
> *   A **Python 3.12 container image** is downloaded.
> *   Essential tools like the **AWS CLI, Node.js, and Docker** are installed.
> *   Your local **AWS credentials** are securely mounted.
> *   A setup script runs to **install all Python and Node.js dependencies** using `uv` and `pnpm`.
> *   Helpful **VS Code extensions** like Prettier and ESLint are installed for you.

### Step 4: Deploy AWS Infrastructure

After the Devcontainer has finished building, deploy the core AWS infrastructure.

1.  Open a new terminal in VS Code via the Command Palette (`Ctrl+Shift+P`) by typing `Terminal: Create New Terminal`.
2.  Run the following commands:

```bash
# Navigate to the infrastructure package
cd packages/infra

# Run the deployment script with your AWS profile name
./deploy-infra.sh your-aws-profile-name
```

> **Deployment Time & Verification**
> *   The infrastructure deployment can take **40 to 60 minutes** to complete. The majority of this time is spent provisioning the Amazon OpenSearch cluster.
> *   **After deployment is successful**, go to the **AWS OpenSearch Console** and verify that the `nori` (Korean morphological analyzer) plugin is correctly installed on your domain. Installing the plugin package may take an additional **10–20 minutes**.

### Step 5: Run the Application Locally

To run the application on your local machine for development, you will need two separate terminals. You can easily create a second terminal or split the current one in VS Code.

**Terminal 1: Start the Backend**

1.  In a new terminal, ensure you are at the project root (`/workspaces/aws-idp-pipeline`).
2.  Activate the Python virtual environment:
    ```bash
    source .venv/bin/activate
    ```
3.  Start the backend server:
    ```bash
    python packages/backend/main.py
    ```

**Terminal 2: Start the Frontend**

1.  Open another new terminal.
2.  Start the frontend development server:
    ```bash
    pnpm dev
    ```

### Step 6: Access the Local Application

Once both the backend and frontend are running, open your web browser and navigate to:

**[http://localhost:3000](http://localhost:3000)**

---

### Step 7 (Optional): Deploy to AWS ECS

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

*   Once the script is finished, it will print the public URL for the frontend.

    ```
    Service URLs:
      Frontend:    http://your-alb-dns-name.amazonaws.com
    ```
*   You can also find this URL in the auto-generated `.env` file at the project root, under the `FRONTEND_URL` key.
*   Access the printed URL in your browser. If your IP address changes, you will need to add the new IP to the `.toml` file and re-run the `./deploy-services.sh` script.

---

**Deployment Complete!** You can now test the AWS IDP environment either locally or in the ECS environment.
