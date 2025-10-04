// src/lib/api.ts
import axios from "axios";

const baseURL =
  import.meta.env.VITE_CONTROLLER_BASE_URL ?? "http://localhost:8765";

export const api = axios.create({ baseURL, timeout: 10000 });

// Optional dev-bearer to match backend DEV_BEARER_TOKEN
api.interceptors.request.use((config) => {
  const token = import.meta.env.VITE_DEV_BEARER_TOKEN;
  if (token) {
    config.headers = config.headers ?? {};
    (config.headers as any).Authorization = `Bearer ${token}`;
  }
  return config;
});
