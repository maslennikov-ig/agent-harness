export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function requestJson<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { error?: string };
      message = payload.error ?? message;
    } catch {
      // Preserve the status text when an error response is not JSON.
    }
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { error?: string };
      message = payload.error ?? message;
    } catch {
      // Preserve the status text when an error response is not JSON.
    }
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}
