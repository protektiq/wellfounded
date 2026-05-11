const _MAX_URL_LEN = 512;

const _normalizeApiBaseUrl = (raw: string): string => {
  const trimmed = raw.trim();
  if (trimmed.length === 0 || trimmed.length > _MAX_URL_LEN) {
    throw new Error("NEXT_PUBLIC_API_URL must be a non-empty URL up to 512 characters");
  }
  if (!trimmed.startsWith("http://") && !trimmed.startsWith("https://")) {
    throw new Error("NEXT_PUBLIC_API_URL must start with http:// or https://");
  }
  return trimmed.replace(/\/+$/, "");
};

export const getApiBaseUrl = (): string => {
  const fromEnv = process.env.NEXT_PUBLIC_API_URL;
  if (fromEnv === undefined || fromEnv.trim() === "") {
    return _normalizeApiBaseUrl("http://127.0.0.1:8000");
  }
  return _normalizeApiBaseUrl(fromEnv);
};
