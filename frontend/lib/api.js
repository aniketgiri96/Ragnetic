const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function getToken() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("ragnetic_token") || "";
}

function getHeaders() {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function throwForError(res) {
  if (res.ok) return;
  let message = res.statusText;
  try {
    const data = await res.json();
    if (data?.detail) message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    else if (data?.message) message = data.message;
    else message = JSON.stringify(data);
  } catch {
    try {
      message = await res.text();
    } catch {
      message = res.statusText;
    }
  }
  throw new ApiError(message || "Request failed", res.status);
}

export async function listKb() {
  const res = await fetch(`${API}/kb/`, { headers: getHeaders() });
  await throwForError(res);
  return res.json();
}

export async function getOnboardingStatus() {
  const res = await fetch(`${API}/onboarding/status`, { headers: getHeaders() });
  await throwForError(res);
  return res.json();
}

export async function createOnboardingSampleKb() {
  const res = await fetch(`${API}/onboarding/sample-kb`, {
    method: "POST",
    headers: getHeaders(),
  });
  await throwForError(res);
  return res.json();
}

export async function createKb(body) {
  const res = await fetch(`${API}/kb/`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({
      name: body?.name ?? "",
      description: body?.description ?? undefined,
    }),
  });
  await throwForError(res);
  return res.json();
}

export async function updateKb(kbId, body) {
  const payload = {};
  if (Object.prototype.hasOwnProperty.call(body || {}, "name")) payload.name = body.name;
  if (Object.prototype.hasOwnProperty.call(body || {}, "description")) payload.description = body.description;
  const res = await fetch(`${API}/kb/${encodeURIComponent(kbId)}`, {
    method: "PATCH",
    headers: getHeaders(),
    body: JSON.stringify(payload),
  });
  await throwForError(res);
  return res.json();
}

export async function deleteKb(kbId) {
  const res = await fetch(`${API}/kb/${encodeURIComponent(kbId)}`, {
    method: "DELETE",
    headers: getHeaders(),
  });
  await throwForError(res);
  return res.json();
}

export async function listKbAuditLogs(kbId, { limit = 100, action } = {}) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (action) params.set("action", String(action));
  const url = `${API}/kb/${encodeURIComponent(kbId)}/audit?${params.toString()}`;
  const res = await fetch(url, { headers: getHeaders() });
  await throwForError(res);
  return res.json();
}

export async function getKbAnalytics(kbId, { days } = {}) {
  const params = new URLSearchParams();
  if (days != null) params.set("days", String(days));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`${API}/kb/${encodeURIComponent(kbId)}/analytics${suffix}`, { headers: getHeaders() });
  await throwForError(res);
  return res.json();
}

export async function uploadFile(file, kbId) {
  const form = new FormData();
  form.append("file", file);
  const params = new URLSearchParams();
  if (kbId != null) params.set("kb_id", String(kbId));
  const url = params.toString() ? `${API}/upload/?${params.toString()}` : `${API}/upload/`;
  const headers = {};
  if (typeof window !== "undefined" && localStorage.getItem("ragnetic_token"))
    headers["Authorization"] = `Bearer ${localStorage.getItem("ragnetic_token")}`;
  const res = await fetch(url, { method: "POST", body: form, headers });
  await throwForError(res);
  return res.json();
}

export async function search(query, kbId) {
  const params = new URLSearchParams({ query });
  if (kbId != null) params.set("kb_id", String(kbId));
  const res = await fetch(`${API}/search/?${params}`, { headers: getHeaders() });
  await throwForError(res);
  return res.json();
}

export async function chat(body) {
  const res = await fetch(`${API}/chat/`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({
      message: body.message,
      kb_id: body.kb_id ?? undefined,
      session_id: body.session_id ?? undefined,
      async_mode: body.async_mode ?? undefined,
    }),
  });
  await throwForError(res);
  return res.json();
}

export async function submitChatFeedback(body) {
  const res = await fetch(`${API}/chat/feedback`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({
      message_id: body.message_id,
      rating: body.rating,
      comment: body.comment ?? undefined,
    }),
  });
  await throwForError(res);
  return res.json();
}

