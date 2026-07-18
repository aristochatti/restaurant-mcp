import { pathToFileURL } from "node:url";
import express from "express";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { z } from "zod";
import { createUIResource } from "@mcp-ui/server";
import { searchRestaurants } from "./places.js";
import { buildCarouselHtml } from "./carousel.js";

export function makeServer() {
  const server = new McpServer({ name: "resto-mcp", version: "0.1.0" });

  server.registerTool(
    "search_restaurants",
    {
      title: "Search restaurants",
      description:
        "Search restaurants in a given location (city, neighborhood, or address) and display them as an interactive carousel. Use whenever the user asks where to eat or for restaurant recommendations.",
      inputSchema: {
        location: z.string().describe("City, neighborhood, or address, e.g. 'Paris 11e' or 'Shibuya, Tokyo'"),
        limit: z.number().int().min(1).max(20).optional().describe("How many restaurants to return (default 8)"),
      },
    },
    async ({ location, limit }) => {
      const restaurants = await searchRestaurants(location, limit ?? 8);

      if (restaurants.length === 0) {
        return { content: [{ type: "text", text: `No restaurants found in "${location}".` }] };
      }

      const html = buildCarouselHtml({ location, restaurants });
      const ui = createUIResource({
        uri: `ui://restaurants/${encodeURIComponent(location)}`,
        content: { type: "rawHtml", htmlString: html },
        encoding: "text",
      });

      // Text fallback for hosts that don't render mcp-ui.
      const fallback = restaurants
        .map((r, i) => {
          const price = r.priceLevel ? " · " + "€".repeat(r.priceLevel) : "";
          const rating = r.rating ? ` · ★${r.rating}` : "";
          return `${i + 1}. ${r.name}${rating}${price} — ${r.address}`;
        })
        .join("\n");

      return {
        content: [
          ui,
          { type: "text", text: `Found ${restaurants.length} restaurants in ${location}:\n${fallback}` },
        ],
      };
    }
  );

  return server;
}

export const app = express();
app.use(express.json());

// Handle malformed bodies ourselves so express's default handler doesn't dump
// a parse stack to stderr on every bad request.
app.use((err, _req, res, next) => {
  if (err instanceof SyntaxError && "body" in err) {
    return res.status(400).json({
      jsonrpc: "2.0",
      error: { code: -32700, message: "Parse error." },
      id: null,
    });
  }
  return next(err);
});

// Stateless Streamable HTTP endpoint — fresh server per request (simple + Alpic-friendly).
app.post("/mcp", async (req, res) => {
  try {
    const server = makeServer();
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
    res.on("close", () => { transport.close(); server.close(); });
    await server.connect(transport);
    await transport.handleRequest(req, res, req.body);
  } catch (err) {
    console.error(err);
    if (!res.headersSent) res.status(500).json({ error: String(err) });
  }
});

// Streamable HTTP is POST-only here; reject other verbs on /mcp with 405
// (matches Alpic's expected conformance behaviour).
const methodNotAllowed = (_req, res) =>
  res.status(405).json({
    jsonrpc: "2.0",
    error: { code: -32000, message: "Method not allowed." },
    id: null,
  });
app.get("/mcp", methodNotAllowed);
app.delete("/mcp", methodNotAllowed);

app.get("/", (_req, res) => res.send("resto-mcp is running. POST /mcp"));
app.get("/health", (_req, res) => res.json({ ok: true }));

// Alpic injects MCP_HTTP_PORT; fall back to PORT / 3000 for local runs.
// Only listen when run directly (`npm start`) so tests can import `app` and
// bind their own ephemeral port.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const PORT = process.env.MCP_HTTP_PORT || process.env.PORT || 3000;
  app.listen(PORT, () => console.log(`resto-mcp listening on :${PORT} (POST /mcp)`));
}
