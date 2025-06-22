# risk_mitigation_agent.py
# Builds and deploys the Risk Mitigation Agent using Google AI Platform ADK

from google.cloud import aiplatform
from google.cloud.aiplatform.agent import (
    AgentClient, Tool, HttpRequestToolConfig, Workflow, Step, Parameter
)

# Initialize AI Platform
aiplatform.init(project="YOUR_PROJECT_ID", location="us-central1")
client = AgentClient()

# Tool: fetch_metrics - query recent pod metrics from Cloud Monitoring API
fetch_metrics = Tool(
    name="fetch_metrics",
    description="Fetch the last hour of memory usage for a given service from Cloud Monitoring.",
    http_request=HttpRequestToolConfig(
        method="POST",
        url="https://monitoring.googleapis.com/v3/projects/${PROJECT_ID}/timeSeries:query",
        headers={"Content-Type": "application/json"},
        body="""
{
  "query": "fetch k8s_container.memory.usage_bytes | filter (resource.labels.pod_name = \"{service}\") | every 60s for 1h"
}
"""
    )
)

# Tool: generate_risk_patch - use LLM to propose mitigation (e.g., bump memory limits)
generate_risk_patch = Tool(
    name="generate_risk_patch",
    description="Generate a Kubernetes resource patch or code stub to mitigate memory trend issues.",
    http_request=HttpRequestToolConfig(
        method="POST",
        url="https://text-bison.googleapis.com/v1/projects/${PROJECT_ID}/locations/global/models/text-bison:predict",
        headers={"Content-Type": "application/json"},
        body="""
{
  "instances": [{
    "prompt": "Memory usage for service {service} has grown from {start} to {end} bytes over the last hour. Propose a minimal Kubernetes resource limit update or config change to mitigate this risk."
  }]
}
"""
    )
)

# Tool: create_pr - open a PR with the proposed mitigation patch
tools_create_pr = Tool(
    name="create_pr",
    description="Create a GitHub PR for the risk mitigation patch.",
    http_request=HttpRequestToolConfig(
        method="POST",
        url="https://api.github.com/repos/${ORG}/${REPO}/pulls",
        headers={
            "Authorization": "Bearer ${GITHUB_TOKEN}",
            "Content-Type": "application/json"
        },
        body="""
{
  "title": "Risk Mitigation: {service} memory limit bump",
  "head": "risk-mitigation/{service}/{timestamp}",
  "base": "main",
  "body": "{{generate_risk_patch.response.predictions[0].content}}"
}
"""
    )
)

# Step definitions
step_fetch = Step(
    name="fetch_metrics",
    tool_name="fetch_metrics",
    arguments={"service": "${SERVICE_NAME}"}
)

step_analyze = Step(
    name="analyze_metrics",
    run="""
import json, time
metrics = json.loads(fetch_metrics.responseBody).get('timeSeries', [])
# Extract first and last values
if not metrics or not metrics[0]['points']:
    return None
series = metrics[0]['points']
start = series[-1]['value']['doubleValue']
end = series[0]['value']['doubleValue']
if end / start < 1.2:
    return None
ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
return {'service': '${SERVICE_NAME}', 'start': start, 'end': end, 'timestamp': ts}
"""
)

step_patch = Step(
    name="generate_risk_patch",
    tool_name="generate_risk_patch",
    when="analyze_metrics.result != null",
    arguments={"service": "{{analyze_metrics.result.service}}", "start": "{{analyze_metrics.result.start}}", "end": "{{analyze_metrics.result.end}}"}
)

step_pr = Step(
    name="create_pr",
    tool_name="create_pr",
    when="generate_risk_patch.response.predictions[0].content != null",
    arguments={"service": "{{analyze_metrics.result.service}}", "timestamp": "{{analyze_metrics.result.timestamp}}"}
)

step_notify = Step(
    name="notify",
    run="""
# Log to RTDB and optionally invoke notification
import json
# write to Firebase under risk-mitigations/{service}/{timestamp}
# (could be another tool)
"""
)

step_wait = Step(
    name="wait",
    run="wait 600s"
)

# Workflow
demo_wf = Workflow(
    display_name="Risk Mitigation Workflow",
    steps=[step_fetch, step_analyze, step_patch, step_pr, step_notify, step_wait],
    repeat_step_name="fetch_metrics"
)

# Create Agent
agent = client.create_agent(
    display_name="Risk Mitigation Agent",
    description="Monitors pod metrics for trends and creates PRs to mitigate risks.",
    tools=[fetch_metrics, generate_risk_patch, create_pr],
    workflow=demo_wf
)
print(f"Created agent: {agent.name}")
