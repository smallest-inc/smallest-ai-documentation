---
title: "Campaigns"
description: "Manage outbound calling campaigns."
---

The `Campaign` module allows you to create and manage bulk outbound calling campaigns easily.

## Clients

```python
from smallestai.atoms.campaign import Campaign
from smallestai.atoms.audience import Audience

campaign = Campaign()
audience = Audience()
```

## Operations

### Create a Campaign

Launch a new outbound campaign.

```python
# 1. Create an audience first
aud_response = audience.create(
    name="Q3 Outreach List",
    phone_numbers=["+14155551234"],
    names=[("John", "Doe")]
)
audience_id = aud_response["data"]["_id"]

# 2. Create the campaign
camp_response = campaign.create(
    name="Q3 Outreach",
    agent_id="your-agent-id",
    audience_id=audience_id,
    phone_ids=["your-phone-id"],  # Get from client.get_phone_numbers()
    description="Sales outreach",
    max_retries=2,
    retry_delay=15
)
campaign_id = camp_response["data"]["_id"]
print(f"Campaign Created: {campaign_id}")

# 3. Start the campaign
campaign.start(campaign_id)
print("Campaign Started")
```
