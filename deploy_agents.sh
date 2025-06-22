\#!/usr/bin/env bash

# deploy\_agents.sh

# Automate exporting environment variables and deploying ADK agents

set -euo pipefail

# Load variables from .env file

if \[ -f .env ]; then
echo "Loading environment variables from .env"

# shellcheck disable=SC1091

source .env
else
echo "Error: .env file not found!"
exit 1
fi

# Ensure required variables are set

REQUIRED\_VARS=(PROJECT\_ID FIREBASE\_DB\_URL GITHUB\_TOKEN SENDGRID\_API\_KEY ACCESS\_TOKEN DATASET ORG REPO SERVICE\_NAME ZONE CLUSTER NAMESPACE)
for var in "\${REQUIRED\_VARS\[@]}"; do
if \[ -z "\${!var:-}" ]; then
echo "Error: Environment variable \$var is not set."
exit 1
fi
done

# Authenticate gcloud for ADK

echo "Authenticating with gcloud..."
gcloud auth application-default login

gcloud config set project "\$PROJECT\_ID"
gcloud config set ai/region us-central1

# Deploy each agent

echo "Deploying Error Analyzer Agent..."
python error\_analyzer\_agent.py

echo "Deploying Fix Generator Agent..."
python fix\_generator\_agent.py

echo "Deploying Risk Mitigation Agent..."
python risk\_mitigation\_agent.py

echo "Deploying Build & Test Agent..."
python build\_test\_agent.py

echo "Deploying Deploy Agent..."
python deploy\_agent.py

echo "Deploying Reporter Agent..."
python reporter\_agent.py

# Completion message

echo "All agents deployed successfully!"
