# error_analyzer_agent.py
# Builds and deploys the Error Analyzer Agent using Google AI Platform ADK

from google.cloud import aiplatform
from google.cloud.aiplatform.agent import AgentClient, Tool, HttpRequestToolConfig, Workflow, Step, Parameter

# Initialize AI Platform
aiplatform.init(project="YOUR_PROJECT_ID", location="us-central1")
client = AgentClient()

# Tool 1: fetch_error - pull latest pod error from Pub/Sub subscription endpoint (via HTTP pull)
fetch_error = Tool(
    name="fetch_error",
    description="Fetch the most recent pod failure event from Pub/Sub subscription.",
    http_request=HttpRequestToolConfig(
        method="POST",
        url="https://pubsub.googleapis.com/v1/projects/YOUR_PROJECT_ID/subscriptions/pod-errors-sub:pull",
        headers={
            "Content-Type": "application/json"
        },
        body="""
{
  "maxMessages": 1
}
"""
    )
)

# Tool 2: write_error - write structured error into Firebase RTDB
write_error = Tool(
    name="write_error",
    description="Write structured error record to Firebase RTDB under /errors/{service}/{timestamp}",
    http_request=HttpRequestToolConfig(
        method="PUT",
        url="${FIREBASE_DB_URL}/errors/{service}/{errorTimestamp}.json",
        body="${error_payload}"
    )
)

# Parameter: none for this simple agent

# Step 1: pull error
step_fetch = Step(
    name="fetch_error",
    tool_name="fetch_error"
)

# Step 2: analyze and structure
step_analyze = Step(
    name="analyze_error",
    run="""
import json, time
# Pub/Sub pull returns {receivedMessages: [...]}
msgs = json.loads(fetch_error.responseBody).get('receivedMessages', [])
if not msgs:
    return None
# Extract data
msg = msgs[0]['message']
data = json.loads(msg['data'])
service = data.get('metadata', {}).get('labels', {}).get('app') or data.get('podName', 'unknown')
error_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
# Build structured payload
payload = {
    'service': service,
    'errorMessage': data.get('error', data.get('log', '')), 
    'raw': data,
    'timestamp': error_ts
}
return {
    'service': service,
    'errorTimestamp': error_ts,
    'error_payload': json.dumps(payload)
}
"""
)

# Step 3: write to RTDB
step_write = Step(
    name="write_error",
    tool_name="write_error",
    when="analyze_error.result != null",
    arguments={
        'service': "{{analyze_error.result.service}}",
        'errorTimestamp': "{{analyze_error.result.errorTimestamp}}",
        'error_payload': "{{analyze_error.result.error_payload}}"
    }
)

# Step 4: wait and loop
step_wait = Step(
    name="wait",
    run="wait 60s"
)

# Assemble workflow
demo_wf = Workflow(
    display_name="Error Analyzer Workflow",
    steps=[step_fetch, step_analyze, step_write, step_wait],
    repeat_step_name="fetch_error"
)

# Create the agent
agent = client.create_agent(
    display_name="Error Analyzer Agent",
    description="Parses pod failure events and logs structured records to Firebase.",
    tools=[fetch_error, write_error],
    workflow=demo_wf
)
print(f"Created agent: {agent.name}")
