function resolveDefaultApiBase() {
  if (typeof window === "undefined") {
    return "http://localhost:8000";
  }

  const { hostname, protocol } = window.location;
  if (hostname === "localhost" || hostname === "127.0.0.1") {
    return "http://localhost:8000";
  }

  return `${protocol}//api.${hostname}`;
}

const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE || resolveDefaultApiBase()
).replace(/\/+$/, "");

export const CUSTOM_API_BASE =
  process.env.NEXT_PUBLIC_CUSTOM_API_BASE ?? `${API_BASE}/api/custom`;

export const AUTH_API_BASE =
  process.env.NEXT_PUBLIC_AUTH_API_BASE ?? `${API_BASE}/api/auth`;

export const LLAMA_API_BASE =
  process.env.NEXT_PUBLIC_LLAMA_API_BASE ?? `${API_BASE}/api/llama`;