export async function chatStream(body, { onEvent } = {}) {
  const res = await fetch(`${API}/chat/stream`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({
      message: body.message,
      kb_id: body.kb_id ?? undefined,
      session_id: body.session_id ?? undefined,
    }),
  });
  await throwForError(res);
  if (!res.body) throw new ApiError("Streaming response body is unavailable.", 500);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalPayload = null;

  const emit = (event, payload) => {
    if (event === "done") finalPayload = payload;
    if (typeof onEvent === "function") onEvent({ event, payload });
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
      if (!rawEvent.trim()) continue;

      let eventName = "message";
      const dataLines = [];
      rawEvent.split("\n").forEach((line) => {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      });
      if (!dataLines.length) continue;

      const payloadText = dataLines.join("\n");
      let payload = payloadText;
      try {
        payload = JSON.parse(payloadText);
      } catch {
        // Keep plain text payload.
      }
      emit(eventName, payload);
    }
  }
  return finalPayload;
}

export async function documentStatus(id) {
  const res = await fetch(`${API}/documents/${id}/status`, { headers: getHeaders() });
  await throwForError(res);
  return res.json();
}

export async function listDocuments(kbId) {
  const params = new URLSearchParams();
  if (kbId != null) params.set("kb_id", String(kbId));
  const url = params.toString() ? `${API}/documents?${params}` : `${API}/documents`;
  const res = await fetch(url, { headers: getHeaders() });
  await throwForError(res);
  return res.json();
}

export async function renameDocument(documentId, filename) {
  const res = await fetch(`${API}/documents/${encodeURIComponent(documentId)}`, {
    method: "PATCH",
    headers: getHeaders(),
    body: JSON.stringify({ filename }),
  });
  await throwForError(res);
  return res.json();
}

export async function retryDocumentIngestion(documentId) {
  const res = await fetch(`${API}/documents/${encodeURIComponent(documentId)}/retry`, {
    method: "POST",
    headers: getHeaders(),
  });
  await throwForError(res);
  return res.json();
}

export async function deleteDocument(documentId) {
  const res = await fetch(`${API}/documents/${encodeURIComponent(documentId)}`, {
    method: "DELETE",
    headers: getHeaders(),
  });
  await throwForError(res);
  return res.json();
}

export async function listKbMembers(kbId) {
  const res = await fetch(`${API}/kb/${kbId}/members`, { headers: getHeaders() });
  await throwForError(res);
  return res.json();
}

export async function addKbMember(kbId, body) {
  const res = await fetch(`${API}/kb/${kbId}/members`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({
      email: body.email,
      role: body.role ?? "viewer",
    }),
  });
  await throwForError(res);
  return res.json();
}

export async function updateKbMemberRole(kbId, memberUserId, role) {
  const res = await fetch(`${API}/kb/${kbId}/members/${memberUserId}`, {
    method: "PATCH",
    headers: getHeaders(),
    body: JSON.stringify({ role }),
  });
  await throwForError(res);
  return res.json();
}

export async function removeKbMember(kbId, memberUserId) {
  const res = await fetch(`${API}/kb/${kbId}/members/${memberUserId}`, {
    method: "DELETE",
    headers: getHeaders(),
  });
  await throwForError(res);
  return res.json();
}

export async function listChatSessions(kbId) {
  const params = new URLSearchParams();
  if (kbId != null) params.set("kb_id", String(kbId));
  const url = params.toString() ? `${API}/chat/sessions?${params}` : `${API}/chat/sessions`;
  const res = await fetch(url, { headers: getHeaders() });
  await throwForError(res);
  return res.json();
}

export async function getChatSession(sessionId, limit = 100) {
  const res = await fetch(`${API}/chat/sessions/${encodeURIComponent(sessionId)}?limit=${limit}`, { headers: getHeaders() });
  await throwForError(res);
  return res.json();
}

export async function deleteChatSession(sessionId) {
  const res = await fetch(`${API}/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
    headers: getHeaders(),
  });
  await throwForError(res);
  return res.json();
}

export async function getChatJob(jobId) {
  const res = await fetch(`${API}/chat/jobs/${encodeURIComponent(jobId)}`, { headers: getHeaders() });
  await throwForError(res);
  return res.json();
}
