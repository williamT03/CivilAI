const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"
).replace(/\/+$/, "");

export const CUSTOM_API_BASE =
  process.env.NEXT_PUBLIC_CUSTOM_API_BASE ?? `${API_BASE}/api/custom`;

export const AUTH_API_BASE =
  process.env.NEXT_PUBLIC_AUTH_API_BASE ?? `${API_BASE}/api/auth`;

export const LLAMA_API_BASE =
  process.env.NEXT_PUBLIC_LLAMA_API_BASE ?? `${API_BASE}/api/llama`;
