# SuccessFunction

Minimal Azure Functions app in Node.js with one anonymous HTTP trigger.

## Endpoint

- `GET /api/hello`

When `LOGIC_APP_URL` is set, the function also invokes the Logic App with a JSON payload after the request is processed successfully.

## Deploy

Use an Azure Function App configured for:

- Runtime stack: `Node.js`
- Azure Functions runtime: `v4`
- Node.js version: `22`

Required app settings:

- `FUNCTIONS_WORKER_RUNTIME=node`
- `FUNCTIONS_EXTENSION_VERSION=~4`
- `AzureWebJobsStorage=<storage-connection-string>`
- `LOGIC_APP_URL=<your-logic-app-trigger-url>`

The Logic App URL should be the HTTP trigger callback URL or another HTTP endpoint that accepts `POST`.

## Local run

1. Install dependencies:
   - `npm install`
2. Start the functions host:
   - `npm start`

If you do not have Azure Functions Core Tools installed, install them first before running `npm start`.
