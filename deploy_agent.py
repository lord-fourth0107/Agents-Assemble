# deploy_agent.py
# Builds and deploys the Deploy Agent using Google AI Platform ADK

from google.cloud import aiplatform
from google.cloud.aiplatform.agent import (
    AgentClient, Tool, HttpRequestToolConfig, Workflow, Step
)

# Initialize AI Platform
aiplatform.init(project="YOUR_PROJECT_ID", location="us-central1")
client = AgentClient()

# Tool: fetch_build - pull the latest build result from Firebase RTDB
fetch_build = Tool(
    name="fetch_build",
    description="Fetch the most recent build result from Firebase RTDB.",
    http_request=HttpRequestToolConfig(
        method="GET",
        url="${FIREBASE_DB_URL}/builds.json?orderBy=\"timestamp\"&limitToLast=1"
    )
)

# Tool: deploy_patch - patch the Kubernetes deployment via GKE API
deploy_patch = Tool(
    name="deploy_patch",
    description="Apply the new image or patch to the Kubernetes deployment.",
    http_request=HttpRequestToolConfig(
        method="PATCH",
        url="https://container.googleapis.com/v1/projects/${PROJECT_ID}/zones/${ZONE}/clusters/${CLUSTER}/namespaces/${NAMESPACE}/deployments/${SERVICE}",
        headers={"Content-Type": "application/json"},
        body="""
{
  "spec": {
    "template": {
      "spec": {
        "containers": [{
          "name": "${SERVICE}",
          "image": "gcr.io/${PROJECT_ID}/${SERVICE}:${BUILD_ID}"
        }]
      }
    }
  }
}
"""
    )
)

# Step definitions
step_fetch = Step(
    name="fetch_build",
    tool_name="fetch_build"
)

step_deploy = Step(
    name="deploy_patch",
    tool_name="deploy_patch",
    when="fetch_build.responseBody.values()[0].status == 'SUCCESS'",
    arguments={
        "BUILD_ID": "{{fetch_build.responseBody.values()[0].id}}",
        "SERVICE": "${SERVICE_NAME}"  
    }
)

step_wait = Step(
    name="wait",
    run="wait 30s"
)

# Workflow
demo_wf = Workflow(
    display_name="Deploy Workflow",
    steps=[step_fetch, step_deploy, step_wait],
    repeat_step_name="fetch_build"
)

# Create Agent
agent = client.create_agent(
    display_name="Deploy Agent",
    description="Fetches successful build results and applies deployment patches to GKE.",
    tools=[fetch_build, deploy_patch],
    workflow=demo_wf
)
print(f"Created agent: {agent.name}")
