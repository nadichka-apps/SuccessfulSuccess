import { signOut } from "aws-amplify/auth"

import { getAccessToken } from "@/lib/auth"
import type {
  ApiErrorBody,
  ApiErrorDetail,
  Meeting,
  MeetingCreateInput,
  MeetingList,
  UserProfile,
} from "@/lib/types"

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

export class ApiError extends Error {
  readonly code: string
  readonly details: ApiErrorDetail[]
  readonly status: number

  constructor(status: number, code: string, message: string, details: ApiErrorDetail[]) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.code = code
    this.details = details
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getAccessToken()
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
      cache: "no-store",
    })
  } catch {
    throw new ApiError(0, "network_error", "Could not reach the meetings API.", [])
  }

  // The session is gone or was revoked: sign out, and the auth guard sends the
  // user back to the login page.
  if (response.status === 401) {
    void signOut()
  }

  if (response.status === 204) {
    return undefined as T
  }

  const text = await response.text()
  const payload = text ? JSON.parse(text) : null

  if (!response.ok) {
    const body = payload as ApiErrorBody | null
    throw new ApiError(
      response.status,
      body?.error?.code ?? "internal_error",
      body?.error?.message ?? `Request failed with status ${response.status}.`,
      body?.error?.details ?? [],
    )
  }

  return payload as T
}

export function listMeetings(params: { date?: string; q?: string } = {}) {
  const search = new URLSearchParams()
  if (params.date) search.set("date", params.date)
  if (params.q) search.set("q", params.q)
  const query = search.toString()
  return request<MeetingList>(`/api/v1/meetings${query ? `?${query}` : ""}`)
}

export function getMeeting(id: string) {
  return request<Meeting>(`/api/v1/meetings/${id}`)
}

export function createMeeting(payload: MeetingCreateInput) {
  return request<Meeting>("/api/v1/meetings", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function updateMeeting(id: string, payload: MeetingCreateInput) {
  return request<Meeting>(`/api/v1/meetings/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}

export function deleteMeeting(id: string) {
  return request<void>(`/api/v1/meetings/${id}`, { method: "DELETE" })
}

export function getMe() {
  return request<UserProfile>("/api/v1/me")
}

/** Call the isolated parser Lambda. This endpoint can suggest data but cannot save it. */
export async function parseAgenda(text: string, signal: AbortSignal) {
  const token = await getAccessToken()
  if (!token) throw new ApiError(401, "unauthorized", "Sign in to parse an agenda.", [])
  const endpoint = process.env.NEXT_PUBLIC_AGENDA_PARSER_URL
  if (!endpoint) throw new ApiError(503, "parser_unconfigured", "Agenda parsing is not configured.", [])
  let response: Response
  const now = new Date()
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`
  try {
    response = await fetch(endpoint, {
      method: "POST", signal,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ text, today, tz: Intl.DateTimeFormat().resolvedOptions().timeZone }),
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error
    throw new ApiError(0, "network_error", "Could not reach the agenda parser.", [])
  }
  const payload = await response.json()
  if (!response.ok) throw new ApiError(response.status, "parse_error", payload.error ?? "Could not parse this agenda.", [])
  return payload as { agenda: { title: string | null; starts_at: string | null; duration_minutes: number | null; items: { topic: string; owner: string | null; minutes: number | null }[]; action_items: { task: string; owner: string | null; due: string | null }[]; language: string }; model: string; prompt_version: string }
}

/** Stores the profile from the ID token in the users table; call after signing in. */
export function syncMe(idToken: string) {
  return request<UserProfile>("/api/v1/me/sync", {
    method: "POST",
    body: JSON.stringify({ id_token: idToken }),
  })
}
