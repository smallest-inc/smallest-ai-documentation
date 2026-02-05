---
title: "Agents"
description: "Manage agents, templates, and webhooks."
---

The `AgentsApi` allows you to programmatically create agents, manage their configuration, and handle webhooks.

## Clients

```python
from smallestai.atoms.api_client import ApiClient
from smallestai.atoms.api.agents_api import AgentsApi

client = ApiClient()
api = AgentsApi(client)
```

## Common Operations

### Get Agent Details

Retrieve configuration for a specific agent.

```python
agent = api.agent_id_get(agent_id="your-agent-id")
print(f"Agent Name: {agent.name}")
```

### Create Agent from Template

Spin up a new agent using a pre-defined template.

```python
from smallestai.atoms.api import AgentTemplatesApi
from smallestai.atoms.models import CreateAgentFromTemplateRequest

# Initialize Templates API
templates_api = AgentTemplatesApi()

new_agent = templates_api.agent_from_template_post(
    create_agent_from_template_request=CreateAgentFromTemplateRequest(
        templateId="template-id",
        name="My New Agent"
    )
)
print(f"Created Agent ID: {new_agent.id}")
```

### Manage Webhooks

Subscribe to events for your agent.

```python
from smallestai.atoms.models import AgentAgentIdWebhookSubscriptionsPostRequest

api.agent_agent_id_webhook_subscriptions_post(
    agent_id="your-agent-id",
    agent_agent_id_webhook_subscriptions_post_request=AgentAgentIdWebhookSubscriptionsPostRequest(
        url="https://your-server.com/webhook",
        events=["call.completed", "transcript.ready"]
    )
)
```
