import { useEffect, useState } from "react";
import { PencilLine, Plus, RefreshCw, Save, Trash2 } from "lucide-react";
import { api, RevenueGuardMaterial } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

type EditableMaterial = RevenueGuardMaterial & {
  keywordsText: string;
  quantityText: string;
};

const createEmptyMaterial = (): EditableMaterial => ({
  id: `tmp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
  name: "",
  keywords: [],
  keywordsText: "",
  severity: "medium",
  category: "Benutzerdefiniert",
  reason: "",
  description: "",
  einheit: "",
  default_menge: null,
  quantityText: "",
  confidence: 0.5,
  enabled: true,
  editable: true,
  origin: "custom",
});

const splitKeywords = (value: string) =>
  value
    .split(/[,;\n]/)
    .map((part) => part.trim().toLowerCase())
    .filter(Boolean);

const toEditable = (item: RevenueGuardMaterial): EditableMaterial => ({
  ...item,
  keywords: item.keywords ?? [],
  keywordsText: (item.keywords ?? []).join(", "),
  quantityText:
    typeof item.default_menge === "number" || item.default_menge === 0
      ? String(item.default_menge)
      : "",
  einheit: item.einheit ?? "",
  confidence: item.confidence ?? 0.5,
  enabled: item.enabled ?? true,
  editable: item.editable ?? true,
  origin: item.origin ?? (item.id?.startsWith("custom_") ? "custom" : "builtin"),
});

type GuardMaterialsEditorProps = {
  refreshSignal?: number;
};

const GuardMaterialsEditor = ({ refreshSignal = 0 }: GuardMaterialsEditorProps) => {
  const [items, setItems] = useState<EditableMaterial[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [formItem, setFormItem] = useState<EditableMaterial>(createEmptyMaterial());
  const [isFormVisible, setIsFormVisible] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.revenueGuardMaterials();
      const mapped = (data.items || []).map(toEditable);
      setItems(mapped);

      if (selectedId) {
        const current = mapped.find((entry) => entry.id === selectedId);
        if (current) {
          setFormItem(current);
        } else {
          setSelectedId(null);
          setIsFormVisible(false);
          setFormItem(createEmptyMaterial());
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Konnte Wächter-Regeln nicht laden.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (refreshSignal > 0) {
      load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshSignal]);

  const handleSelect = (id: string) => {
    const item = items.find((entry) => entry.id === id);
    if (!item) return;
    setSelectedId(id);
    setFormItem({ ...item });
    setIsFormVisible(true);
  };

  const handleAddClick = () => {
    setSelectedId(null);
    setFormItem(createEmptyMaterial());
    setIsFormVisible(true);
  };

  const handleDelete = (id: string) => {
    const entry = items.find((item) => item.id === id);
    if (!entry || entry.origin === "builtin") return;
    setItems((prev) => prev.filter((item) => item.id !== id));
    if (selectedId === id) {
      setSelectedId(null);
      setIsFormVisible(false);
      setFormItem(createEmptyMaterial());
    }
  };

  const handleFormChange = (changes: Partial<EditableMaterial>) => {
    setFormItem((prev) => ({ ...prev, ...changes }));
  };

  const handleFormCommit = () => {
    const normalizedKeywords = splitKeywords(formItem.keywordsText);
    const normalized: EditableMaterial = {
      ...formItem,
      origin: formItem.origin ?? (selectedId ? items.find((i) => i.id === selectedId)?.origin : "custom"),
      keywords: normalizedKeywords,
      keywordsText: normalizedKeywords.join(", "),
      quantityText: formItem.quantityText,
      default_menge:
        formItem.quantityText === "" ? null : Number(formItem.quantityText.replace(",", ".")),
    };

    if (selectedId) {
      setItems((prev) => prev.map((item) => (item.id === selectedId ? normalized : item)));
      setFormItem(normalized);
    } else {
      const next = { ...normalized, origin: "custom" };
      setItems((prev) => [...prev, next]);
      setFormItem(createEmptyMaterial());
      setIsFormVisible(false);
    }
    setSuccess(null);
  };

  const toPayload = (item: EditableMaterial) => ({
    id: item.id,
    name: item.name,
    keywords: splitKeywords(item.keywordsText),
    severity: item.severity,
    category: item.category,
    reason: item.reason,
    description: item.description,
    einheit: item.einheit || null,
    default_menge:
      item.quantityText === "" ? null : Number(item.quantityText.replace(",", ".")),
    confidence: item.confidence ?? 0.5,
    enabled: item.enabled ?? true,
    origin: item.origin,
  });

  const save = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const payload = items.map(toPayload);
      const data = await api.saveRevenueGuardMaterials(payload);
      const mapped = (data.items || []).map(toEditable);
      setItems(mapped);
      if (selectedId) {
        const current = mapped.find((entry) => entry.id === selectedId);
        if (current) {
          setFormItem(current);
        } else {
          setSelectedId(null);
          setIsFormVisible(false);
          setFormItem(createEmptyMaterial());
        }
      }
      setSuccess("Guard-Materialien gespeichert.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Konnte Änderungen nicht speichern.");
    } finally {
      setSaving(false);
    }
  };

  const severityTone = (severity: string) => {
    switch (severity) {
      case "high":
        return "bg-red-100 text-red-700 border-red-200";
      case "low":
        return "bg-emerald-100 text-emerald-700 border-emerald-200";
      default:
        return "bg-amber-100 text-amber-800 border-amber-200";
    }
  };

  return (
    <div className="space-y-5">
      {error && (
        <Alert variant="destructive">
          <AlertTitle>Fehler</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {success && (
        <Alert>
          <AlertTitle>Gespeichert</AlertTitle>
          <AlertDescription>{success}</AlertDescription>
        </Alert>
      )}

      <section className="rounded-xl border border-border bg-muted/30 p-4">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h4 className="text-sm font-semibold text-foreground">Alle Wächter-Checks</h4>
            <p className="text-sm text-muted-foreground">
              Standard- und benutzerdefinierte Posten. Klicke auf eine Karte, um sie zu bearbeiten.
            </p>
          </div>
          <Button size="icon" variant="ghost" onClick={load} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>

        <div className="mt-4 space-y-3">
          {items.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Noch keine Wächter-Checks definiert. Nutze „Weitere Posten hinzufügen“.
            </p>
          )}
          {items.map((item) => {
            const isSelected = selectedId === item.id;
            const isBuiltin = item.origin === "builtin";
            return (
              <button
                key={`${item.id}-row`}
                type="button"
                onClick={() => handleSelect(item.id)}
                className={`w-full rounded-lg border bg-background p-3 text-left shadow-sm transition hover:border-primary ${
                  isSelected ? "border-primary ring-1 ring-primary/40" : "border-border/70"
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-foreground">{item.name || "Unbenannt"}</span>
                  <Badge variant="secondary">{item.category || "Allgemein"}</Badge>
                  <Badge className={severityTone(item.severity ?? "medium")}>{item.severity ?? "medium"}</Badge>
                  <Badge variant={isBuiltin ? "outline" : "default"} className="text-xs">
                    {isBuiltin ? "Standard" : "Custom"}
                  </Badge>
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <PencilLine className="h-3 w-3" />
                    Klicken zum Bearbeiten
                  </span>
                </div>
                {item.reason && <p className="mt-1 text-sm text-muted-foreground">{item.reason}</p>}
                <p className="mt-1 text-xs text-muted-foreground">
                  Schlüsselwörter: {(item.keywordsText || "—").toString()}
                </p>
                <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
                  {item.einheit && <span>Einheit: {item.einheit}</span>}
                  {item.quantityText && <span>Standardmenge: {item.quantityText}</span>}
                </div>
                {!isBuiltin && (
                  <div className="mt-3 flex justify-end">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(item.id);
                      }}
                    >
                      <Trash2 className="mr-1 h-4 w-4" />
                      Entfernen
                    </Button>
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </section>

      <section className="rounded-xl border border-border bg-background/60 p-4 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold text-foreground">Arbeiten / Materialien bearbeiten</h4>
            <p className="text-sm text-muted-foreground">
              Wähle einen bestehenden Posten aus oder füge neue typische Arbeiten hinzu.
            </p>
          </div>
          <Button size="sm" variant="secondary" onClick={handleAddClick}>
            <Plus className="mr-2 h-4 w-4" />
            Weitere Posten hinzufügen
          </Button>
        </div>

        {isFormVisible ? (
          <>
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div className="flex-1">
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">Bezeichnung</Label>
                <Input
                  value={formItem.name}
                  onChange={(e) => handleFormChange({ name: e.target.value })}
                  placeholder="z. B. Brandschutzfarbe F30"
                />
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <div>
                  <Label className="text-xs uppercase tracking-wide text-muted-foreground">Priorität</Label>
                  <select
                    value={formItem.severity ?? "medium"}
                    onChange={(e) =>
                      handleFormChange({ severity: e.target.value as EditableMaterial["severity"] })
                    }
                    className="mt-1 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  >
                    <option value="high">hoch</option>
                    <option value="medium">mittel</option>
                    <option value="low">niedrig</option>
                  </select>
                </div>
                <div className="flex flex-col items-center">
                  <Label className="text-xs uppercase tracking-wide text-muted-foreground">Aktiv</Label>
                  <Switch checked={formItem.enabled ?? true} onCheckedChange={(checked) => handleFormChange({ enabled: checked })} />
                </div>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">Schlüsselwörter</Label>
                <Textarea
                  rows={2}
                  value={formItem.keywordsText}
                  placeholder="Kommagetrennte Begriffe, die in bestehenden Positionen gesucht werden…"
                  onChange={(e) =>
                    handleFormChange({
                      keywordsText: e.target.value,
                    })
                  }
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Mindestens ein Begriff muss vorkommen, sonst schlägt der Wächter Alarm.
                </p>
              </div>
              <div>
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">Begründung / Hinweis</Label>
                <Textarea
                  rows={2}
                  value={formItem.reason ?? ""}
                  onChange={(e) => handleFormChange({ reason: e.target.value })}
                  placeholder="Warum ist das Material Pflicht?"
                />
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <div>
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">Kategorie</Label>
                <Input
                  value={formItem.category ?? ""}
                  onChange={(e) => handleFormChange({ category: e.target.value })}
                  placeholder="z. B. Brandschutz, Vorarbeiten …"
                />
              </div>
              <div>
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">Einheit</Label>
                <Input
                  value={formItem.einheit ?? ""}
                  onChange={(e) => handleFormChange({ einheit: e.target.value })}
                  placeholder="z. B. L, kg, Stück"
                />
              </div>
              <div>
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">Standardmenge</Label>
                <Input
                  type="number"
                  step="0.1"
                  value={formItem.quantityText}
                  onChange={(e) => handleFormChange({ quantityText: e.target.value })}
                  placeholder="optional"
                />
              </div>
            </div>

            <div className="flex flex-wrap justify-end gap-3">
              {formItem.origin === "custom" && selectedId && (
                <Button
                  variant="outline"
                  className="border-destructive/40 text-destructive hover:bg-destructive/10"
                  onClick={() => handleDelete(selectedId)}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  Aktuellen Posten löschen
                </Button>
              )}
              <Button variant="secondary" onClick={handleFormCommit}>
                {selectedId ? "Änderungen übernehmen" : "Zur Liste hinzufügen"}
              </Button>
            </div>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            Keine Auswahl aktiv. Wähle einen Posten oben oder klicke „Weitere Posten hinzufügen“.
          </p>
        )}

        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <Button variant="outline" onClick={load} disabled={loading || saving}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Änderungen zurücksetzen
          </Button>
          <Button onClick={save} disabled={saving || loading}>
            <Save className="mr-2 h-4 w-4" />
            Speichern
          </Button>
        </div>
      </section>
    </div>
  );
};

export default GuardMaterialsEditor;
