/**
 * Cloudflare Worker: Edge Gateway & Workers AI Integration
 * Proxies research requests to backend (Render, Railway, Cloud Run)
 * with Edge caching and optional Workers AI validation.
 */
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Health check endpoint at the edge
    if (url.pathname === "/edge-health") {
      return new Response(JSON.stringify({
        status: "healthy",
        edge: "cloudflare-worker",
        timestamp: new Date().toISOString()
      }), {
        headers: { "Content-Type": "application/json" }
      });
    }

    // Edge AI Claim Quick-Check using Cloudflare Workers AI
    if (url.pathname === "/api/edge/check-claim" && request.method === "POST" && env.AI) {
      try {
        const body = await request.json();
        const claim = body.claim || "";
        
        const response = await env.AI.run("@cf/meta/llama-3-8b-instruct", {
          messages: [
            { role: "system", content: "You are an objective fact checker. Return JSON: {\"is_verifiable\": boolean, \"category\": string}" },
            { role: "user", content: `Evaluate this claim: "${claim}"` }
          ]
        });
        return new Response(JSON.stringify(response), {
          headers: { "Content-Type": "application/json" }
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), { status: 500 });
      }
    }

    // Proxy all other requests to Backend (Render, Railway, or Cloud Run)
    const backendUrl = env.BACKEND_API_URL || "http://localhost:8080";
    const targetUrl = new URL(url.pathname + url.search, backendUrl);

    const modifiedRequest = new Request(targetUrl, {
      method: request.method,
      headers: request.headers,
      body: request.body,
      redirect: "follow"
    });

    try {
      const response = await fetch(modifiedRequest);
      return response;
    } catch (err) {
      return new Response(JSON.stringify({
        error: "Backend unavailable",
        message: err.message,
        hint: "Ensure BACKEND_API_URL is configured in wrangler.toml"
      }), {
        status: 502,
        headers: { "Content-Type": "application/json" }
      });
    }
  }
};
