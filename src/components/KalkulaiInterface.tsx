import { useState, useRef, useEffect } from "react";
import { Mic, Camera, MessageSquare, ArrowUp, Edit, Save, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import WizardMaler, { WizardFinalizeResult } from "@/components/WizardMaler";

import type {
  RevenueGuardResponse,
  RevenueGuardSuggestion,
  WizardStepResponse,
} from "@/lib/api";

// ---- Einheitliche Kartenhöhe (hier zentral ändern) ----
const CARD_HEIGHT = "h-[50dvh]"; // Beispiele: "h-[640px]" | "h-[70vh]" | "h-[calc(100dvh-200px)]"

// ---- UI Types ----
type UiSection = {
  id?: string;
  ts?: number;
  title: string;
  subtitle?: string;
  description?: string | null;
  source: "chat" | "wizard" | "system";
  items?: Array<{
    position: string;
    description: string;
    quantity: string;
    unit: string;
    ep: string;
    gp: string;
  }>;
};

// ---- Eingabe-Historie (links) ----
type InputEntry = { id: string; text: string; ts: number };

const KalkulaiInterface = () => {
  const [activeTab, setActiveTab] = useState<"angebot" | "rechnung">("angebot");
  const [activeNav, setActiveNav] = useState<"erstellen" | "bibliothek">("erstellen");
  const [leftMode, setLeftMode] = useState<"chat" | "wizard">("chat");
  const [rightFilter, setRightFilter] = useState<"all" | "wizard" | "chat">("all");

  const [inputText, setInputText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isMakingPdf, setIsMakingPdf] = useState(false);

  // Angebotspositionen (final-relevant: PDF, Preise)
  const [positions, setPositions] = useState<
    Array<{ nr: number; name: string; menge: number; einheit: string; epreis: number; gesamtpreis?: number }>
  >([]);

  // Rechte Output-Box (Chat/Wizard/System)
  const [sections, setSections] = useState<UiSection[]>([]);

  // Revenue Guard + Wizard-Kontext
  const [guard, setGuard] = useState<RevenueGuardResponse | null>(null);
  const [wizardCtx, setWizardCtx] = useState<any>(null);

  // ---- Linke Historie + Autoscroll ----
  const [inputs, setInputs] = useState<InputEntry[]>([]);
  const leftScrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    leftScrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [inputs]);

  // ---- Backend-Reset beim Mount + lokaler Reset ----
  useEffect(() => {
    (async () => {
      try {
        await api.reset(); // leert Chat-Memory & Wizard-Sessions im Backend
      } catch (e) {
        // optional: System-Hinweis rechts anzeigen
        setSections((prev) => [
          {
            id: String(Date.now() + Math.random()),
            ts: Date.now(),
            title: "Hinweis",
            subtitle: "Server-Reset",
            description: "Konnte den Server-Reset nicht ausführen. Bitte Seite neu laden oder später erneut versuchen.",
            source: "system",
          },
          ...prev,
        ]);
      } finally {
        // lokalen Zustand auch leeren
        setPositions([]);
        setSections([]);
        setGuard(null);
        setInputs([]);
        setInputText("");
      }
    })();
  }, []);

  // Helper: Section bauen (mit id/ts)
  const mkSection = (s: Omit<UiSection, "id" | "ts">): UiSection => ({
    id: String(Date.now() + Math.random()),
    ts: Date.now(),
    ...s,
  });

  const handleSend = async () => {
    const text = inputText.trim();
    if (!text || isLoading) return;
    setInputs((prev) => [...prev, { id: crypto.randomUUID(), text, ts: Date.now() }]);
  
    setIsLoading(true);
    try {
      const chat = await api.chat(text);
      const replyText =
        typeof chat?.reply === "string"
          ? chat.reply
          : (chat?.reply as any)?.message
          ? String((chat.reply as any).message)
          : JSON.stringify(chat?.reply ?? chat ?? "", null, 2);
  
      setSections((prev) => [
        mkSection({
          title: "Chat-Antwort",
          subtitle: "Erste Analyse",
          description: replyText,
          source: "chat",
        }),
        ...prev,
      ]);
  
      // NEU: auch Nutzer-Text auf Bestätigung prüfen
      const textLower = text.toLowerCase();
      const userLooksConfirmed = /(passen\s*so|stimmen\s*so|best[aä]tig|freigeben|erstelle\s+(?:das\s+)?angebot)/i.test(textLower);
      const replyLooksConfirmed = /status\s*:\s*best(ae|ä)tigt/i.test(replyText) ||
        /angebot wird (jetzt )?erstellt/i.test(replyText) ||
        /mengen übernommen/i.test(replyText);
  
      if (chat?.ready_for_offer || userLooksConfirmed || replyLooksConfirmed) {
        try {
          const offer = await api.offerFromChat();
          if (offer?.positions?.length) {
            setPositions(offer.positions);
            setSections((prev) => [
              mkSection({
                title: "Bestätigung erhalten",
                subtitle: "Angebot erzeugt",
                description: `Es wurden **${offer.positions.length} Positionen** übernommen. Du kannst jetzt das PDF erstellen.`,
                source: "system",
              }),
              ...prev,
            ]);
            await runRevenueGuard();
          } else {
            setSections((prev) => [
              mkSection({
                title: "Hinweis",
                subtitle: "Keine Positionen erkannt",
                description:
                  "Die Bestätigung wurde erkannt, aber es konnten keine Katalogpositionen gemappt werden. Bitte formuliere die Produkte konkreter (z. B. „Dispersionsfarbe, 10 L“, „Tiefgrund, 10 L“, „Abdeckfolie 4×5 m“).",
                source: "system",
              }),
              ...prev,
            ]);
          }
        } catch (e: any) {
          setSections((prev) => [
            mkSection({
              title: "Fehler",
              subtitle: "Angebotserstellung",
              description: String(e?.message ?? "Unbekannter Fehler bei /api/offer"),
              source: "system",
            }),
            ...prev,
          ]);
        }
      }
    } catch (e: any) {
      const err = String(e?.message ?? "Unbekannter Fehler");
      setSections((prev) => [
        mkSection({
          title: "Fehler",
          subtitle: "Chat fehlgeschlagen",
          description: err,
          source: "system",
        }),
        ...prev,
      ]);
    } finally {
      setIsLoading(false);
      setInputText("");
    }
  };
  


  // ---------- PDF (nur wenn positions vorhanden) ----------
  const handleMakePdf = async () => {
    if (isMakingPdf) return;
    if (positions.length === 0) {
      setSections((prev) => [
        mkSection({
          title: "Hinweis",
          subtitle: "PDF nicht möglich",
          description: "Es sind noch keine Positionen vorhanden. Bitte zuerst über Chat oder Wizard Positionen ermitteln.",
          source: "system",
        }),
        ...prev,
      ]);
      return;
    }

    setIsMakingPdf(true);
    try {
      const res = await api.pdf({
        positions,
        kunde: "Bau GmbH\nHauptstraße 1\n12345 Stadt",
      });

      const fullUrl = `${import.meta.env.VITE_API_BASE}${res.pdf_url}`;
      await forceDownload(fullUrl, "Angebot.pdf");
    } catch (e: any) {
      setSections((prev) => [
        mkSection({
          title: "Fehler",
          subtitle: "PDF fehlgeschlagen",
          description: String(e?.message ?? "Unbekannter Fehler"),
          source: "system",
        }),
        ...prev,
      ]);
    } finally {
      setIsMakingPdf(false);
    }
  };

  async function forceDownload(url: string, filename = "Angebot.pdf") {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`Download fehlgeschlagen (HTTP ${r.status})`);
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      URL.revokeObjectURL(a.href);
      a.remove();
    }, 1000);
  }

  // ---------- Wizard: Progress (Live-Vorschau nur rechts) ----------
  const handleWizardProgress = (res: WizardStepResponse) => {
    setWizardCtx(res?.context_partial || null);

    const suggs = Array.isArray(res?.suggestions) ? res.suggestions : [];
    if (suggs.length === 0) {
      setSections((prev) => prev.filter((s) => !(s.source === "wizard" && s.title === "Live-Vorschau")));
      return;
    }

    const previewMd = suggs
      .map((p) => {
        const qty = typeof p.menge === "number" && !Number.isNaN(p.menge) ? p.menge : 0;
        const unit = p.einheit ?? "";
        const extra = p.text ? `\n  - ${p.text}` : "";
        return `- **${p.name}** – ${qty} ${unit}${extra}`;
      })
      .join("\n");

    setSections((prev) => {
      const withoutLive = prev.filter((s) => !(s.source === "wizard" && s.title === "Live-Vorschau"));
      return [
        mkSection({
          title: "Live-Vorschau",
          subtitle: "Mengen & Materialien (ohne Preise)",
          description: previewMd,
          source: "wizard",
        }),
        ...withoutLive,
      ];
    });
  };

  // ---------- Wizard: Finalize ----------
  const handleWizardFinalize = async (wz: WizardFinalizeResult) => {
    const matLines = wz.positions
      .map((p) => `- name=${p.name}, menge=${Number(p.menge)}, einheit=${p.einheit}`)
      .join("\n");

    const syntheticMessage =
      `Projektassistent Wizard abgeschlossen.\n` +
      `Zusammenfassung: ${wz.summary}\n` +
      `---\n` +
      `status: bestätigt\n` +
      `materialien:\n${matLines}\n` +
      `---`;

    try {
      await api.chat(syntheticMessage);
    } catch {
      /* soft fail ok */
    }

    let mappedPositions: Array<{ nr: number; name: string; menge: number; einheit: string; epreis: number; gesamtpreis?: number }> = [];
    try {
      const names = wz.positions.map((p) => p.name).filter(Boolean);
      if (names.length) {
        const offer = await api.offerFromList(names);
        if (offer?.positions?.length) mappedPositions = offer.positions;
      }
    } catch {
      /* noop */
    }

    if (!mappedPositions.length) {
      mappedPositions = wz.positions.map((p) => ({
        nr: p.nr,
        name: p.name,
        menge: Number(p.menge) || 0,
        einheit: p.einheit,
        epreis: 0,
      }));
      setSections((prev) => [
        mkSection({
          title: "Hinweis",
          subtitle: "Automatische Katalog-Zuordnung",
          description:
            "Konnte nicht alle Positionen automatisch zuordnen. Du kannst trotzdem ein PDF erzeugen; Preise sind zunächst 0.",
          source: "system",
        }),
        ...prev,
      ]);
    }

    setPositions(mappedPositions);

    setSections((prev) => {
      const withoutLive = prev.filter((s) => !(s.source === "wizard" && s.title === "Live-Vorschau"));
      return [
        mkSection({
          title: "Wizard abgeschlossen",
          subtitle: "Zusammenfassung",
          description: `**${wz.summary}**\n\nEs wurden ${wz.positions.length} Materialpositionen vorbereitet.`,
          source: "wizard",
        }),
        ...withoutLive,
      ];
    });

    await runRevenueGuard(wizardCtx);
    setLeftMode("chat");
  };

  // ---------- Revenue Guard ----------
  async function runRevenueGuard(optionalCtx?: any) {
    if (!positions.length) {
      setGuard(null);
      return;
    }
    try {
      const resp = await api.revenueGuardCheck({
        positions: positions.map((p) => ({
          nr: p.nr,
          name: p.name,
          menge: p.menge,
          einheit: p.einheit,
          epreis: p.epreis,
        })),
        context: optionalCtx || wizardCtx || {},
      });
      setGuard(resp);
    } catch {
      setGuard(null);
    }
  }

  async function addSuggestion(sug: RevenueGuardSuggestion) {
    let mapped = null as any;
    try {
      const offer = await api.offerFromList([sug.name]);
      if (offer?.positions?.[0]) mapped = offer.positions[0];
    } catch {
      /* noop */
    }

    const newPos =
      mapped ??
      ({
        nr: positions.length + 1,
        name: sug.name,
        menge: Number(sug.menge) || 0,
        einheit: sug.einheit || "",
        epreis: 0,
      } as const);

    setPositions((prev) => [...prev, newPos]);
    // Nach Hinzufügen direkt erneut prüfen
    await runRevenueGuard();
  }

  // ---------- Sections filter ----------
  const filteredSections = sections.filter((s) => (rightFilter === "all" ? true : s.source === rightFilter));

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="bg-card border-b border-border px-6 py-4">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <img
                src="/lovable-uploads/c512bb54-21ad-4d03-a77e-daa5f6a25264.png"
                alt="KalkulAI Logo"
                className="h-16 w-auto"
              />
            </div>
            <div className="flex items-center gap-8">
              <button
                onClick={() => setActiveNav("erstellen")}
                className={`text-sm font-medium transition-colors ${
                  activeNav === "erstellen" ? "text-foreground font-bold" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Erstellen
              </button>
              <button
                onClick={() => setActiveNav("bibliothek")}
                className={`text-sm font-medium transition-colors ${
                  activeNav === "bibliothek" ? "text-foreground font-bold" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Bibliothek
              </button>

              {/* Chat <-> Wizard Umschalter */}
              <div className="ml-6 flex items-center gap-2">
                <button
                  onClick={() => setLeftMode("chat")}
                  className={`text-sm px-3 py-1 rounded-full ${
                    leftMode === "chat"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground hover:bg-muted/80"
                  }`}
                >
                  Chat
                </button>
                <button
                  onClick={() => setLeftMode("wizard")}
                  className={`text-sm px-3 py-1 rounded-full ${
                    leftMode === "wizard"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground hover:bg-muted/80"
                  }`}
                >
                  Wizard
                </button>
              </div>
            </div>
          </div>

          {/* Tab Toggle */}
          <div className="flex items-center justify-center gap-2">
            <button
              onClick={() => setActiveTab("angebot")}
              className={`px-6 py-2 rounded-full text-sm font-medium transition-all ${
                activeTab === "angebot" ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/80"
              }`}
            >
              Angebot
            </button>
            <button
              onClick={() => setActiveTab("rechnung")}
              className={`px-6 py-2 rounded-full text-sm font-medium transition-all ${
                activeTab === "rechnung" ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/80"
              }`}
            >
              Rechnung
            </button>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="max-w-7xl mx-auto p-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left */}
          <div className="space-y-4">
            <Card className={`relative p-6 ${CARD_HEIGHT} shadow-soft border border-border flex flex-col`}>
              {leftMode === "chat" ? (
                <>
                  {/* Historie deiner Eingaben */}
                  <div className="flex-1 overflow-y-auto pr-2 space-y-4">
                    {inputs.map((m) => (
                      <div key={m.id} className="flex justify-end">
                        <div className="max-w-[80%] rounded-2xl px-4 py-2 text-sm shadow-sm bg-primary text-primary-foreground">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {m.text}
                          </ReactMarkdown>
                          <div className="text-[10px] opacity-70 mt-1 text-right">
                            {new Date(m.ts).toLocaleTimeString()}
                          </div>
                        </div>
                      </div>
                    ))}
                    <div ref={leftScrollRef} />
                  </div>

                  {/* Composer */}
                  <div className="mt-2 border rounded-lg p-2 bg-background min-h-[56px]">
                    <textarea
                      value={inputText}
                      onChange={(e) => setInputText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          handleSend();
                        }
                      }}
                      placeholder="Nachricht eingeben …"
                      className="w-full h-8 min-h-0 resize-none border-none outline-none text-sm leading-5 placeholder:text-muted-foreground bg-transparent p-0"
                      rows={1}
                    />
                    <div className="flex items-center justify-between pt-1">
                      <div className="flex items-center gap-1.5">
                        <Button size="icon" variant="ghost" className="h-8 w-8">
                          <MessageSquare className="w-4 h-4" />
                        </Button>
                        <Button size="icon" variant="ghost" className="h-8 w-8">
                          <Mic className="w-4 h-4" />
                        </Button>
                        <Button size="icon" variant="ghost" className="h-8 w-8">
                          <Camera className="w-4 h-4" />
                        </Button>
                      </div>
                      <Button onClick={handleSend} disabled={isLoading || !inputText.trim()} className="h-9 px-3 rounded-full">
                        <ArrowUp className="w-4 h-4 mr-1" />
                        Senden
                      </Button>
                    </div>
                  </div>
                </>
              ) : (
                <div className="max-w-xl mx-auto flex-1">
                  <WizardMaler onFinalize={handleWizardFinalize} onProgress={handleWizardProgress} />
                </div>
              )}
            </Card>
          </div>

          {/* Right */}
          <div className="space-y-4">
            <Card className={`p-6 ${CARD_HEIGHT} shadow-soft border border-border flex flex-col`}>
              {/* Kopf */}
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold text-foreground mb-1">Ergebnis</h2>
                  <p className="text-sm text-muted-foreground">Chat + Wizard</p>
                </div>
                <div className="flex items-center gap-2">
                  <div className="hidden md:flex items-center gap-1 mr-2">
                    <button
                      className={`text-xs px-2 py-1 rounded-full ${
                        rightFilter === "all" ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60"
                      }`}
                      onClick={() => setRightFilter("all")}
                    >
                      Alle
                    </button>
                    <button
                      className={`text-xs px-2 py-1 rounded-full ${
                        rightFilter === "chat" ? "bg-emerald-100 text-emerald-700" : "text-muted-foreground hover:bg-muted/60"
                      }`}
                      onClick={() => setRightFilter("chat")}
                    >
                      Chat
                    </button>
                    <button
                      className={`text-xs px-2 py-1 rounded-full ${
                        rightFilter === "wizard" ? "bg-blue-100 text-blue-700" : "text-muted-foreground hover:bg-muted/60"
                      }`}
                      onClick={() => setRightFilter("wizard")}
                    >
                      Wizard
                    </button>
                  </div>
                  <Button
                    variant="outline"
                    disabled={isMakingPdf || positions.length === 0}
                    onClick={handleMakePdf}
                    title={positions.length === 0 ? "Keine Positionen vorhanden" : "PDF erstellen"}
                  >
                    <FileText className="w-4 h-4 mr-2" />
                    {isMakingPdf ? "PDF…" : "PDF erstellen"}
                  </Button>
                </div>
              </div>

              {/* Scrollbarer Content-Bereich */}
              <div className="flex-1 overflow-y-auto">
                {isLoading && sections.length === 0 && (!guard || guard.missing.length === 0) ? (
                  <div className="flex items-center justify-center h-full">
                    <div className="text-center">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
                      <p className="text-muted-foreground">Analysiere Eingabe…</p>
                    </div>
                  </div>
                ) : sections.length > 0 || (guard && guard.missing.length > 0) ? (
                  <>
                    {/* Revenue Guard Block */}
                    {guard && guard.missing.length > 0 && (
                      <div className="mb-6 border border-blue-200 bg-blue-50 rounded p-4">
                        <div className="flex items-center justify-between mb-2">
                          <h3 className="font-semibold text-blue-900">Vergessene Posten (Wächter)</h3>
                          <span className="text-xs text-blue-700">{guard.missing.length} Vorschlag/Vorschläge</span>
                        </div>
                        <ul className="space-y-2">
                          {guard.missing.map((m) => (
                            <li key={m.id} className="flex items-start justify-between gap-3">
                              <div>
                                <div className="font-medium">
                                  {m.name}{" "}
                                  <span className="text-xs text-muted-foreground">({m.category})</span>
                                </div>
                                <div className="text-xs text-muted-foreground">
                                  {m.menge ?? "—"} {m.einheit ?? ""} &middot; {m.reason}
                                </div>
                              </div>
                              <Button size="sm" variant="outline" onClick={() => addSuggestion(m)}>
                                Übernehmen
                              </Button>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Sections */}
                    {filteredSections.map((section) => (
                      <div key={section.id} className="mb-8">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="text-lg font-semibold text-foreground">{section.title}</h3>
                          <span
                            className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded ${
                              section.source === "wizard"
                                ? "bg-blue-100 text-blue-700"
                                : section.source === "chat"
                                ? "bg-emerald-100 text-emerald-700"
                                : "bg-muted text-muted-foreground"
                            }`}
                          >
                            {section.source}
                          </span>
                        </div>
                        {section.subtitle && <p className="text-sm text-muted-foreground mb-3">{section.subtitle}</p>}
                        {section.description && (
                          <div
                            className="mb-4 prose prose-sm md:prose-base max-w-none text-foreground
                                       prose-headings:mt-0 prose-p:my-2 prose-li:my-0
                                       prose-strong:font-semibold prose-code:px-1 prose-code:py-0.5"
                          >
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              components={{
                                a: (props) => <a {...props} target="_blank" rel="noopener noreferrer" />,
                                ul: ({ node, ...props }) => <ul className="list-disc pl-6 my-2 space-y-1" {...props} />,
                                ol: ({ node, ...props }) => <ol className="list-decimal pl-6 my-2 space-y-1" {...props} />,
                                li: ({ node, ...props }) => <li className="leading-relaxed" {...props} />,
                              }}
                            >
                              {String(section.description)}
                            </ReactMarkdown>
                          </div>
                        )}
                      </div>
                    ))}
                  </>
                ) : (
                  <div className="flex items-center justify-center h-full">
                    <p className="text-muted-foreground text-center">
                      Beschreiben Sie Ihr Bauprojekt im Chatfeld links oder nutzen Sie den Wizard, um das Angebot erstellen zu lassen.
                    </p>
                  </div>
                )}
              </div>

              {/* Footer (rechts) */}
              <div className="mt-4 pt-4 border-t border-border">
                <div className="flex gap-3 justify-center">
                  <Button variant="outline" className="px-6 py-2 bg-muted hover:bg-muted/80 text-muted-foreground border-muted">
                    <Edit className="w-4 h-4 mr-2" />
                    Bearbeiten
                  </Button>
                  <Button variant="outline" className="px-6 py-2 bg-muted hover:bg-muted/80 text-muted-foreground border-muted">
                    <Save className="w-4 h-4 mr-2" />
                    Speichern
                  </Button>
                </div>
              </div>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
};

export default KalkulaiInterface;
