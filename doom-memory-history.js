/**
 * Doom v1.4.4 — browser-side adapter for manual history deletion and memory editing.
 *
 * Important: after PATCH, always replace the local memory with the JSON returned
 * by the server. Do not only mutate the input form or a stale local copy.
 */

export async function deleteDoomConversation(sessionId, confirmationToken = null) {
  const response = await fetch(`/api/conversations/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmation_token: confirmationToken }),
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.detail || payload.message || "history_delete_failed");
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

export async function editDoomMemory(memoryId, sessionId, patch, confirmationToken = null) {
  const body = {
    ...patch,
    confirmation_token: confirmationToken,
  };

  const response = await fetch(
    `/api/memories/${encodeURIComponent(memoryId)}?session_id=${encodeURIComponent(sessionId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.detail || payload.message || "memory_edit_failed");
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  // Return the canonical server state. The UI should replace its old memory object.
  return payload;
}

export function replaceMemoryInState(memories, savedMemory) {
  const index = memories.findIndex((memory) => memory.id === savedMemory.id);
  if (index === -1) return [...memories, savedMemory];
  const next = memories.slice();
  next[index] = savedMemory;
  return next;
}
