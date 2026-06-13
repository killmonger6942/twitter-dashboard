const BASE = import.meta.env.VITE_API_URL || '/api';

const TOKEN_KEY = 'dashboard_token';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${BASE}${path}`, {
    headers,
    ...options,
  });

  if (res.status === 401) {
    clearToken();
    window.location.reload();
    throw new Error('Session expired');
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export interface Account {
  id: string;
  username: string;
  display_name: string;
  persona_id: string | null;
  is_logged_in: boolean;
  is_active: boolean;
  created_at: string;
}

export interface Persona {
  id: string;
  name: string;
  tone: string;
  topics: string[];
  style_guide: string;
  posting_frequency: string;
  example_tweets: string[];
  system_prompt: string;
  created_at: string;
}

export interface ContentItem {
  id: string;
  account_id: string;
  content_type: string;
  status: string;
  body: string;
  target_tweet_url: string | null;
  scheduled_for: string | null;
  posted_at: string | null;
  error_message: string | null;
  screenshot_path: string | null;
  created_at: string;
}

export const api = {
  auth: {
    login: (username: string, password: string) =>
      request<{ token: string }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      }),
    me: () => request<{ username: string }>('/auth/me'),
  },

  accounts: {
    list: () => request<Account[]>('/accounts'),
    add: (username: string) => request<Account>('/accounts', {
      method: 'POST',
      body: JSON.stringify({ username }),
    }),
    login: (id: string) => request<{ message: string }>(`/accounts/${id}/login`, {
      method: 'POST',
    }),
    confirmLogin: (id: string) => request<{ message: string }>(`/accounts/${id}/confirm-login`, {
      method: 'POST',
    }),
    screenshot: (id: string) => request<{ screenshot: string }>(`/accounts/${id}/screenshot`),
    delete: (id: string) => request<{ message: string }>(`/accounts/${id}`, {
      method: 'DELETE',
    }),
  },

  personas: {
    list: () => request<Persona[]>('/personas'),
    create: (data: Omit<Persona, 'id' | 'system_prompt' | 'created_at'>) =>
      request<Persona>('/personas', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    update: (id: string, data: Omit<Persona, 'id' | 'system_prompt' | 'created_at'>) =>
      request<Persona>(`/personas/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      }),
    assign: (personaId: string, accountId: string) =>
      request<{ message: string }>(`/personas/${personaId}/assign/${accountId}`, {
        method: 'POST',
      }),
    delete: (id: string) => request<{ message: string }>(`/personas/${id}`, {
      method: 'DELETE',
    }),
    generate: (description: string) =>
      request<{ name: string; tone: string; topics: string[]; style_guide: string; posting_frequency: string; example_tweets: string[] }>('/personas/generate', {
        method: 'POST',
        body: JSON.stringify({ description }),
      }),
  },

  content: {
    list: (params?: { account_id?: string; status?: string }) => {
      const query = new URLSearchParams();
      if (params?.account_id) query.set('account_id', params.account_id);
      if (params?.status) query.set('status', params.status);
      const qs = query.toString();
      return request<ContentItem[]>(`/content${qs ? `?${qs}` : ''}`);
    },
    create: (data: { account_id: string; content_type?: string; body: string; target_tweet_url?: string }) =>
      request<ContentItem>('/content', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    approve: (id: string) => request<ContentItem>(`/content/${id}/approve`, {
      method: 'PATCH',
    }),
    post: (id: string) => request<ContentItem & { computer_use_result?: any }>(`/content/${id}/post`, {
      method: 'POST',
    }),
    generate: (account_id: string, direction?: string, count?: number) =>
      request<{ drafts: string[]; persona_name: string }>('/content/generate', {
        method: 'POST',
        body: JSON.stringify({ account_id, direction: direction || undefined, count: count || 3 }),
      }),
    delete: (id: string) => request<{ message: string }>(`/content/${id}`, {
      method: 'DELETE',
    }),
  },

  analytics: {
    summary: (account_id: string, days = 7) =>
      request<{ days: number; actions: Record<string, { total: number; done: number; failed: number }> }>(
        `/analytics/summary?account_id=${account_id}&days=${days}`
      ),
    timeline: (account_id: string, days = 7) =>
      request<Array<Record<string, any>>>(`/analytics/timeline?account_id=${account_id}&days=${days}`),
    successRate: (account_id: string, days = 7) =>
      request<Array<{ action_type: string; done: number; failed: number }>>(
        `/analytics/success-rate?account_id=${account_id}&days=${days}`
      ),
    followCampaign: (account_id: string) =>
      request<{ total: number; followed: number; remaining: number; failed: number; progress: number; counts: Record<string, number> }>(
        `/analytics/follow-campaign?account_id=${account_id}`
      ),
    recent: (account_id: string, limit = 20) =>
      request<Array<{ action_type: string; status: string; time: string | null; category: string | null; error_message: string | null; source: string }>>(
        `/analytics/recent?account_id=${account_id}&limit=${limit}`
      ),
    profile: (account_id: string) =>
      request<{ current: { followers: number; following: number; tweets: number }; growth: Record<string, number>; history: Array<{ date: string; followers: number; following: number; tweets: number }> }>(
        `/analytics/profile?account_id=${account_id}`
      ),
    snapshotProfile: (account_id: string) =>
      request<{ date: string; followers: number; following: number; tweets: number }>(
        `/analytics/profile/snapshot?account_id=${account_id}`,
        { method: 'POST' }
      ),
  },

  behavior: {
    start: (account_id: string) =>
      request<any>(`/behavior/start?account_id=${account_id}`, { method: 'POST' }),
    stop: (account_id: string) =>
      request<any>(`/behavior/stop?account_id=${account_id}`, { method: 'POST' }),
    status: (account_id: string) =>
      request<any>(`/behavior/status?account_id=${account_id}`),
    followCampaignStatus: (account_id: string) =>
      request<any>(`/behavior/follow-campaign/status?account_id=${account_id}`),
    followCampaignStart: (account_id: string) =>
      request<any>(`/behavior/follow-campaign/start?account_id=${account_id}`, { method: 'POST' }),
    followCampaignStop: (account_id: string) =>
      request<any>(`/behavior/follow-campaign/stop?account_id=${account_id}`, { method: 'POST' }),
  },
};
