# resto-mcp

MCP server that searches restaurants via **Google Places** and returns an interactive **mcp-ui** carousel. Streamable HTTP transport — ready for Mistral Le Chat / Alpic.

## Run locally
```bash
npm install
cp .env.example .env   # add your GOOGLE_MAPS_API_KEY
npm start              # POST http://localhost:3000/mcp
```
Enable **Places API (New)** on your Google Cloud project for the key.

## Deploy on Alpic
1. Push this repo to GitHub (private is fine).
2. New project on Alpic → connect the repo.
3. Build: `npm install` · Start: `npm start`
4. Env var: `GOOGLE_MAPS_API_KEY`
5. Alpic gives you a public URL → your MCP endpoint is `https://<that-url>/mcp`

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
