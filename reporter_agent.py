# reporter_agent.py
# Builds and deploys the Reporter Agent using Google AI Platform ADK

from google.cloud import aiplatform
from google.cloud.aiplatform.agent import (
    AgentClient, Tool, HttpRequestToolConfig, Workflow, Step
)

# Initialize AI Platform
aiplatform.init(project="YOUR_PROJECT_ID", location="us-central1")
client = AgentClient()

# Tool: fetch_events - fetch latest events from remediation-related RTDB paths
tools_fetch = []
for path in ["errors", "pr-requests", "builds", "deploys", "risk-mitigations"]:
    tools_fetch.append(
        Tool(
            name=f"fetch_{path}",
            description=f"Fetch latest {path} entry",
            http_request=HttpRequestToolConfig(
                method="GET",
                url=f"${{FIREBASE_DB_URL}}/{path}.json?orderBy=\"timestamp\"&limitToLast=1"
            )
        )
    )

# Tool: send_email
send_email = Tool(
    name="send_email",
    description="Send remediation report via SendGrid API",
    http_request=HttpRequestToolConfig(
        method="POST",
        url="https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": "Bearer ${SENDGRID_API_KEY}", "Content-Type": "application/json"},
        body="${email_payload}"
    )
)

# Tool: log_bq
log_bq = Tool(
    name="log_bq",
    description="Append event to BigQuery remediation_log table",
    http_request=HttpRequestToolConfig(
        method="POST",
        url="https://bigquery.googleapis.com/bigquery/v2/projects/${PROJECT}/datasets/${DATASET}/tables/remediation_log/insertAll",
        headers={"Authorization":"Bearer ${ACCESS_TOKEN}", "Content-Type":"application/json"},
        body="${bq_payload}"
    )
)

# Steps: fetch all, build payloads, send email, log to BigQuery, wait, loop
steps = []
# fetch steps
for path in ["errors", "pr_requests", "builds", "deploys", "risk_mitigations"]:
    steps.append(
        Step(
            name=f"fetch_{path}",
            tool_name=f"fetch_{path}"
        )
    )

# build payloads
data_sources = {"errors": "fetch_errors", "pr_requests": "fetch_pr-requests", "builds": "fetch_builds", "deploys": "fetch_deploys", "risk_mitigations": "fetch_risk-mitigations"}
build_payload = Step(
    name="build_payloads",
    run="""
import json
data = {}
# collect each event
for key, step_name in %s.items():
    resp = json.loads(globals()[step_name].responseBody or '{}')
    item = list(resp.values())[0] if resp else None
    if item:
        data[key] = item
# choose the newest by timestamp across types
all_items = [v for v in data.values()]
if not all_items:
    return None
newest = max(all_items, key=lambda x: x['timestamp'])
# construct email payload and bq payload
email = {
  "personalizations": [{"to":[{"email":"oncall@company.com"}]}],
  "from": {"email":"noreply@company.com"},
  "subject": f"Remediation Update: {newest.get('service','')} - {newest.get('timestamp','')}",
  "content": [{"type":"text/plain","value":json.dumps(newest, indent=2)}]
}
bq = {"rows":[{"json":newest}]}
return {"email_payload": json.dumps(email), "bq_payload": json.dumps(bq)}
""" % data_sources
)

# send email
steps.append(build_payload)
steps.append(
    Step(
        name="send_email",
        tool_name="send_email",
        when="build_payloads.result != null",
        arguments={"email_payload": "{{build_payloads.result.email_payload}}"}
    )
)
# log to BigQuery
steps.append(
    Step(
        name="log_bq",
        tool_name="log_bq",
        when="build_payloads.result != null",
        arguments={"bq_payload": "{{build_payloads.result.bq_payload}}"}
    )
)
# wait and loop
steps.append(Step(name="wait", run="wait 60s"))

demo_wf = Workflow(
    display_name="Reporter Workflow",
    steps=steps,
    repeat_step_name="fetch_errors"
)

agent = client.create_agent(
    display_name="Reporter Agent",
    description="Aggregates remediation events, emails updates, and logs to BigQuery.",
    tools=tools_fetch + [send_email, log_bq],
    workflow=demo_wf
)
print(f"Created agent: {agent.name}")
