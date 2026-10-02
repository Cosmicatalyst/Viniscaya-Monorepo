export async function medicalApi(path: string, init?: RequestInit) {
  const response = await fetch(`/api/medical/${path}`, init);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : data.error || "The request failed.");
  return data;
}

export type ChatMessage = { role: "user" | "assistant"; content: string; startedAt?: number; duration?: number };
