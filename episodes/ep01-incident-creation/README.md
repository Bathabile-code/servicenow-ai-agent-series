# EP01: AI Creates a ServiceNow Incident via API

**Date:** 2026-04-20  
**Status:** ✅ Working

## What happened

Told an AI agent (Chomi, running on OpenClaw) to create a ServiceNow incident. It used the REST API to create INC0010025 in the PDI.

## How it works

```
User: "Create a ServiceNow incident"
→ AI Agent (OpenClaw/Chomi)
→ REST API call to ServiceNow PDI
→ Incident INC0010025 created
```

## The API call

```bash
curl -X POST "https://dev228466.service-now.com/api/now/table/incident" \
  -u "username:password" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "short_description": "Test incident from AI agent",
    "state": "1",
    "priority": "3"
  }'
```

## Result

✅ **INC0010025** created and visible in ServiceNow PDI

## What's next

- EP02: AI reads and responds to incidents
- EP03: Connect to WhatsApp — notify when incidents created
- EP04: Multi-agent pattern — spawn agents for different tasks
