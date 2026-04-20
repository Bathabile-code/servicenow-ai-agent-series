# ServiceNow PDI Setup

## Credentials Used

- Instance: `https://dev228466.service-now.com/`
- API uses Basic Auth (username:password)

## Getting Access

1. Go to https://developer.servicenow.com/
2. Request a Personal Developer Instance (PDI)
3. Use the credentials to connect via REST API

## Testing the Connection

```bash
curl -u "username:password" \
  "https://dev228466.service-now.com/api/now/table/incident?sysparm_limit=1"
```
