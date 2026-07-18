# resto-mcp 🍝

MCP server that searches restaurants via **Google Places** and returns an interactive **mcp-ui** carousel. Streamable HTTP transport — ready for Mistral Le Chat / Alpic.

Python 3.14 · [FastMCP](https://github.com/modelcontextprotocol/python-sdk) · [uv](https://docs.astral.sh/uv/)

## Run locally
```bash
uv python install 3.14
uv sync --locked
cp .env.example .env   # add your GOOGLE_MAPS_API_KEY
uv run main.py         # POST http://localhost:3000/mcp
```
Enable **Places API (New)** on your Google Cloud project for the key.

## Test with Mistral Vibe locally

Use ngrok to expose your local server for testing in Mistral Le Chat:

```bash
# One-time setup: authenticate ngrok (requires free account)
ngrok config add-authtoken <YOUR_AUTHTOKEN>  # Get it from https://dashboard.ngrok.com/get-started/your-authtoken

# Terminal 1: Start your server
MCP_HTTP_PORT=8001 uv run main.py

# Terminal 2: Expose it via ngrok
ngrok http 8001
# Copy the forwarding URL (e.g., https://abc123.ngrok.io)
```

In Mistral Le Chat:
- Connectors → Add MCP → paste `https://abc123.ngrok.io/mcp`
- Ask: *"Where should I eat in Paris?"* → carousel renders

> Free ngrok accounts get a new random subdomain each time. Use `ngrok http --subdomain=resto-mcp 8001` if you have a paid plan to keep a fixed URL.

---

## Run automated tests
```bash
uv run pytest
```

## Deploy on Alpic
1. Push this repo to GitHub (private is fine).
2. New project on Alpic → connect the repo → select the **Python 3.14** runtime.
3. Install: `uv sync --locked` · Start: `uv run main.py` (also in `alpic.json`).
4. Env var: `GOOGLE_MAPS_API_KEY`
5. Alpic gives you a public URL → your MCP endpoint is `https://<that-url>/mcp`

> Note: `MCP_ALLOWED_HOSTS` is left unset on purpose. FastMCP ships with
> DNS-rebinding protection restricted to localhost, which would reject every
> request once the server sits behind a public domain. See `.env.example`.

## Add to Mistral Le Chat
Connectors → add MCP → paste the `https://<alpic-url>/mcp` endpoint.
Then ask: *"Where should I eat in Paris 11e?"* → the carousel renders automatically.

## Team
- Danny Antonelli
- Andrea Gemelli
- Lorenzo Santolini
- Giulia Buzzetti

## Tool
`search_restaurants(location, limit?)` → mcp-ui carousel + text fallback.
