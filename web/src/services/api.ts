import { config } from '../config';
import { getAuthToken } from './auth';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Child {
  childId: string;
  displayName: string;
  parentId: string;
  registeredAt: string;
}

export interface Message {
  conversationId: string;
  timestamp: string;
  senderId: string;
  senderType: 'parent' | 'child';
  content: string;
}

export interface ScreenshotRequest {
  requestId: string;
  childId: string;
  status: string;
  url?: string;
}

export interface GenerateCodeResponse {
  code: string;
  expiresAt: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const baseUrl = config.apiUrl;

async function authHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  if (config.localDev) {
    headers['X-Parent-Id'] = 'dev-parent-001';
  } else {
    const token = await getAuthToken();
    headers['Authorization'] = `Bearer ${token}`;
  }

  return headers;
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = await authHeaders();
  const res = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: { ...headers, ...(options.headers as Record<string, string>) },
  });

  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`API ${res.status}: ${body || res.statusText}`);
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Children
// ---------------------------------------------------------------------------

export async function getChildren(): Promise<Child[]> {
  return request<Child[]>('/api/children');
}

export async function generateCode(
  childName: string
): Promise<GenerateCodeResponse> {
  return request<GenerateCodeResponse>('/api/children/generate-code', {
    method: 'POST',
    body: JSON.stringify({ childName }),
  });
}

// ---------------------------------------------------------------------------
// Messages
// ---------------------------------------------------------------------------

export async function getMessages(
  childId: string,
  since?: string
): Promise<Message[]> {
  const params = new URLSearchParams({ childId });
  if (since) {
    params.set('since', since);
  }
  return request<Message[]>(`/api/messages?${params.toString()}`);
}

export interface SendMessageResponse {
  messageId: string;
  conversationId: string;
}

export async function sendMessage(
  childId: string,
  content: string
): Promise<SendMessageResponse> {
  return request<SendMessageResponse>('/api/messages', {
    method: 'POST',
    body: JSON.stringify({ childId, content }),
  });
}

// ---------------------------------------------------------------------------
// Screenshots
// ---------------------------------------------------------------------------

export async function requestScreenshot(
  childId: string
): Promise<ScreenshotRequest> {
  return request<ScreenshotRequest>('/api/screenshots/request', {
    method: 'POST',
    body: JSON.stringify({ childId }),
  });
}

export async function getScreenshot(
  requestId: string,
  childId: string
): Promise<ScreenshotRequest> {
  const params = new URLSearchParams({ childId });
  return request<ScreenshotRequest>(
    `/api/screenshots/${requestId}?${params.toString()}`
  );
}
