const configuredBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").trim();

export function apiUrl(path: string): string {
  const baseUrl = configuredBaseUrl.replace(/\/+$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;

  return `${baseUrl}${normalizedPath}`;
}
