# Edge-first Security and Deployment

Rate limiting, SSL termination, and DDoS mitigation are enforced at Cloudflare's edge network. The backend server connects securely via `cloudflared` (Cloudflare Tunnel) with zero exposed ports.

The backend VPS runs behind a Cloudflare Tunnel — no public IP, no open ports except the tunnel itself. Cloudflare handles rate limiting (15 req/min per IP on `/api/*`), SSL, and DDoS protection at the edge before traffic ever reaches the server. This eliminates attack surfaces on the backend while protecting Groq API keys and host CPU at $0 cost.

Considered options: application-level rate limiting in FastAPI (rejected — runs after traffic reaches the server, wasting CPU), cloudflared-only without rate limiting (rejected — no abuse protection).
