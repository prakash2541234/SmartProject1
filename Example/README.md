# Azure Function App - Key Vault Creator

This Azure Function App is designed to provision Azure Key Vaults dynamically based on HTTP requests.

## Prerequisites

1. Azure Subscription
2. Azure CLI installed
3. Python 3.8 or later
4. Azure Functions Core Tools installed

## Setup Instructions

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run Locally**:
   ```bash
   func start
   ```

3. **Deploy to Azure**:
   ```bash
   func azure functionapp publish <YourFunctionAppName>
   ```

## Configuration

- Update `local.settings.json` with your Azure Storage connection string and other required settings.
- Set `CentralKeyVaultName` to the name of the centralized Key Vault that contains the DigiCert secrets.
- Ensure the function app managed identity has `get` access to the secrets in that vault.

## Files

- `kvcreate.py`: Main function logic.
- `requirements.txt`: Python dependencies.
- `host.json`: Azure Functions host configuration.
- `local.settings.json`: Local development settings.
- `.funcignore`: Files to ignore during deployment.
- `.gitignore`: Files to ignore in version control.

## Notes

Ensure the managed identity has the necessary permissions to create Key Vaults in the subscription.
