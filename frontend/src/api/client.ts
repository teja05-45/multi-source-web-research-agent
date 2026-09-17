import type {
  Conversation,
  ConversationCreate,
  ConversationUpdate,
  Message,
  ProviderStatus,
  ResearchReport,
  ResearchRequest,
  ResearchRequestCreate,
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const REQUEST_TIMEOUT_MS = 150_000;

/**
 * Error category for a failed API call. The backend guarantees a structured
 * envelope (`{ error: { code, message, request_id, retryable } }`) on every
 * failure, so the client can surface an actionable message instead of an
 * opaque "Failed to fetch".
 */
export type ApiErrorCode = string;

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: ApiErrorCode = "http_error",
    public requestId?: string,
    public retryable: boolean = status >= 500
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** The fetch() call itself failed (offline, backend down, or CORS masked
 *  the response). No HTTP status is available from the server. */
export class NetworkError extends ApiError {
  constructor(message: string, requestId?: string) {
    super(message, 0, "network_error", requestId, true);
    this.name = "NetworkError";
  }
}

async function parseError(response: Response): Promise<ApiError> {
  let code: ApiErrorCode = "http_error";
  let message = `Request failed with status ${response.status}`;
  let requestId: string | undefined;
  let retryable = response.status >= 500;

  try {
    const body = await response.json();
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      requestId = body.error.request_id ?? requestId;
      retryable = body.error.retryable ?? retryable;
    } else if (typeof body?.detail === "string") {
      message = body.detail;
    } else if (body?.detail?.message) {
      message = body.detail.message;
    }
  } catch {
    // Response body wasn't JSON; keep the defaults.
  }

  requestId = requestId || response.headers.get("X-Request-ID") || undefined;

  if (response.status === 401) {
    message = "Research backend denied access. Check the API key configuration.";
  } else if (response.status === 404) {
    message = "The requested resource no longer exists.";
  }

  return new ApiError(message, response.status, code, requestId, retryable);
}

async function handleResponse(response: Response): Promise<Response> {
  if (!response.ok) {
    throw await parseError(response);
  }
  return response;
}

async function fetchWithTimeout(
  url: string,
  init: RequestInit = {},
  timeoutMs: number = REQUEST_TIMEOUT_MS
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(
        "Request timed out. The research run took too long; try a quicker, more specific question.",
        408,
        "timeout"
      );
    }
    if (err instanceof TypeError) {
      // fetch() rejects TypeError on network failure or when CORS blocks the
      // response. With the backend's error contract, CORS can no longer hide a
      // server 500, so this almost always means the backend is unreachable.
      throw new NetworkError(
        "Could not reach the research backend. Check that it is running, the CORS origin is allowed, and the API base URL in frontend/.env is correct."
      );
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export async function runResearch(request: ResearchRequest, conversationId?: string): Promise<ResearchReport> {
  const url = conversationId
    ? `${API_BASE_URL}/api/conversations/${conversationId}/research`
    : `${API_BASE_URL}/api/research`;
  const response = await handleResponse(
    await fetchWithTimeout(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    })
  );
  return response.json();
}

export async function checkHealth(): Promise<Record<string, unknown>> {
  const response = await handleResponse(await fetchWithTimeout(`${API_BASE_URL}/health`, {}, 10_000));
  return response.json();
}

export async function getProviderStatus(): Promise<ProviderStatus[]> {
  const response = await handleResponse(
    await fetchWithTimeout(`${API_BASE_URL}/api/providers/status`, {}, 10_000)
  );
  const body = (await response.json()) as { providers: ProviderStatus[] };
  return body.providers;
}

// --- Conversation API ---

export async function listConversations(
  status?: string,
  search?: string,
  limit = 50,
  offset = 0
): Promise<Conversation[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (search) params.set("search", search);
  params.set("limit", limit.toString());
  params.set("offset", offset.toString());

  const response = await handleResponse(
    await fetchWithTimeout(`${API_BASE_URL}/api/conversations?${params.toString()}`)
  );
  return response.json();
}

export async function createConversation(payload: ConversationCreate): Promise<Conversation> {
  const response = await handleResponse(
    await fetchWithTimeout(`${API_BASE_URL}/api/conversations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
  return response.json();
}

export async function getConversation(id: string): Promise<Conversation> {
  const response = await handleResponse(await fetchWithTimeout(`${API_BASE_URL}/api/conversations/${id}`));
  return response.json();
}

export async function updateConversation(id: string, payload: ConversationUpdate): Promise<Conversation> {
  const response = await handleResponse(
    await fetchWithTimeout(`${API_BASE_URL}/api/conversations/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
  return response.json();
}

export async function deleteConversation(id: string): Promise<void> {
  const url = `${API_BASE_URL}/api/conversations/${id}`;
  await handleResponse(
    await fetchWithTimeout(url, {
      method: "DELETE",
    })
  );
}

export async function listMessages(
  conversationId: string,
  limit = 100,
  offset = 0
): Promise<Message[]> {
  const params = new URLSearchParams();
  params.set("limit", limit.toString());
  params.set("offset", offset.toString());

  const response = await handleResponse(
    await fetchWithTimeout(`${API_BASE_URL}/api/conversations/${conversationId}/messages?${params.toString()}`)
  );
  return response.json();
}

export async function runResearchInConversation(
  conversationId: string,
  request: ResearchRequestCreate
): Promise<ResearchReport> {
  const response = await handleResponse(
    await fetchWithTimeout(`${API_BASE_URL}/api/conversations/${conversationId}/research`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    })
  );
  return response.json();
}