async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch (e) {
    throw new Error(`后端不可达（${url}）`);
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      detail = j.detail || j.error || detail;
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  meta: () => request<any>("/api/meta"),
  status: () => request<any>("/api/status"),
  diagnostics: () => request<any>("/api/diagnostics"),
  models: () => request<any>("/api/models"),
  llmModels: () => request<any>("/api/llm/models"),
  getSettings: () => request<any>("/api/settings"),
  saveSettings: (patch: any) => request<any>("/api/settings", json("PUT", patch)),
  getUiState: () => request<{ state: any }>("/api/ui-state"),
  saveUiState: (state: any) => request<any>("/api/ui-state", json("PUT", { state })),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ id: string; url: string; width: number; height: number }>(
      "/api/upload",
      { method: "POST", body: fd }
    );
  },
  generate: (body: any) => request<any>("/api/generate", json("POST", body)),
  refine: (body: any) => request<any>("/api/refine", json("POST", body)),
  render: (body: any) => request<any>("/api/render", json("POST", body)),
  cancel: (id: string) => request<any>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  history: () => request<{ items: any[] }>("/api/history"),
  historyItem: (id: string) => request<any>(`/api/history/${id}`),
  deleteHistory: (id: string) =>
    request<any>(`/api/history/${id}`, { method: "DELETE" }),
  llmStart: (gguf?: string, mmproj?: string) =>
    request<any>("/api/llm/start", json("POST", { gguf, mmproj })),
  llmStop: () => request<any>("/api/llm/stop", { method: "POST" }),
};
