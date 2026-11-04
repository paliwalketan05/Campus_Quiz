# CampusQuiz Frontend

React, TypeScript, Vite, and Tailwind CSS application for student, faculty, and
administrator workflows.

## Development

Use Node.js 22 and npm:

```powershell
Copy-Item .env.example .env.local
npm ci
npm run dev
```

The default API base is `http://localhost:8000/api/v1`. Set
`VITE_API_BASE_URL` in `.env.local` when the backend runs elsewhere. Do not put
secrets in Vite variables; values are embedded in the browser bundle.

## Checks

```powershell
npm run lint
npm run build
```

See [`../docs/DEPLOYMENT.md`](../docs/DEPLOYMENT.md) for staging configuration
and acceptance checks.
