const { app } = require('@azure/functions');

async function callLogicApp(context) {
  const logicAppUrl = process.env.LOGIC_APP_URL;

  if (!logicAppUrl) {
    context.log('LOGIC_APP_URL is not set, skipping Logic App call.');
    return null;
  }

  const response = await fetch(logicAppUrl, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      source: 'azure-function',
      message: 'hello function completed successfully',
      timestamp: new Date().toISOString(),
    }),
  });

  const responseText = await response.text();

  if (!response.ok) {
    throw new Error(
      `Logic App call failed with status ${response.status}: ${responseText}`
    );
  }

  return {
    status: response.status,
    body: responseText,
  };
}

app.http('hello', {
  methods: ['GET'],
  authLevel: 'anonymous',
  handler: async (request, context) => {
    context.log(`HTTP function processed request for url "${request.url}".`);

    const logicAppResult = await callLogicApp(context);

    return {
      status: 200,
      headers: {
        'content-type': 'application/json; charset=utf-8',
      },
      body: JSON.stringify({
        message: 'SuccessFunction is running.',
        logicAppCalled: Boolean(logicAppResult),
        logicAppStatus: logicAppResult?.status ?? null,
      }),
    };
  },
});
