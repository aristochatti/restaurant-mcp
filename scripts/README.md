# Google Maps List MCP Server - Guide

A Model Context Protocol (MCP) server that resolves public Google Maps shared lists, extracts places, coordinates, and custom user-written notes, and enriches them with price ranges and images.

## Requirements
* Python 3.10+
* Node.js & npm (optional, only needed for tunneling to web apps)

## Installation & Setup

1. Create a Python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Install the official MCP SDK and dependencies:
   ```bash
   pip install mcp starlette uvicorn pydantic
   ```

---

## Execution Modes

### Mode A: Desktop Clients (stdio)
Desktop apps (like Claude Desktop or Cursor) connect via standard I/O (stdio).

#### Claude Desktop Configuration
Add this to your configuration file (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "google-maps-list": {
      "command": "/absolute/path/to/venv/bin/python3",
      "args": ["/absolute/path/to/mcp_server.py"],
      "env": {
        "GOOGLE_PLACES_API_KEY": "YOUR_GOOGLE_MAPS_API_KEY"
      }
    }
  }
}
```

---

### Mode B: Web Chat Clients (SSE HTTP + Public Tunnel)
Web-based chat apps (like Mistral Vibe Web) connect over HTTP via Server-Sent Events (SSE). Because web browsers block HTTPS pages from connecting directly to unsecure `http://127.0.0.1` origins, and cloud servers cannot reach your computer's local interface directly, you must run a secure public tunnel.

#### Step 1: Start the Local MCP Server
Expose the server locally on port `8000` using the `sse` transport:
```bash
export GOOGLE_PLACES_API_KEY="YOUR_GOOGLE_MAPS_API_KEY"
./venv/bin/python3 mcp_server.py --transport sse --port 8000
```
*The server is now listening at `http://127.0.0.1:8000/sse`.*

#### Step 2: Open the Secure Tunnel (Pinggy)
Use SSH (built-in on macOS/Linux) to map port `8000` to a public secure HTTPS URL. We route through secure port `443` to bypass standard network restrictions:
```bash
ssh -p 443 -o StrictHostKeyChecking=no -R 80:localhost:8000 +ssl@a.pinggy.io
```
This command outputs temporary URLs in the terminal:
```text
https://phryk-130-93-90-94.run.pinggy-free.link
```

#### Step 3: Register in your Web App
Copy the HTTPS URL generated in Step 2, append `/sse` to it, and input it in your web chat application tool settings:
`https://phryk-130-93-90-94.run.pinggy-free.link/sse`

Your web chat client is now connected directly to your local Maps list extractor!
