import test from "node:test";
import assert from "node:assert/strict";
import { app } from "../src/server.js";

// Boot the real express app on an ephemeral port and talk to it over HTTP,
// so this exercises the same path Alpic hits in production.
const server = await new Promise((resolve) => {
  const s = app.listen(0, () => resolve(s));
});
const base = `http://127.0.0.1:${server.address().port}`;

test.after(() => server.close());

const MCP_HEADERS = {
  "Content-Type": "application/json",
  Accept: "application/json, text/event-stream",
};

// The transport may answer as JSON or as an SSE stream; accept either.
async function readRpc(res) {
  const body = await res.text();
  if (res.headers.get("content-type")?.includes("text/event-stream")) {
    const line = body.split("\n").find((l) => l.startsWith("data:"));
    assert.ok(line, `no SSE data frame in: ${body.slice(0, 200)}`);
    return JSON.parse(line.slice(5).trim());
  }
  return JSON.parse(body);
}

function rpc(method, params, id = 1) {
  return fetch(`${base}/mcp`, {
    method: "POST",
    headers: MCP_HEADERS,
    body: JSON.stringify({ jsonrpc: "2.0", id, method, params }),
  });
}

const INIT_PARAMS = {
  protocolVersion: "2024-11-05",
  capabilities: {},
  clientInfo: { name: "test-client", version: "0.0.0" },
};

test("health endpoint responds", async () => {
  const res = await fetch(`${base}/health`);
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { ok: true });
});

test("root endpoint advertises the MCP path", async () => {
  const res = await fetch(`${base}/`);
  assert.equal(res.status, 200);
  assert.match(await res.text(), /POST \/mcp/);
});

test("initialize handshake returns the server identity", async () => {
  const res = await rpc("initialize", INIT_PARAMS);
  assert.equal(res.status, 200);

  const json = await readRpc(res);
  assert.equal(json.error, undefined);
  assert.equal(json.result.serverInfo.name, "resto-mcp");
  assert.ok(json.result.capabilities.tools, "server must advertise tools capability");
});

test("tools/list exposes search_restaurants with its input schema", async () => {
  // Stateless transport: each request stands alone, but the SDK still wants
  // an initialize on the same request chain, so re-init then list.
  await rpc("initialize", INIT_PARAMS);
  const res = await rpc("tools/list", {}, 2);

  const json = await readRpc(res);
  assert.equal(json.error, undefined);

  const tool = json.result.tools.find((t) => t.name === "search_restaurants");
  assert.ok(tool, `search_restaurants missing from: ${JSON.stringify(json.result.tools)}`);
  assert.match(tool.description, /restaurant/i);
  assert.deepEqual(tool.inputSchema.required, ["location"]);
  assert.equal(tool.inputSchema.properties.location.type, "string");
  assert.equal(tool.inputSchema.properties.limit.type, "integer");
});

test("GET and DELETE /mcp are rejected with 405", async () => {
  for (const method of ["GET", "DELETE"]) {
    const res = await fetch(`${base}/mcp`, { method });
    assert.equal(res.status, 405, `${method} /mcp should be 405`);

    const json = await res.json();
    assert.equal(json.jsonrpc, "2.0");
    assert.equal(json.error.code, -32000);
  }
});

test("malformed JSON body does not crash the server", async () => {
  const res = await fetch(`${base}/mcp`, {
    method: "POST",
    headers: MCP_HEADERS,
    body: "{not json",
  });
  assert.ok(res.status >= 400, `expected an error status, got ${res.status}`);

  // Server still alive afterwards.
  const health = await fetch(`${base}/health`);
  assert.equal(health.status, 200);
});
