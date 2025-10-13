import { useMemo, useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

type Suggestion = {
  nr: number;
  name: string;
  menge: number;
  einheit: string;
  text: string;
};

type StepResponse = {
  session_id: string;
  step: string;
  question: string;
  ui: {
    type: "singleSelect" | "multiSelect" | "number" | "info";
    options?: string[];
    min?: number;
    max?: number;
    step?: number;
  };
  context_partial: Record<string, any>;
  done: boolean;
  suggestions?: Suggestion[];
};

export type WizardFinalizeResult = {
  session_id: string;
  summary: string;
  positions: { nr: number; name: string; menge: number; einheit: string; text: string }[];
  done: boolean;
};

type Props = {
  onFinalize: (result: WizardFinalizeResult) => Promise<void> | void;
  onProgress?: (s: StepResponse) => void;
};

const TOTAL_STEPS = 8;

export default function WizardMaler({ onFinalize, onProgress }: Props) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [step, setStep] = useState<StepResponse | null>(null);
  const [answerMulti, setAnswerMulti] = useState<Record<string, boolean>>({});
  const [history, setHistory] = useState<Array<{ key: string; value: any }>>([]);

  // --- NEU: kontrolliertes Number-Input + Guard gegen Doppelsend ---
  const [numValue, setNumValue] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);

  // Startet neue Session und zeigt die erste Frage
  const start = async () => {
    const res = await api.wizardNext();
    setSessionId(res.session_id);
    setStep(res);
    setHistory([]);
    setAnswerMulti({});
    setNumValue(""); // sicherheitshalber
    onProgress?.(res);
  };

  // Antwort senden (merkt sich den Schritt in history)
  const sendAnswer = async (value: any) => {
    if (!sessionId || !step) return;
    setHistory((prev) => [...prev, { key: step.step, value }]);
    const res = await api.wizardNext(sessionId, { [step.step]: value });
    setStep(res);
    onProgress?.(res);
  };

  // Einen Schritt zurück
  const goBack = async () => {
    if (!step || history.length === 0) return;
    const newHistory = history.slice(0, -1);

    const first = await api.wizardNext();
    let sid = first.session_id;
    let lastRes: StepResponse = first;

    for (const entry of newHistory) {
      lastRes = await api.wizardNext(sid, { [entry.key]: entry.value });
    }

    setSessionId(sid);
    setStep(lastRes);
    setHistory(newHistory);
    setAnswerMulti({});
    setNumValue(""); // Eingabefeld leeren
    onProgress?.(lastRes);
  };

  const toggleMulti = (opt: string) => setAnswerMulti((prev) => ({ ...prev, [opt]: !prev[opt] }));
  const sendMulti = async () => {
    const selected = Object.keys(answerMulti).filter((k) => answerMulti[k]);
    await sendAnswer(selected);
    setAnswerMulti({});
  };

  const finalize = async () => {
    if (!sessionId) return;
    const res = await api.wizardFinalize(sessionId);
    await onFinalize(res);
  };

  // Fortschritt
  const ctx = useMemo(() => step?.context_partial ?? {}, [step]);
  const filledCount = useMemo(() => Object.keys(ctx).length, [ctx]);
  const currentIndex = Math.min(filledCount + 1, TOTAL_STEPS);
  const pct = Math.round((Math.min(currentIndex, TOTAL_STEPS) / TOTAL_STEPS) * 100);

  // --- NEU: Bei Schrittwechsel Number-Input leeren ---
  useEffect(() => {
    setNumValue("");
    setSubmitting(false);
  }, [step?.step, step?.ui?.type]);

  // --- NEU: Bestätigen-Helper für Number ---
  const confirmNumber = async () => {
    if (submitting) return;
    setSubmitting(true);
    const raw = numValue.replace(",", ".").trim();
    const parsed = raw === "" ? 0 : Number(raw);
    await sendAnswer(isNaN(parsed) ? 0 : parsed);
    setNumValue("");        // nach Bestätigung leeren
    setSubmitting(false);
  };

  return (
    <div className="space-y-4">
      {!step && (
        <div className="flex justify-center">
          <Button onClick={start}>Wizard starten</Button>
        </div>
      )}

      {step && (
        <div className="space-y-4">
          {/* Header: Stepper + Zurück */}
          <div>
            <div className="flex justify-between items-center mb-2">
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">
                  Schritt {Math.min(currentIndex, TOTAL_STEPS)} / {TOTAL_STEPS}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={goBack}
                  disabled={history.length === 0 || !!step.done}
                >
                  Zurück
                </Button>
              </div>
              <span className="text-sm text-muted-foreground">{pct}%</span>
            </div>
            <div className="w-full bg-muted h-2 rounded">
              <div className="h-2 bg-primary rounded transition-all" style={{ width: `${pct}%` }} />
            </div>
          </div>

          {/* Frage */}
          {!step.done && <h3 className="text-lg font-semibold">{step.question}</h3>}

          {/* UI je Step */}
          {!step.done && step.ui?.type === "singleSelect" && (
            <div className="flex flex-wrap gap-2">
              {(step.ui.options ?? []).map((o) => (
                <Button key={o} variant="outline" onClick={() => sendAnswer(o)}>
                  {o}
                </Button>
              ))}
            </div>
          )}

          {!step.done && step.ui?.type === "multiSelect" && (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2">
                {(step.ui.options ?? []).map((o) => (
                  <Button
                    key={o}
                    variant={answerMulti[o] ? "default" : "outline"}
                    onClick={() => toggleMulti(o)}
                  >
                    {o}
                  </Button>
                ))}
              </div>
              <Button onClick={sendMulti} disabled={!Object.values(answerMulti).some(Boolean)}>
                Weiter
              </Button>
            </div>
          )}

          {!step.done && step.ui?.type === "number" && (
            <div className="flex items-center gap-3">
              <input
                key={step.step}                       // Remount bei Schrittwechsel
                type="number"
                inputMode="decimal"
                min={step.ui.min}
                max={step.ui.max}
                step={step.ui.step}
                className="border rounded px-2 py-1 w-40 focus:outline-none focus:ring-2 focus:ring-primary"
                value={numValue}                      // kontrolliert
                onChange={(e) => setNumValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void confirmNumber();
                  }
                }}
                onBlur={() => void confirmNumber()}
              />
              <span className="text-sm text-muted-foreground">Enter oder Fokus verlassen für Weiter</span>
            </div>
          )}

          {/* Finalize */}
          {step.done && (
            <div className="space-y-3">
              <p>Alle Angaben vollständig. Jetzt finalisieren?</p>
              <div className="flex items-center gap-2">
                <Button variant="outline" onClick={goBack}>Zurück</Button>
                <Button onClick={finalize}>Finalisieren</Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
