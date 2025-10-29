/// <reference types="vitest/globals" />

const setupApi = async () => {
  vi.resetModules();
  const { api } = await import("./api");
  return api;
};

describe("api helper", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.unstubAllEnvs();
  });

  it("sanitizes the configured base URL", async () => {
    vi.stubEnv("VITE_API_BASE", "https://example.com/nested//");
    const api = await setupApi();

    expect(api.base()).toBe("https://example.com/nested");
  });

  it("falls back to an empty base URL when none is provided", async () => {
    vi.stubEnv("VITE_API_BASE", "");
    const api = await setupApi();

    expect(api.base()).toBe("");
  });

  it("posts chat messages to the backend with JSON payload", async () => {
    vi.stubEnv("VITE_API_BASE", "https://example.com");
    const api = await setupApi();

    const responsePayload = { reply: "Hi there", ready_for_offer: true };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: () => Promise.resolve(JSON.stringify(responsePayload)),
    }) as unknown as typeof fetch;

    const result = await api.chat("Hello backend!");

    expect(globalThis.fetch).toHaveBeenCalledWith("https://example.com/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "Hello backend!" }),
    });
    expect(result).toEqual(responsePayload);
  });

  it("throws a descriptive error when the server responds with JSON error payloads", async () => {
    vi.stubEnv("VITE_API_BASE", "https://example.com");
    const api = await setupApi();

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      text: () => Promise.resolve(JSON.stringify({ detail: "Not found" })),
    }) as unknown as typeof fetch;

    await expect(api.offerFromChat()).rejects.toThrow("HTTP 404 – Not found");
  });

  it("throws when the backend answers with non-JSON data", async () => {
    vi.stubEnv("VITE_API_BASE", "https://example.com");
    const api = await setupApi();

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: () => Promise.resolve("not-json"),
    }) as unknown as typeof fetch;

    await expect(api.reset()).rejects.toThrow("Unerwartete Antwort vom Server (kein JSON)");
  });
});
