# Civil AI Web

This frontend is a static Next.js app that talks to the Civil AI backend over HTTP.

## Local development

```bash
npm install
npm run dev
```

Set environment variables in `.env.local`:

```env
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_ENABLE_LLAMA=false
```

## Cloudflare deployment

Deploy this app from the `frontend/Website/civil-ai-web` directory, not the repository root.

Use these Cloudflare Pages settings:

- Framework preset: `Next.js (Static HTML Export)`
- Root directory: `frontend/Website/civil-ai-web`
- Build command: `npx next build`
- Build output directory: `out`

Set these environment variables in Cloudflare Pages:

```env
NEXT_PUBLIC_API_BASE=https://api.civilai.willcloudlab.com
NEXT_PUBLIC_ENABLE_LLAMA=false
```

## Notes

- The backend must stay on your server. Cloudflare Pages only hosts the frontend.
- PDF uploads and retrieval still go through the backend API.
- Use a public `https://...` backend URL. A private LAN IP such as `192.168.x.x` or a plain `http://...` endpoint will not work from the public Cloudflare site.
- The app derives `/api/custom`, `/api/auth`, and `/api/llama` from `NEXT_PUBLIC_API_BASE`.
- Turn `NEXT_PUBLIC_ENABLE_LLAMA=true` only if `/api/llama` is actually live on the backend.
