# VarshaGuard NebulaOrb (Next.js)

This folder is a standalone Next.js App Router implementation of the supplied NebulaOrb component and its `nebula-scene.tsx` shader scene.

## Run locally

```bash
cd nebula-orb-next
npm install
npm run dev
```

Open http://localhost:3000. The demo includes state buttons for idle, listening, thinking, speaking, and disabled.

## Deploy this app to Vercel

Create a separate Vercel project from this repository and set **Root Directory** to `nebula-orb-next`. Vercel will detect Next.js and use `npm run build`.

## Integration note

The existing main VarshaGuard site is currently served by Flask from `frontend/`, with root-level Vercel routing to `backend/app.py`. A React/Next.js component cannot be imported directly into that plain HTML page. Deploy this Next.js app first, then integrate it into the existing chat through an explicit cross-app mount/iframe or migrate the frontend routing to Next.js. This folder does not silently change the current Flask routes or replace the main site's entrypoint.
