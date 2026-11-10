export async function apiRequest(path: string, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(path, { ...init, signal: AbortSignal.timeout(75000) });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new Error('The request timed out. Please try again.');
    }
    throw new Error('Cannot reach the backend. Start FastAPI on port 8000 and try again.');
  }
  if (!response.ok) {
    let detail: unknown;
    try { detail = (await response.json()).detail; } catch { /* Vite may return a non-JSON proxy error. */ }
    throw new Error(typeof detail === 'string' ? detail : 'The voice service is unavailable. Check that FastAPI is running and try again.');
  }
  return response;
}
