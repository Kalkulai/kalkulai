import { useState, useRef, useEffect } from "react";
import { Mic, Camera, MessageSquare, ArrowUp, Edit, Save, FileText, UserCircle, ChevronDown, User, Settings, LogOut, Mail, Lock, Loader2, Eye, EyeOff, Check } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import WizardMaler, { WizardFinalizeResult } from "@/components/WizardMaler";
import DatabaseManager from "@/components/DatabaseManager";
import GuardMaterialsEditor from "@/components/GuardMaterialsEditor";
import OfferEditor, { OfferPosition } from "@/components/OfferEditor";
import OfferLibrary from "@/components/OfferLibrary";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DropdownMenuSeparator } from "@/components/ui/dropdown-menu";

import type {
  RevenueGuardResponse,
  RevenueGuardSuggestion,
  WizardStepResponse,
  Offer,
} from "@/lib/api";

// ---- Einheitliche Kartenhöhe (hier zentral ändern) ----
const CARD_HEIGHT = "h-[65dvh]"; // Beispiele: "h-[640px]" | "h-[70vh]" | "h-[calc(100dvh-200px)]"

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

interface KalkulaiInterfaceProps {
  embedded?: boolean;
}

const KalkulaiInterface = ({ embedded = false }: KalkulaiInterfaceProps) => {
  const { user, token, logout, changePassword, changeEmail, updateProfile } = useAuth();
  
  const [activeTab, setActiveTab] = useState<"angebot" | "rechnung">("angebot");
  const [activeNav, setActiveNav] = useState<"erstellen" | "bibliothek">("erstellen");
  const [leftMode, setLeftMode] = useState<"chat" | "wizard">("chat");
  const [isProfileDialogOpen, setIsProfileDialogOpen] = useState(false);
  const [isSettingsDialogOpen, setIsSettingsDialogOpen] = useState(false);
  const [guardRefreshKey, setGuardRefreshKey] = useState(0);

  const [inputText, setInputText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isMakingPdf, setIsMakingPdf] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  
  // Profile/Account state
  const [profileName, setProfileName] = useState(user?.name || "");
  const [isUpdatingProfile, setIsUpdatingProfile] = useState(false);
  const [profileMessage, setProfileMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  
  // Password change state
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPasswords, setShowPasswords] = useState(false);
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  
  // Email change state
  const [newEmail, setNewEmail] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [isChangingEmail, setIsChangingEmail] = useState(false);
  const [emailMessage, setEmailMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  
  // Current offer being edited (from library)
  const [currentOffer, setCurrentOffer] = useState<Offer | null>(null);
  const [offerTitle, setOfferTitle] = useState("");
  const [offerKunde, setOfferKunde] = useState("");
  const [isSavingOffer, setIsSavingOffer] = useState(false);

  // Angebotspositionen (final-relevant: PDF, Preise)
  const [positions, setPositions] = useState<
    Array<{ nr: number; name: string; menge: number; einheit: string; epreis: number; gesamtpreis?: number }>
  >([]);

  // Rechte Output-Box (Chat/Wizard/System)
  const [sections, setSections] = useState<UiSection[]>([]);

  // Revenue Guard + Wizard-Kontext
  const [guard, setGuard] = useState<RevenueGuardResponse | null>(null);
  const [wizardCtx, setWizardCtx] = useState<any>(null);

  const settingsCategories = [
    {
      title: "Allgemeine Einstellungen",
      description: "Standardsprache, Zeitzone und Darstellung der Oberfläche anpassen.",
    },
    {
      title: "Benachrichtigungen",
      description: "E-Mail-, In-App- und Team-Updates gezielt konfigurieren.",
    },
    {
      title: "Abrechnung & Pläne",
      description: "Tarifübersicht, Rechnungsarchiv und Zahlungsmethoden einsehen.",
    },
  ];

  // ---- Linke Historie + Autoscroll ----
  const [inputs, setInputs] = useState<InputEntry[]>([]);
  const leftScrollRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    leftScrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [inputs]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const minHeight = 44;
    const maxHeight = 320;
    textarea.style.height = "auto";
    const nextHeight = Math.min(Math.max(textarea.scrollHeight, minHeight), maxHeight);
    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [inputText]);

  // ---- Backend-Reset beim Mount + lokaler Reset ----
  useEffect(() => {
    (async () => {
      try {
        await api.reset(); // leert Chat-Memory & Wizard-Sessions im Backend
      } catch (e) {
        // optional: System-Hinweis rechts anzeigen
        setSections((prev) => [
          ...prev,
          {
            id: String(Date.now() + Math.random()),
            ts: Date.now(),
            title: "Hinweis",
            subtitle: "Server-Reset",
            description: "Konnte den Server-Reset nicht ausführen. Bitte Seite neu laden oder später erneut versuchen.",
            source: "system",
          },
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

  useEffect(() => {
    if (isSettingsDialogOpen) {
      setGuardRefreshKey((key) => key + 1);
    }
  }, [isSettingsDialogOpen]);

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
    setInputText("");
    textareaRef.current?.focus();
    setSections([]);

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
        ...prev,
        mkSection({
          title: "Chat-Antwort",
          subtitle: "Erste Analyse",
          description: replyText,
          source: "chat",
        }),
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
              ...prev,
              mkSection({
                title: "Bestätigung erhalten",
                subtitle: "Angebot erzeugt",
                description: `Es wurden **${offer.positions.length} Positionen** übernommen. Du kannst jetzt das PDF erstellen.`,
                source: "system",
              }),
            ]);
            await runRevenueGuard();
          } else {
            setSections((prev) => [
              ...prev,
              mkSection({
                title: "Hinweis",
                subtitle: "Keine Positionen erkannt",
                description:
                  "Die Bestätigung wurde erkannt, aber es konnten keine Katalogpositionen gemappt werden. Bitte formuliere die Produkte konkreter (z. B. „Dispersionsfarbe, 10 L“, „Tiefgrund, 10 L“, „Abdeckfolie 4×5 m“).",
                source: "system",
              }),
            ]);
          }
        } catch (e: any) {
          setSections((prev) => [
            ...prev,
            mkSection({
              title: "Fehler",
              subtitle: "Angebotserstellung",
              description: String(e?.message ?? "Unbekannter Fehler bei /api/offer"),
              source: "system",
            }),
          ]);
        }
      }
    } catch (e: any) {
      const err = String(e?.message ?? "Unbekannter Fehler");
      setSections((prev) => [
        ...prev,
        mkSection({
          title: "Fehler",
          subtitle: "Chat fehlgeschlagen",
          description: err,
          source: "system",
        }),
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
        ...prev,
        mkSection({
          title: "Hinweis",
          subtitle: "PDF nicht möglich",
          description: "Es sind noch keine Positionen vorhanden. Bitte zuerst über Chat oder Wizard Positionen ermitteln.",
          source: "system",
        }),
      ]);
      return;
    }

    setIsMakingPdf(true);
    try {
      const res = await api.pdf({
        positions,
        kunde: "Bau GmbH\nHauptstraße 1\n12345 Stadt",
      });

      const base = api.base();
      const fullUrl = /^https?:\/\//i.test(res.pdf_url) ? res.pdf_url : `${base}${res.pdf_url}`;
      await forceDownload(fullUrl, "Angebot.pdf");
    } catch (e: any) {
      setSections((prev) => [
        ...prev,
        mkSection({
          title: "Fehler",
          subtitle: "PDF fehlgeschlagen",
          description: String(e?.message ?? "Unbekannter Fehler"),
          source: "system",
        }),
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
        ...withoutLive,
        mkSection({
          title: "Live-Vorschau",
          subtitle: "Mengen & Materialien (ohne Preise)",
          description: previewMd,
          source: "wizard",
        }),
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
        ...prev,
        mkSection({
          title: "Hinweis",
          subtitle: "Automatische Katalog-Zuordnung",
          description:
            "Konnte nicht alle Positionen automatisch zuordnen. Du kannst trotzdem ein PDF erzeugen; Preise sind zunächst 0.",
          source: "system",
        }),
      ]);
    }

    setPositions(mappedPositions);

    setSections((prev) => {
      const withoutLive = prev.filter((s) => !(s.source === "wizard" && s.title === "Live-Vorschau"));
      return [
        ...withoutLive,
        mkSection({
          title: "Wizard abgeschlossen",
          subtitle: "Zusammenfassung",
          description: `**${wz.summary}**\n\nEs wurden ${wz.positions.length} Materialpositionen vorbereitet.`,
          source: "wizard",
        }),
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

    // Berechne die korrekte nächste Positionsnummer
    const nextNr = positions.length > 0 
      ? Math.max(...positions.map(p => p.nr)) + 1 
      : 1;

    const newPos = {
      ...(mapped ?? {
        name: sug.name,
        menge: Number(sug.menge) || 0,
        einheit: sug.einheit || "",
        epreis: 0,
      }),
      nr: nextNr,  // Immer die korrekte fortlaufende Nummer setzen
    };

    setPositions((prev) => [...prev, newPos]);
    // Nach Hinzufügen direkt erneut prüfen
    await runRevenueGuard();
  }

  const chatSection = sections.find((s) => s.source === "chat");
  const supportingSections = sections.filter((s) => s.source !== "chat");

  // Editor handlers
  const handleStartEditing = () => {
    if (positions.length > 0) {
      setIsEditing(true);
    }
  };

  const handleSaveEdits = (updatedPositions: OfferPosition[]) => {
    setPositions(updatedPositions);
    setIsEditing(false);
    setSections((prev) => [
      ...prev,
      mkSection({
        title: "Angebot aktualisiert",
        subtitle: "Änderungen übernommen",
        description: `Das Angebot enthält jetzt **${updatedPositions.length} Positionen**. Du kannst nun das PDF erstellen.`,
        source: "system",
      }),
    ]);
  };

  const handleCancelEditing = () => {
    setIsEditing(false);
  };

  // --- Bibliothek Funktionen ---
  const handleEditOfferFromLibrary = (offer: Offer) => {
    setCurrentOffer(offer);
    setOfferTitle(offer.title);
    setOfferKunde(offer.kunde || "");
    setPositions(offer.positions);
    setActiveNav("erstellen");
    setSections([
      mkSection({
        title: "Angebot geladen",
        subtitle: offer.title,
        description: `Das Angebot wurde aus der Bibliothek geladen. Du kannst es jetzt bearbeiten oder über den Chat anpassen.`,
        source: "system",
      }),
    ]);
  };

  const handleNewOffer = () => {
    setCurrentOffer(null);
    setOfferTitle("");
    setOfferKunde("");
    setPositions([]);
    setSections([]);
    setInputs([]);
    setGuard(null);
    setActiveNav("erstellen");
  };

  const handleSaveOffer = async () => {
    if (!token || positions.length === 0) return;
    
    const title = offerTitle.trim() || `Angebot vom ${new Date().toLocaleDateString("de-DE")}`;
    
    setIsSavingOffer(true);
    try {
      if (currentOffer) {
        // Update existing offer
        const response = await api.offers.update(token, currentOffer.id, {
          title,
          kunde: offerKunde || undefined,
          positions,
        });
        setCurrentOffer(response.offer);
        setSections((prev) => [
          ...prev,
          mkSection({
            title: "Angebot gespeichert",
            subtitle: title,
            description: "Änderungen wurden in der Bibliothek gespeichert.",
            source: "system",
          }),
        ]);
      } else {
        // Create new offer
        const response = await api.offers.create(token, {
          title,
          kunde: offerKunde || undefined,
          positions,
        });
        setCurrentOffer(response.offer);
        setSections((prev) => [
          ...prev,
          mkSection({
            title: "Angebot gespeichert",
            subtitle: title,
            description: "Das Angebot wurde in der Bibliothek gespeichert.",
            source: "system",
          }),
        ]);
      }
    } catch (err: any) {
      setSections((prev) => [
        ...prev,
        mkSection({
          title: "Fehler",
          subtitle: "Speichern fehlgeschlagen",
          description: err.message || "Unbekannter Fehler beim Speichern",
          source: "system",
        }),
      ]);
    } finally {
      setIsSavingOffer(false);
    }
  };

  return (
    <div className={embedded ? "" : "min-h-screen bg-background"}>
      {/* Embedded Header - kompakt für eingebetteten Modus */}
      {embedded ? (
        <div className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Angebote & Rechnungen</h1>
            <p className="text-slate-500 mt-1">Erstelle und verwalte deine Dokumente</p>
          </div>
          <div className="flex items-center gap-4">
            {/* Navigation Tabs */}
            <div className="flex items-center gap-2 bg-slate-100 p-1 rounded-lg">
              <button
                onClick={() => setActiveNav("erstellen")}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
                  activeNav === "erstellen" 
                    ? "bg-white shadow-sm text-slate-900" 
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                Erstellen
              </button>
              <button
                onClick={() => setActiveNav("bibliothek")}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
                  activeNav === "bibliothek" 
                    ? "bg-white shadow-sm text-slate-900" 
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                Bibliothek
              </button>
            </div>
            
            {/* Mode Toggle (Chat/Wizard) */}
            {activeNav === "erstellen" && (
              <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg">
                <button
                  onClick={() => setLeftMode("chat")}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                    leftMode === "chat"
                      ? "bg-primary text-white shadow-sm"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  Chat
                </button>
                <button
                  onClick={() => setLeftMode("wizard")}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                    leftMode === "wizard"
                      ? "bg-primary text-white shadow-sm"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  Wizard
                </button>
              </div>
            )}

            {/* Type Toggle (Angebot/Rechnung) */}
            <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg">
              <button
                onClick={() => setActiveTab("angebot")}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                  activeTab === "angebot" 
                    ? "bg-white shadow-sm text-slate-900" 
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                Angebot
              </button>
              <button
                onClick={() => setActiveTab("rechnung")}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                  activeTab === "rechnung" 
                    ? "bg-white shadow-sm text-slate-900" 
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                Rechnung
              </button>
            </div>

            {/* Settings Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsSettingsDialogOpen(true)}
              className="gap-2"
            >
              <Settings className="w-4 h-4" />
              <span className="hidden sm:inline">Einstellungen</span>
            </Button>
          </div>
        </div>
      ) : (
        /* Original Header für Standalone-Modus */
        <header className="bg-card border-b border-border px-4 lg:px-6 py-4">
          <div className="max-w-[1440px] mx-auto">
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
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground"
                    >
                      <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                        <span className="text-sm font-semibold text-primary">
                          {(user?.name || user?.email || "U").charAt(0).toUpperCase()}
                        </span>
                      </div>
                      <span className="hidden sm:inline max-w-[120px] truncate">
                        {user?.name || user?.email || "Profil"}
                      </span>
                      <ChevronDown className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-56">
                    <div className="px-3 py-2 border-b border-border">
                      <p className="text-sm font-medium truncate">{user?.name || "Benutzer"}</p>
                      <p className="text-xs text-muted-foreground truncate">{user?.email}</p>
                    </div>
                    <DropdownMenuItem
                      onSelect={() => setIsProfileDialogOpen(true)}
                      className="mt-1"
                    >
                      <User className="mr-2 h-4 w-4" />
                      <span>Mein Profil</span>
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onSelect={() => setIsSettingsDialogOpen(true)}
                    >
                      <Settings className="mr-2 h-4 w-4" />
                      <span>Einstellungen</span>
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onSelect={logout}
                      className="text-red-600 focus:text-red-600 focus:bg-red-50"
                    >
                      <LogOut className="mr-2 h-4 w-4" />
                      <span>Abmelden</span>
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
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
      )}

      {/* Main */}
      <main className={embedded ? "" : "max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 py-6"}>
        {activeNav === "bibliothek" ? (
          /* Bibliothek View */
          <Card className="p-6 lg:p-8 min-h-[70vh] shadow-soft border border-border">
            <OfferLibrary 
              onEditOffer={handleEditOfferFromLibrary}
              onNewOffer={handleNewOffer}
            />
          </Card>
        ) : (
          /* Erstellen View */
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left */}
          <div className="space-y-4">
            <Card className={`relative p-6 lg:p-8 ${CARD_HEIGHT} shadow-soft border border-border flex flex-col`}>
              {leftMode === "chat" ? (
                <>
                  {/* Historie deiner Eingaben */}
                  <div className="flex-1 overflow-y-auto pr-2 space-y-4">
                    {inputs.map((m) => (
                      <div key={m.id} className="flex justify-end">
                        <div className="max-w-[80%] rounded-2xl px-4 py-2 text-base shadow-sm bg-primary text-primary-foreground">
                          <div className="markdown-body text-primary-foreground">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
                          </div>
                          <div className="text-[10px] opacity-70 mt-1 text-right">
                            {new Date(m.ts).toLocaleTimeString()}
                          </div>
                        </div>
                      </div>
                    ))}
                    <div ref={leftScrollRef} />
                  </div>

                  {/* Composer */}
                  <div className="mt-3 border rounded-xl p-3 bg-background/80 min-h-[60px] shadow-inner">
                    <textarea
                      ref={textareaRef}
                      value={inputText}
                      onChange={(e) => setInputText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          handleSend();
                        }
                      }}
                      placeholder="Nachricht eingeben um einen Angebotsvorschlag zu erhalten"
                      className="w-full min-h-[44px] resize-none border-none outline-none text-base leading-6 placeholder:text-muted-foreground bg-transparent p-0"
                      rows={1}
                    />
                    <div className="flex items-center justify-between pt-2">
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
            <Card className={`p-7 lg:p-9 ${CARD_HEIGHT} shadow-soft border border-border flex flex-col`}>
              {isEditing ? (
                /* Editor Mode */
                <OfferEditor
                  positions={positions}
                  onSave={handleSaveEdits}
                  onCancel={handleCancelEditing}
                />
              ) : (
                <>
              {/* Kopf */}
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold text-foreground mb-1">Ergebnis</h2>
                  <p className="text-base text-muted-foreground">Aktuelle Auswertung</p>
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

              {/* Scrollbarer Content-Bereich */}
              <div className="flex-1 overflow-y-auto">
                {isLoading && !chatSection && supportingSections.length === 0 && (!guard || guard.missing.length === 0) ? (
                  <div className="flex items-center justify-center h-full">
                    <div className="text-center">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
                      <p className="text-muted-foreground">Analysiere Eingabe…</p>
                    </div>
                  </div>
                    ) : chatSection || supportingSections.length > 0 || (guard && guard.missing.length > 0) || positions.length > 0 ? (
                  <div className="space-y-6">
                        {/* Positions Preview */}
                        {positions.length > 0 && (
                          <div className="mb-4 border border-border rounded-lg overflow-hidden">
                            <div className="bg-muted/50 px-4 py-2 border-b border-border">
                              <h3 className="font-semibold text-foreground text-sm">
                                Angebotspositionen ({positions.length})
                              </h3>
                            </div>
                            <div className="divide-y divide-border max-h-[200px] overflow-y-auto">
                              {positions.map((p, idx) => (
                                <div key={`${p.nr}-${idx}`} className="px-4 py-2 flex justify-between items-center text-sm">
                                  <div className="flex-1">
                                    <span className="text-muted-foreground mr-2">{p.nr}.</span>
                                    <span className="font-medium">{p.name}</span>
                                  </div>
                                  <div className="text-right text-muted-foreground">
                                    {p.menge} {p.einheit} × {p.epreis.toFixed(2)} € = <span className="font-medium text-foreground">{((p.menge || 0) * (p.epreis || 0)).toFixed(2)} €</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                            <div className="bg-muted/30 px-4 py-2 border-t border-border flex justify-between">
                              <span className="text-sm font-medium">Netto Summe</span>
                              <span className="font-semibold tabular-nums">
                                {positions.reduce((sum, p) => sum + (p.menge || 0) * (p.epreis || 0), 0).toFixed(2)} €
                              </span>
                            </div>
                          </div>
                        )}

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

                    {chatSection && (
                      <div key={chatSection.id} className="rounded-xl border border-border bg-card/60 p-5 shadow-sm">
                        <h3 className="text-lg font-semibold text-foreground mb-1">{chatSection.title}</h3>
                        {chatSection.subtitle && (
                          <p className="text-sm text-muted-foreground mb-3">{chatSection.subtitle}</p>
                        )}
                        {chatSection.description && (
                          <div className="markdown-body text-foreground text-base leading-7">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {String(chatSection.description)}
                            </ReactMarkdown>
                          </div>
                        )}
                      </div>
                    )}

                    {supportingSections.map((section) => (
                      <div key={section.id} className="rounded-xl border border-dashed border-border/80 p-4">
                        <div className="flex items-center justify-between mb-1">
                          <h3 className="text-sm font-semibold text-foreground">{section.title}</h3>
                          <span className="text-xs uppercase text-muted-foreground">{section.source}</span>
                        </div>
                        {section.subtitle && <p className="text-xs text-muted-foreground mb-2">{section.subtitle}</p>}
                        {section.description && (
                          <div className="markdown-body text-sm leading-6 text-foreground">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {String(section.description)}
                            </ReactMarkdown>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex items-center justify-center h-full">
                    <p className="text-base text-muted-foreground text-center">
                      Beschreiben Sie Ihr Bauprojekt im Chatfeld links oder nutzen Sie den Wizard, um das Angebot erstellen zu lassen.
                    </p>
                  </div>
                )}
              </div>

              {/* Footer (rechts) */}
              <div className="mt-4 pt-4 border-t border-border">
                {/* Current offer info */}
                {(currentOffer || positions.length > 0) && (
                  <div className="mb-3 flex items-center gap-2">
                    <Input
                      placeholder="Angebotstitel (optional)"
                      value={offerTitle}
                      onChange={(e) => setOfferTitle(e.target.value)}
                      className="flex-1 h-9 text-sm"
                    />
                    <Input
                      placeholder="Kunde (optional)"
                      value={offerKunde}
                      onChange={(e) => setOfferKunde(e.target.value)}
                      className="flex-1 h-9 text-sm"
                    />
                  </div>
                )}
                <div className="flex gap-3 justify-center">
                  <Button
                    variant="outline"
                    className={`px-6 py-2 ${positions.length > 0 ? 'hover:bg-primary/10 hover:border-primary' : 'bg-muted text-muted-foreground border-muted'}`}
                    disabled={positions.length === 0}
                    onClick={handleStartEditing}
                    title={positions.length === 0 ? "Erst Positionen erstellen" : "Angebot bearbeiten"}
                  >
                    <Edit className="w-4 h-4 mr-2" />
                    Bearbeiten
                  </Button>
                  <Button 
                    variant="outline" 
                    className={`px-6 py-2 ${positions.length > 0 ? 'hover:bg-green-50 hover:border-green-500 hover:text-green-700' : 'bg-muted text-muted-foreground border-muted'}`}
                    disabled={positions.length === 0 || isSavingOffer}
                    onClick={handleSaveOffer}
                    title={positions.length === 0 ? "Erst Positionen erstellen" : "In Bibliothek speichern"}
                  >
                    {isSavingOffer ? (
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    ) : (
                      <Save className="w-4 h-4 mr-2" />
                    )}
                    {currentOffer ? "Aktualisieren" : "Speichern"}
                  </Button>
                </div>
              </div>
                </>
              )}
            </Card>
          </div>
        </div>
        )}
      </main>

      {/* Dialogs */}
      <Dialog open={isProfileDialogOpen} onOpenChange={(open) => {
        setIsProfileDialogOpen(open);
        if (open) {
          setProfileName(user?.name || "");
          setProfileMessage(null);
          setCurrentPassword("");
          setNewPassword("");
          setConfirmPassword("");
          setPasswordMessage(null);
          setNewEmail("");
          setEmailPassword("");
          setEmailMessage(null);
        }
      }}>
        <DialogContent className="max-w-xl max-h-[85vh] overflow-y-auto">
          <DialogHeader className="space-y-1 text-left">
            <DialogTitle>Mein Profil</DialogTitle>
            <DialogDescription>
              Verwalte deine persönlichen Daten und Zugangsdaten.
            </DialogDescription>
          </DialogHeader>
          
          <Tabs defaultValue="profile" className="w-full">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="profile">Profil</TabsTrigger>
              <TabsTrigger value="password">Passwort</TabsTrigger>
              <TabsTrigger value="email">E-Mail</TabsTrigger>
            </TabsList>
            
            {/* Profile Tab */}
            <TabsContent value="profile" className="mt-4 space-y-4">
              <div className="flex items-center gap-4 p-4 bg-muted/40 rounded-lg">
                <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center">
                  <span className="text-2xl font-semibold text-primary">
                    {(user?.name || user?.email || "U").charAt(0).toUpperCase()}
                  </span>
                </div>
                <div>
                  <p className="font-medium">{user?.name || "Kein Name"}</p>
                  <p className="text-sm text-muted-foreground">{user?.email}</p>
                </div>
              </div>
              
          <div className="space-y-3">
                <div className="space-y-2">
                  <Label htmlFor="profile-name">Name</Label>
                  <Input
                    id="profile-name"
                    value={profileName}
                    onChange={(e) => setProfileName(e.target.value)}
                    placeholder="Dein Name"
                  />
                </div>
                
                {profileMessage && (
                  <div className={`p-3 rounded-lg text-sm ${
                    profileMessage.type === "success" 
                      ? "bg-green-50 border border-green-200 text-green-700" 
                      : "bg-red-50 border border-red-200 text-red-700"
                  }`}>
                    {profileMessage.text}
                  </div>
                )}
                
                <Button 
                  onClick={async () => {
                    setIsUpdatingProfile(true);
                    setProfileMessage(null);
                    try {
                      await updateProfile(profileName);
                      setProfileMessage({ type: "success", text: "Profil erfolgreich aktualisiert" });
                    } catch (err: any) {
                      setProfileMessage({ type: "error", text: err.message || "Fehler beim Aktualisieren" });
                    } finally {
                      setIsUpdatingProfile(false);
                    }
                  }}
                  disabled={isUpdatingProfile || profileName === user?.name}
                  className="w-full"
                >
                  {isUpdatingProfile ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Wird gespeichert...
                    </>
                  ) : (
                    <>
                      <Check className="mr-2 h-4 w-4" />
                      Name speichern
                    </>
                  )}
                </Button>
              </div>
            </TabsContent>
            
            {/* Password Tab */}
            <TabsContent value="password" className="mt-4 space-y-4">
              <div className="space-y-3">
                <div className="space-y-2">
                  <Label htmlFor="current-password">Aktuelles Passwort</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="current-password"
                      type={showPasswords ? "text" : "password"}
                      value={currentPassword}
                      onChange={(e) => setCurrentPassword(e.target.value)}
                      className="pl-10 pr-10"
                      placeholder="••••••••"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPasswords(!showPasswords)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                      {showPasswords ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
          </div>
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="new-password">Neues Passwort</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="new-password"
                      type={showPasswords ? "text" : "password"}
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      className="pl-10"
                      placeholder="Mindestens 6 Zeichen"
                    />
                  </div>
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="confirm-password">Passwort bestätigen</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="confirm-password"
                      type={showPasswords ? "text" : "password"}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      className="pl-10"
                      placeholder="Passwort wiederholen"
                    />
                  </div>
                </div>
                
                {passwordMessage && (
                  <div className={`p-3 rounded-lg text-sm ${
                    passwordMessage.type === "success" 
                      ? "bg-green-50 border border-green-200 text-green-700" 
                      : "bg-red-50 border border-red-200 text-red-700"
                  }`}>
                    {passwordMessage.text}
                  </div>
                )}
                
                <Button 
                  onClick={async () => {
                    setPasswordMessage(null);
                    
                    if (newPassword !== confirmPassword) {
                      setPasswordMessage({ type: "error", text: "Passwörter stimmen nicht überein" });
                      return;
                    }
                    if (newPassword.length < 6) {
                      setPasswordMessage({ type: "error", text: "Passwort muss mindestens 6 Zeichen lang sein" });
                      return;
                    }
                    
                    setIsChangingPassword(true);
                    try {
                      await changePassword(currentPassword, newPassword);
                      setPasswordMessage({ type: "success", text: "Passwort erfolgreich geändert" });
                      setCurrentPassword("");
                      setNewPassword("");
                      setConfirmPassword("");
                    } catch (err: any) {
                      setPasswordMessage({ type: "error", text: err.message || "Fehler beim Ändern" });
                    } finally {
                      setIsChangingPassword(false);
                    }
                  }}
                  disabled={isChangingPassword || !currentPassword || !newPassword || !confirmPassword}
                  className="w-full"
                >
                  {isChangingPassword ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Wird geändert...
                    </>
                  ) : (
                    <>
                      <Lock className="mr-2 h-4 w-4" />
                      Passwort ändern
                    </>
                  )}
                </Button>
              </div>
            </TabsContent>
            
            {/* Email Tab */}
            <TabsContent value="email" className="mt-4 space-y-4">
              <div className="p-3 bg-muted/40 rounded-lg">
                <p className="text-sm text-muted-foreground">
                  Aktuelle E-Mail: <span className="font-medium text-foreground">{user?.email}</span>
                </p>
              </div>
              
              <div className="space-y-3">
                <div className="space-y-2">
                  <Label htmlFor="new-email">Neue E-Mail-Adresse</Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="new-email"
                      type="email"
                      value={newEmail}
                      onChange={(e) => setNewEmail(e.target.value)}
                      className="pl-10"
                      placeholder="neue@email.de"
                    />
                  </div>
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="email-password">Passwort zur Bestätigung</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="email-password"
                      type="password"
                      value={emailPassword}
                      onChange={(e) => setEmailPassword(e.target.value)}
                      className="pl-10"
                      placeholder="Dein aktuelles Passwort"
                    />
                  </div>
                </div>
                
                {emailMessage && (
                  <div className={`p-3 rounded-lg text-sm ${
                    emailMessage.type === "success" 
                      ? "bg-green-50 border border-green-200 text-green-700" 
                      : "bg-red-50 border border-red-200 text-red-700"
                  }`}>
                    {emailMessage.text}
                  </div>
                )}
                
                <Button 
                  onClick={async () => {
                    setEmailMessage(null);
                    setIsChangingEmail(true);
                    try {
                      await changeEmail(newEmail, emailPassword);
                      setEmailMessage({ type: "success", text: "E-Mail erfolgreich geändert" });
                      setNewEmail("");
                      setEmailPassword("");
                    } catch (err: any) {
                      setEmailMessage({ type: "error", text: err.message || "Fehler beim Ändern" });
                    } finally {
                      setIsChangingEmail(false);
                    }
                  }}
                  disabled={isChangingEmail || !newEmail || !emailPassword}
                  className="w-full"
                >
                  {isChangingEmail ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Wird geändert...
                    </>
                  ) : (
                    <>
                      <Mail className="mr-2 h-4 w-4" />
                      E-Mail ändern
                    </>
                  )}
                </Button>
              </div>
            </TabsContent>
          </Tabs>
          
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsProfileDialogOpen(false)}>
              Schließen
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={isSettingsDialogOpen} onOpenChange={setIsSettingsDialogOpen}>
        <DialogContent className="max-w-3xl space-y-6 max-h-[85vh] overflow-y-auto">
          <DialogHeader className="space-y-1 text-left">
            <DialogTitle>Einstellungen</DialogTitle>
            <DialogDescription>
              Richte KalkulAI nach deinen Arbeitsabläufen aus und verwalte deine Präferenzen zentral.
            </DialogDescription>
          </DialogHeader>
          <Tabs defaultValue="overview" className="w-full">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="overview">Übersicht</TabsTrigger>
              <TabsTrigger value="database">Datenbank</TabsTrigger>
              <TabsTrigger value="guard">Vergessener Wächter</TabsTrigger>
            </TabsList>
            <TabsContent value="overview" className="mt-4 space-y-3">
              {settingsCategories.map((category) => (
                <div
                  key={category.title}
                  className="rounded-xl border border-border bg-muted/40 p-4 transition hover:border-primary hover:bg-muted/60"
                >
                  <h3 className="text-sm font-semibold text-foreground">{category.title}</h3>
                  <p className="text-sm text-muted-foreground mt-1">{category.description}</p>
                </div>
              ))}
            </TabsContent>
            <TabsContent value="database" className="mt-4">
              <DatabaseManager />
            </TabsContent>
            <TabsContent value="guard" className="mt-4 max-h-[65vh] overflow-y-auto pr-1">
              <GuardMaterialsEditor refreshSignal={guardRefreshKey} />
            </TabsContent>
          </Tabs>
          <DialogFooter className="sm:justify-between">
            <span className="text-xs text-muted-foreground">
              Änderungen hier wirken sich direkt auf deine lokale Datenbank aus.
            </span>
            <Button variant="outline" onClick={() => setIsSettingsDialogOpen(false)}>
              Schließen
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default KalkulaiInterface;


//changes for testing deployment to cloudflare
