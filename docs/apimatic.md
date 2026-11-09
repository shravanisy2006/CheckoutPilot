# CheckoutPilot API docs and SDKs with APIMatic

CheckoutPilot's backend publishes its API description automatically (OpenAPI 3.1).
We use [APIMatic](https://www.apimatic.io/) to turn it into a developer portal and
client SDKs, so a merchant or platform can call CheckoutPilot from their own code.

- API description: [`docs/openapi.json`](openapi.json) (validated, 6 endpoints)
- Field-by-field reference: [`docs/api_contract.md`](api_contract.md)

## 1. Export the API description

From the project root (venv active):

```bash
python -m scripts.export_openapi        # writes docs/openapi.json
```

Run it again whenever an endpoint changes. (With the backend running, the same file is
also served at http://localhost:8000/openapi.json.)

## 2. Install the APIMatic CLI and log in

Needs Node.js 20 or newer (`node --version`).

```bash
npm install -g @apimatic/cli
apimatic --version
apimatic auth login          # free APIMatic account
apimatic auth status
```

## 3. Generate the developer portal

```bash
mkdir apimatic-portal
cd apimatic-portal
apimatic quickstart          # choose "API Documentation Portal", then import ../docs/openapi.json
apimatic portal serve        # preview at http://localhost:3000
```

Keep `apimatic-portal/` out of the main code (it is generated); publish it with APIMatic's
hosting option and put the link below.

## 4. Generate client SDKs

Run `apimatic quickstart` again in an empty folder and choose **SDK**, import
`docs/openapi.json`, and pick languages (we suggest **Python** and **TypeScript**).

## Links (fill in after publishing)

- Developer portal: _link_
- Python SDK: _link_
- TypeScript SDK: _link_

Sources: [APIMatic CLI portal quickstart](https://docs.apimatic.io/cli-getting-started/portal-quickstart-dac/),
[Importing an API specification](https://docs.apimatic.io/getting-started/importing-api-spec/).
