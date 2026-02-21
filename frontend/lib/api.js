const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function getHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("ragnetic_token");
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
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

export async function uploadFile(file, kbId) {
  const form = new FormData();
  form.append("file", file);
  const url = kbId != null ? `${API}/upload/?kb_id=${kbId}` : `${API}/upload/`;
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
    }),
  });
  await throwForError(res);
  return res.json();
}

export async function documentStatus(id) {
  const res = await fetch(`${API}/documents/${id}/status`, { headers: getHeaders() });
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
