# build_test_agent.py
# Builds and deploys the Build & Test Orchestrator Agent using Google AI Platform ADK

from google.cloud import aiplatform
from google.cloud.aiplatform.agent import (
    AgentClient, Tool, HttpRequestToolConfig, Workflow, Step
)

# Initialize AI Platform
aiplatform.init(project="YOUR_PROJECT_ID", location="us-central1")
client = AgentClient()

# Tool: trigger_build - invoke Cloud Build for a given branch or PR
trigger_build = Tool(
    name="trigger_build",
    description="Trigger a Cloud Build job for the specified branch or PR.",
    http_request=HttpRequestToolConfig(
        method="POST",
        url="https://cloudbuild.googleapis.com/v1/projects/${PROJECT_ID}/builds",
        headers={"Content-Type": "application/json"},
        body="""
{
  "source": {
    "repoSource": {
      "projectId": "${PROJECT_ID}",
      "repoName": "${REPO}",
      "branchName": "${BRANCH_NAME}"
    }
  },
  "steps": [
    { "name": "gcr.io/cloud-builders/docker", "args": ["build", "-t", "gcr.io/${PROJECT_ID}/${SERVICE}:${BRANCH_NAME}", "."] },
    { "name": "gcr.io/cloud-builders/docker", "args": ["push", "gcr.io/${PROJECT_ID}/${SERVICE}:${BRANCH_NAME}"] },
    { "name": "gcr.io/cloud-builders/gcloud", "args": ["beta", "run", "deploy", "${SERVICE}", "--image", "gcr.io/${PROJECT_ID}/${SERVICE}:${BRANCH_NAME}"] }
  ],
  "timeout": "1200s"
}
"""
    )
)

# Tool: check_build_status - get Cloud Build job status
check_build = Tool(
    name="check_build_status",
    description="Poll the Cloud Build API for job status.",
    http_request=HttpRequestToolConfig(
        method="GET",
        url="https://cloudbuild.googleapis.com/v1/projects/${PROJECT_ID}/builds/${BUILD_ID}"
    )
)

# Step definitions
step_trigger = Step(
    name="trigger_build",
    tool_name="trigger_build",
    arguments={"BRANCH_NAME": "${BRANCH_NAME}", "SERVICE": "${SERVICE}"}
)

step_wait_build = Step(
    name="wait_for_build",
    tool_name="check_build_status",
    when="trigger_build.response.name != null",
    arguments={"BUILD_ID": "{{trigger_build.response.metadata.build.id}}"}
)

step_evaluate = Step(
    name="evaluate_build",
    run="""
import json
status = json.loads(wait_for_build.responseBody).get('status')
if status in ('SUCCESS', 'WORKING'): return {'status': status}
return {'status': 'FAILURE'}
"""
)

step_wait = Step(
    name="wait",
    run="wait 30s"
)

# Workflow
demo_wf = Workflow(
    display_name="Build & Test Workflow",
    steps=[step_trigger, step_wait_build, step_evaluate, step_wait],
    repeat_step_name="trigger_build"
)

# Create Agent
agent = client.create_agent(
    display_name="Build & Test Agent",
    description="Triggers Cloud Build for new branches/PRs and monitors the build status.",
    tools=[trigger_build, check_build],
    workflow=demo_wf
)
print(f"Created agent: {agent.name}")
