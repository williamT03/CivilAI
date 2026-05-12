# Frontend Feature Map

The frontend keeps Next.js route files under `app/` because the framework requires that shape. Feature folders provide readable facades over those route files, hooks, API clients, components, context, and assets.

## Current Facades

- `Features/Chat/chat_run.ts`: chat page, hooks, composer, setup panel, thread list, and message list.
- `Features/Auth/auth_run.ts`: auth context, protected route, and auth experience component.
- `Features/Layout/layout_run.ts`: site header, reveal, theme, and workspace shell components.
- `Features/API/api_run.ts`: frontend API client/config helpers.
- `Features/Routes/routes_run.ts`: route page exports for account, about, login, register, subscription, and home.
- `Features/Assets/assets_run.ts`: public visual asset paths.
