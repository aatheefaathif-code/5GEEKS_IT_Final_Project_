export type Locale = "English" | "Sinhala" | "Tamil";

export type FamilyUser = {
  id: string;
  email: string;
  role: "parent" | "teacher";
  full_name: string | null;
};

export type Student = {
  id: string;
  display_name: string;
  grade: number;
};

export type SourceReference = {
  textbook_title: string | null;
  source_file: string;
  pdf_page_number: number;
  chapter: string | null;
  lesson: string | null;
};

export function getApiBaseUrl(): string {
  return (import.meta.env.VITE_API_BASE_URL ?? "/api/v1").replace(/\/+$/, "");
}

export async function apiRequest(
  path: string,
  token: string | null,
  init: RequestInit = {},
): Promise<unknown> {
  const headers = new Headers(init.headers);
  if (init.body) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${getApiBaseUrl()}${path}`, { ...init, headers });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof payload.detail === "string"
        ? payload.detail
        : `Request failed (${response.status}).`;
    throw new Error(detail);
  }
  return payload;
}

export function isStudent(value: unknown): value is Student {
  return (
    typeof value === "object" &&
    value !== null &&
    "id" in value &&
    typeof value.id === "string" &&
    "display_name" in value &&
    typeof value.display_name === "string" &&
    "grade" in value &&
    typeof value.grade === "number"
  );
}
