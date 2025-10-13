// --- Basis: API-URL aus .env ---
const RAW_BASE = import.meta.env.VITE_API_BASE || "";
// Stelle sicher, dass kein trailing slash am Ende steht
const API_BASE = RAW_BASE.replace(/\/+$/, "");

// --- Fetch-Helper (JSON) ---
async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;

  const res = await fetch(url, {
    method: "GET",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });

  // Text lesen, dann versuchen JSON zu parsen
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    // HTML/Plaintext (z. B. 404-Seite) → sprechenden Fehler werfen
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} – Nicht-JSON Antwort von ${url}`);
    }
    throw new Error(`Unerwartete Antwort vom Server (kein JSON)`);
  }

  if (!res.ok) {
    const detail = data?.detail ? ` – ${data.detail}` : "";
    throw new Error(`HTTP ${res.status}${detail}`);
  }

  return data as T;
}

// ------------------------------------------------------------
//                   Geteilte Typen (Exports)
// ------------------------------------------------------------

// Chat
export type ChatResponse = {
  reply: string;
  ready_for_offer: boolean;
};

// Offer
export type OfferPosition = {
  nr: number;
  name: string;
  menge: number;
  einheit: string;
  epreis: number;
  gesamtpreis?: number;
};
export type OfferResponse = { positions: OfferPosition[]; raw: string };

// PDF
export type PdfRequestPayload = {
  positions: OfferPosition[];
  kunde?: string;
  angebot_nr?: string;
  datum?: string;
};
export type PdfResponse = { pdf_url: string; context: any };

// Wizard
export type WizardUISchema = {
  type: "singleSelect" | "multiSelect" | "number" | "info";
  options?: string[];
  min?: number;
  max?: number;
  step?: number;
};
export type WizardSuggestion = {
  nr: number;
  name: string;
  menge: number;
  einheit: string;
  text: string;
};
export type WizardStepResponse = {
  session_id: string;
  step: string;
  question: string;
  ui: WizardUISchema;
  context_partial: Record<string, any>;
  done: boolean;
  suggestions?: WizardSuggestion[]; // kommt vom Backend, wenn genug Kontext da ist
};
export type WizardFinalizeResult = {
  session_id: string;
  summary: string;
  positions: Array<{ nr: number; name: string; menge: number; einheit: string; text: string }>;
  done: boolean;
};

// Revenue Guard
export type RevenueGuardSuggestion = {
  id: string;
  name: string;
  menge: number | null;
  einheit: string | null;
  reason: string;
  confidence: number; // 0..1
  severity: "low" | "medium" | "high";
  category: string;
};
export type RevenueGuardResponse = {
  passed: boolean;
  missing: RevenueGuardSuggestion[];
  rules_fired: { id: string; label?: string; hit: boolean; explanation?: string }[];
};

// Reset
export type ResetResponse = {
  ok: boolean;
  message?: string;
};

// ------------------------------------------------------------
//                        API-Client
// ------------------------------------------------------------

export const api = {
  base: () => API_BASE,

  // --- Server-Reset: leert Chat-Memory & Wizard-Sessions ---
  reset: () =>
    jsonFetch<ResetResponse>(`/api/session/reset`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  // Chat (LLM1)
  chat: (message: string) =>
    jsonFetch<ChatResponse>(`/api/chat`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  // Angebot (LLM2) – aus Chat-Kontext
  offerFromChat: () =>
    jsonFetch<OfferResponse>(`/api/offer`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  // Angebot (LLM2) – explizite Liste von Produktnamen
  offerFromList: (products: string[]) =>
    jsonFetch<OfferResponse>(`/api/offer`, {
      method: "POST",
      body: JSON.stringify({ products }),
    }),

  // PDF
  pdf: (payload: PdfRequestPayload) =>
    jsonFetch<PdfResponse>(`/api/pdf`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // --- Wizard Endpoints ---
  wizardNext: (sessionId?: string, answers?: Record<string, any>) =>
    jsonFetch<WizardStepResponse>(`/wizard/maler/next`, {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, answers }),
    }),

  wizardFinalize: (sessionId: string) =>
    jsonFetch<WizardFinalizeResult>(`/wizard/maler/finalize`, {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    }),

  // --- Revenue Guard ---
  revenueGuardCheck: (payload: {
    positions: Array<{ nr?: number; name: string; menge: number | null; einheit: string | null; epreis?: number | null }>;
    context?: any;
  }) =>
    jsonFetch<RevenueGuardResponse>(`/revenue-guard/check`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
