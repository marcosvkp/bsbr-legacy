/**
 * Base da API:
 * - Server (RSC): `API_INTERNAL_URL` em runtime (dentro do compose é
 *   http://api:8000/api/v1). Vars sem NEXT_PUBLIC_ NÃO são inlinadas no build.
 * - Browser: `NEXT_PUBLIC_API_URL` embutida no bundle (http://localhost:$PORT).
 */
function resolveApiBase(): string {
  if (typeof window === "undefined") {
    return process.env.API_INTERNAL_URL ?? "http://api:8000/api/v1";
  }
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
}

export const API_BASE = resolveApiBase();

const REQUEST_TIMEOUT_MS = 10_000;

type JsonInit = { headers?: Record<string, string>; timeoutMs?: number };

export class ApiError extends Error {
  readonly status: number | null;
  readonly cause?: unknown;

  constructor(message: string, status: number | null = null, cause?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.cause = cause;
  }
}

async function requestJson<T>(
  path: string,
  method: "GET" | "POST",
  body: unknown,
  init?: JsonInit,
): Promise<T> {
  const controller = new AbortController();
  const timeoutMs = init?.timeoutMs ?? REQUEST_TIMEOUT_MS;
  const timeout = setTimeout(
    () => controller.abort(),
    timeoutMs,
  );

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      signal: controller.signal,
      // Envia/recebe cookies de sessão do usuário (bsbr_user_session) no
      // fetch cross-origin (dev: localhost:3000 → localhost:8000).
      credentials: "include",
      headers: {
        Accept: "application/json",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
  } catch (cause) {
    const timedOut = controller.signal.aborted;
    throw new ApiError(
      timedOut
        ? `Timeout ao chamar ${API_BASE}${path}`
        : `Falha de rede ao chamar ${API_BASE}${path}`,
      null,
      cause,
    );
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    throw new ApiError(
      `Resposta ${response.status} de ${API_BASE}${path}`,
      response.status,
    );
  }

  try {
    return (await response.json()) as T;
  } catch (cause) {
    throw new ApiError(
      `Resposta inválida (JSON) de ${API_BASE}${path}`,
      response.status,
      cause,
    );
  }
}

/**
 * GET JSON da API do backend, com timeout de 10s via AbortController.
 * Lança `ApiError` em rede indisponível, timeout ou status não-2xx.
 */
export async function getJson<T>(path: string, init?: JsonInit): Promise<T> {
  return requestJson<T>(path, "GET", undefined, init);
}

/** POST JSON da API do backend (mesmo contrato de erro de `getJson`). */
export async function postJson<T>(
  path: string,
  body: unknown,
  init?: JsonInit,
): Promise<T> {
  return requestJson<T>(path, "POST", body ?? {}, init);
}

