import type { Item, User } from "./types";

const BASE = "";

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// Auth
export async function login(email: string, password: string) {
  return fetchAPI<{ message: string }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
    credentials: "include",
  });
}

export async function logout() {
  return fetchAPI("/api/auth/logout", {
    method: "POST",
    credentials: "include",
  });
}

export async function checkAuth() {
  return fetchAPI<User>("/api/auth/me", {
    credentials: "include",
  });
}

// Items (Admin)
export async function getItems() {
  return fetchAPI<Item[]>("/api/admin/items", { credentials: "include" });
}

export async function createItem(data: { name: string; description?: string }) {
  return fetchAPI<Item>("/api/admin/items", {
    method: "POST",
    body: JSON.stringify(data),
    credentials: "include",
  });
}

export async function updateItem(id: string, data: Partial<Item>) {
  return fetchAPI<Item>(`/api/admin/items/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
    credentials: "include",
  });
}

export async function deleteItem(id: string) {
  return fetchAPI(`/api/admin/items/${id}`, {
    method: "DELETE",
    credentials: "include",
  });
}

// Items (Public)
export async function getPublicItems() {
  return fetchAPI<Item[]>("/api/public/items");
}
