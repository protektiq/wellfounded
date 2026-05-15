import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { getApiBaseUrl } from "@/lib/api-base";

const _MAX_COOKIE_HEADER = 8192;

const buildCookieHeader = async (): Promise<string | null> => {
  const jar = await cookies();
  const parts = jar.getAll().map((c) => {
    const nameLen = c.name.length;
    const valLen = c.value.length;
    if (nameLen === 0 || nameLen > 4096 || valLen > 8192) {
      throw new Error("cookie name or value exceeds allowed length");
    }
    return `${c.name}=${c.value}`;
  });
  const header = parts.join("; ");
  if (header.length > _MAX_COOKIE_HEADER) {
    throw new Error("combined Cookie header exceeds maximum length");
  }
  if (header.length === 0) {
    return null;
  }
  return header;
};

export const serverFetchJson = async (
  path: string,
  init?: Omit<RequestInit, "headers"> & {
    headers?: Record<string, string>;
  },
): Promise<Response> => {
  const base = getApiBaseUrl();
  if (path.length === 0 || path.length > 2048 || !path.startsWith("/")) {
    throw new Error("path must be a non-empty API path starting with /");
  }
  const url = `${base}${path}`;
  const cookieHeader = await buildCookieHeader();
  const headers: Record<string, string> = {
    ...(init?.headers ?? {}),
  };
  if (cookieHeader !== null) {
    headers.Cookie = cookieHeader;
  }
  return fetch(url, {
    ...init,
    headers,
    cache: "no-store",
  });
};

export const serverFetchJsonOrRedirect = async (
  path: string,
  init?: Omit<RequestInit, "headers"> & {
    headers?: Record<string, string>;
  },
): Promise<Response> => {
  const res = await serverFetchJson(path, init);
  if (res.status === 401) {
    redirect("/");
  }
  return res;
};
