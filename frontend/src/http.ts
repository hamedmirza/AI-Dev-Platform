export function api<T>(path: string, init?: RequestInit): Promise<T> {
  return fetch(path, {
    credentials: "same-origin",
    headers: {
      "content-type": "application/json",
      ...(init?.headers || {})
    },
    ...init
  }).then(async (response) => {
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `${response.status} ${response.statusText}`);
    }
    return response.json() as Promise<T>;
  });
}

export function postForm(path: string, fields: Record<string, string>): Promise<Response> {
  const form = new FormData();
  Object.entries(fields).forEach(([key, value]) => form.append(key, value));
  return fetch(path, {
    method: "POST",
    credentials: "same-origin",
    body: form,
    redirect: "manual"
  });
}
