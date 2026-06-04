import type { components } from "./api-types";
import { getCSRFToken } from "./csrf";
import type { Item, ItemCreate, ItemUpdate, LoginResponse, User } from "./types";

export type Invoice = components["schemas"]["InvoiceResponse"];
export type InvoiceCreate = components["schemas"]["InvoiceCreate"];
export type InvoiceSummary = {
  count: number;
  by_currency: { currency: string; total: number }[];
};

const BASE = "";
const WRITE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const method = (options?.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options?.headers ?? {}) as Record<string, string>),
  };

  if (WRITE_METHODS.has(method)) {
    const token = getCSRFToken();
    if (token) headers["X-CSRF-Token"] = token;
  }

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// Auth
export async function login(email: string, password: string) {
  return fetchAPI<LoginResponse>("/api/auth/login", {
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

export async function createItem(data: ItemCreate) {
  return fetchAPI<Item>("/api/admin/items", {
    method: "POST",
    body: JSON.stringify(data),
    credentials: "include",
  });
}

export async function updateItem(id: string, data: ItemUpdate) {
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

// Invoices (Admin) — promoted from the Supplier invoice cleaner Flatpack.
export async function listInvoices() {
  return fetchAPI<Invoice[]>("/api/admin/invoices", { credentials: "include" });
}

export async function createInvoice(data: InvoiceCreate) {
  return fetchAPI<Invoice>("/api/admin/invoices", {
    method: "POST",
    body: JSON.stringify(data),
    credentials: "include",
  });
}

export async function getInvoiceSummary() {
  return fetchAPI<InvoiceSummary>("/api/admin/invoices/summary", {
    credentials: "include",
  });
}
