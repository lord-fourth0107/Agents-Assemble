# fix_generator_agent.py
# Builds and deploys the Fix Generator Agent using Google AI Platform ADK

from google.cloud import aiplatform
from google.cloud.aiplatform.agent import (
    AgentClient, Tool, HttpRequestToolConfig, Workflow, Step, Parameter
)

# Initialize AI Platform
aiplatform.init(project="YOUR_PROJECT_ID", location="us-central1")
client = AgentClient()

# Tool: fetch_structured_error - pull the latest structured error from RTDB
fetch_structured_error = Tool(
    name="fetch_structured_error",
    description="Fetch the most recent structured error from Firebase RTDB.",
    http_request=HttpRequestToolConfig(
        method="GET",
        url="${FIREBASE_DB_URL}/errors.json?orderBy=\"timestamp\"&limitToLast=1"
    )
)

# Tool: clone_repo - clone the GitHub repo for the affected service
clone_repo = Tool(
    name="clone_repo",
    description="Clone the service repository to workspace.",
    http_request=HttpRequestToolConfig(
        method="POST",
        url="https://api.github.com/repos/${ORG}/${REPO}/zipball/main"
    )
)

# Tool: generate_patch - ask LLM to propose a diff based on error context
generate_patch = Tool(
    name="generate_patch",
    description="Generate a code/config patch via LLM based on the error context.",
    http_request=HttpRequestToolConfig(
        method="POST",
        url="https://text-bison.googleapis.com/v1/projects/${PROJECT}/locations/global/models/text-bison:predict",
        headers={"Content-Type": "application/json"},
        body="""
{
  "instances": [{
    "prompt": "Error: {{structured_error.result.errorMessage}}\nContext: Service {{structured_error.result.service}}\nPropose a minimal patch or resource change to fix this issue."
  }]
}
"""
    )
)

# Tool: create_branch_and_patch - create a new branch and apply the patch via GitHub API
create_branch_and_patch = Tool(
    name="create_branch_and_patch",
    description="Create a new branch and apply the generated patch in the GitHub repo.",
    http_request=HttpRequestToolConfig(
        method="POST",
        url="https://api.github.com/repos/${ORG}/${REPO}/pulls",
        headers={
            "Authorization": "Bearer ${GITHUB_TOKEN}",
            "Content-Type": "application/json"
        },
        body="""
{
  "title": "Auto-fix for {{structured_error.result.service}}",
  "head": "auto-fix/{{structured_error.result.service}}-{{structured_error.result.errorTimestamp}}",
  "base": "main",
  "body": "{{generate_patch.response.predictions[0].content}}"
}
"""
    )
)

# Workflow steps
step_fetch = Step(
    name="fetch_structured_error",
    tool_name="fetch_structured_error"
)

step_clone = Step(
    name="clone_repo",
    tool_name="clone_repo",
    when="fetch_structured_error.result != null"
)

step_patch = Step(
    name="generate_patch",
    tool_name="generate_patch",
    when="clone_repo.status == 'OK'"
)

step_pr = Step(
    name="create_branch_and_patch",
    tool_name="create_branch_and_patch",
    when="generate_patch.response.predictions[0].content != null"
)

step_wait = Step(
    name="wait",
    run="wait 5s"
)

# Assemble workflow
demo_wf = Workflow(
    display_name="Fix Generator Workflow",
    steps=[step_fetch, step_clone, step_patch, step_pr, step_wait],
    repeat_step_name="fetch_structured_error"
)

# Create the agent
agent = client.create_agent(
    display_name="Fix Generator Agent",
    description="Generates code or config patches for detected errors and opens a PR.",
    tools=[fetch_structured_error, clone_repo, generate_patch, create_branch_and_patch],
    workflow=demo_wf
)
print(f"Created agent: {agent.name}")
