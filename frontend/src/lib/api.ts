// --- Basis: API-URL aus .env ---
const RAW_BASE = import.meta.env.VITE_API_BASE || "";
// Stelle sicher, dass kein trailing slash am Ende steht
const API_BASE = RAW_BASE.replace(/\/+$/, "");
const ADMIN_KEY = import.meta.env.VITE_ADMIN_API_KEY || "";
const ADMIN_HEADERS = ADMIN_KEY ? { "X-Admin-Key": ADMIN_KEY } : {};

// Fetch Helper (JSON)
async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;

  const res = await fetch(url, {
    ...init,
    method: init?.method || "GET",
    headers: { 
      "Content-Type": "application/json", 
      ...(init?.headers || {}) 
    },
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

// Catalog
export type CatalogSearchResult = {
  sku: string | null;
  name: string | null;
  unit: string | null;
  pack_sizes: string | null;
  synonyms: string[];
  category: string | null;
  brand: string | null;
  confidence: number | null;
};
export type CatalogSearchResponse = {
  query: string;
  limit: number;
  count: number;
  results: CatalogSearchResult[];
  took_ms: number;
};

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
export type RevenueGuardMaterial = {
  id: string;
  name: string;
  keywords: string[];
  severity: "low" | "medium" | "high";
  category: string;
  reason?: string;
  description?: string;
  einheit?: string | null;
  default_menge?: number | null;
  confidence?: number | null;
  enabled?: boolean;
  editable?: boolean;
  origin?: "builtin" | "custom";
};
export type RevenueGuardMaterialsResponse = {
  items: RevenueGuardMaterial[];
};
export type RevenueGuardMaterialInput = Omit<RevenueGuardMaterial, "editable">;

// Reset
export type ResetResponse = {
  ok: boolean;
  message?: string;
};

// Admin
export type AdminProduct = {
  company_id: string;
  sku: string;
  name: string;
  description?: string | null;
  active: boolean;
  updated_at?: string | null;
};
export type SynonymMap = Record<string, string[]>;

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

  // Catalog search (thin retrieval)
  catalogSearch: (query: string, topK = 5) =>
    jsonFetch<CatalogSearchResponse>(
      `/api/catalog/search?q=${encodeURIComponent(query)}&top_k=${encodeURIComponent(
        Math.max(1, topK),
      )}`,
      { method: "GET" },
    ),

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

  revenueGuardMaterials: () => jsonFetch<RevenueGuardMaterialsResponse>(`/api/revenue-guard/materials`),
  saveRevenueGuardMaterials: (items: RevenueGuardMaterialInput[]) =>
    jsonFetch<RevenueGuardMaterialsResponse>(`/api/revenue-guard/materials`, {
      method: "PUT",
      body: JSON.stringify({ items }),
    }),

  admin: {
    listProducts: (companyId: string, includeDeleted = false) =>
      jsonFetch<AdminProduct[]>(
        `/api/admin/products?company_id=${encodeURIComponent(companyId)}&include_deleted=${includeDeleted ? "1" : "0"}`,
        {
          method: "GET",
          headers: { ...ADMIN_HEADERS },
        },
      ),
    upsertProduct: (
      companyId: string,
      product: { sku: string; name: string; description?: string; active?: boolean },
    ) =>
      jsonFetch<AdminProduct>(`/api/admin/products`, {
        method: "POST",
        headers: { ...ADMIN_HEADERS },
        body: JSON.stringify({
          company_id: companyId,
          sku: product.sku,
          name: product.name,
          description: product.description ?? "",
          active: product.active ?? true,
        }),
      }),
    deleteProduct: (companyId: string, sku: string) =>
      jsonFetch<{ deleted: boolean }>(
        `/api/admin/products/${encodeURIComponent(sku)}?company_id=${encodeURIComponent(companyId)}`,
        {
          method: "DELETE",
          headers: { ...ADMIN_HEADERS },
        },
      ),
    listSynonyms: (companyId: string) =>
      jsonFetch<SynonymMap>(`/api/admin/synonyms?company_id=${encodeURIComponent(companyId)}`, {
        method: "GET",
        headers: { ...ADMIN_HEADERS },
      }),
      addSynonyms: (companyId: string, canon: string, variants: string[]) =>
        jsonFetch<SynonymMap>(`/api/admin/synonyms`, {
          method: "POST",
          headers: { ...ADMIN_HEADERS },
          body: JSON.stringify({
            company_id: companyId,
            canon,
            synonyms: variants,
          }),
        }),
      
      // NEU: Rebuild Index
      rebuildIndex: (companyId: string) =>
        jsonFetch<{ status: string; count: number }>(`/api/admin/index/rebuild`, {
          method: "POST",
          headers: { ...ADMIN_HEADERS },
          body: JSON.stringify({
            company_id: companyId,
          }),
        }),
    },
  };
