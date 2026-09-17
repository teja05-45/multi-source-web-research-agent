import type { ProviderStatus, ResearchReport, ResearchRequest } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const REQUEST_TIMEOUT_MS = 150_000;

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
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
      throw new ApiError("Request timed out. The research run took too long; try a quicker or more specific question.", 408);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export async function runResearch(request: ResearchRequest): Promise<ResearchReport> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/research`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      message = body?.detail?.message || body?.message || message;
    } catch {
      // response body wasn't JSON; keep the default message
    }
    throw new ApiError(message, response.status);
  }

  return response.json();
}

export async function checkHealth(): Promise<Record<string, unknown>> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/health`, {}, 10_000);
  if (!response.ok) {
    throw new ApiError("Health check failed", response.status);
  }
  return response.json();
}

export async function getProviderStatus(): Promise<ProviderStatus[]> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/providers/status`, {}, 10_000);
  if (!response.ok) {
    throw new ApiError("Provider status check failed", response.status);
  }
  const body = (await response.json()) as { providers: ProviderStatus[] };
  return body.providers;
}