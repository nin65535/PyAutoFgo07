export type SessionCredentials = {
  sessionId: string;
  token: string;
};

let cached: SessionCredentials | undefined;

export function getSessionCredentials(): SessionCredentials {
  if (cached) return cached;
  const values = new URLSearchParams(window.location.hash.slice(1));
  const sessionId = values.get("autofgoSession");
  const token = values.get("autofgoToken");
  if (!sessionId || !token) throw new Error("起動セッション情報がありません。");
  cached = { sessionId, token };
  history.replaceState(null, "", `${location.pathname}${location.search}`);
  return cached;
}

export function authenticatedHeaders(headers?: HeadersInit): Headers {
  const credentials = getSessionCredentials();
  const result = new Headers(headers);
  result.set("X-AutoFgo-Session-Id", credentials.sessionId);
  result.set("Authorization", `Bearer ${credentials.token}`);
  return result;
}

export function authenticatedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  return fetch(input, { ...init, headers: authenticatedHeaders(init.headers) });
}
