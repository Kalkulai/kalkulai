import { useEffect, useState } from "react";
import { 
  AlertTriangle, 
  Check, 
  ChevronDown, 
  ChevronRight, 
  Info, 
  PencilLine, 
  Play, 
  Plus, 
  RefreshCw, 
  Save, 
  Shield, 
  Trash2,
  X
} from "lucide-react";
import { api, RevenueGuardMaterial, RevenueGuardResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card } from "@/components/ui/card";

type EditableMaterial = RevenueGuardMaterial & {
  keywordsText: string;
  quantityText: string;
};

const createEmptyMaterial = (): EditableMaterial => ({
  id: `custom_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`,
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

// Kategorien für die Gruppierung
const CATEGORY_ORDER = [
  "Vorarbeiten",
  "Abdecken",
  "Werkzeuge",
  "Arbeitsschutz",
  "Abdichtung",
  "Reinigung",
  "Allgemeines",
  "Benutzerdefiniert",
];

const CATEGORY_ICONS: Record<string, string> = {
  "Vorarbeiten": "🔧",
  "Abdecken": "🛡️",
  "Werkzeuge": "🖌️",
  "Arbeitsschutz": "🧤",
  "Abdichtung": "💧",
  "Reinigung": "🧹",
  "Allgemeines": "📋",
  "Benutzerdefiniert": "⭐",
};

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
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set(CATEGORY_ORDER));
  
  // Test-Funktion States
  const [testMode, setTestMode] = useState(false);
  const [testPositions, setTestPositions] = useState("");
  const [testResult, setTestResult] = useState<RevenueGuardResponse | null>(null);
  const [testing, setTesting] = useState(false);

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
  }, []);

  useEffect(() => {
    if (refreshSignal > 0) {
      load();
    }
  }, [refreshSignal]);

  const handleSelect = (id: string) => {
    const item = items.find((entry) => entry.id === id);
    if (!item) return;
    setSelectedId(id);
    setFormItem({ ...item });
    setIsFormVisible(true);
    setTestMode(false);
  };

  const handleAddClick = () => {
    setSelectedId(null);
    setFormItem(createEmptyMaterial());
    setIsFormVisible(true);
    setTestMode(false);
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
      const next = { ...normalized, origin: "custom" as const };
      setItems((prev) => [...prev, next]);
      setFormItem(createEmptyMaterial());
      setIsFormVisible(false);
    }
    setSuccess("Änderungen übernommen (noch nicht gespeichert)");
    setTimeout(() => setSuccess(null), 2000);
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
      setSuccess("✓ Alle Änderungen gespeichert!");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Konnte Änderungen nicht speichern.");
    } finally {
      setSaving(false);
    }
  };

  // Test-Funktion
  const runTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      // Parse test positions
      const lines = testPositions.trim().split("\n").filter(Boolean);
      const positions = lines.map((line, idx) => ({
        nr: idx + 1,
        name: line.trim(),
        menge: 1,
        einheit: "Stück",
      }));

      const result = await api.revenueGuardCheck({ positions, context: {} });
      setTestResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test fehlgeschlagen");
    } finally {
      setTesting(false);
    }
  };

  const toggleCategory = (cat: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  const severityConfig = {
    high: { label: "Hoch", color: "bg-red-100 text-red-700 border-red-200", icon: "🔴" },
    medium: { label: "Mittel", color: "bg-amber-100 text-amber-700 border-amber-200", icon: "🟡" },
    low: { label: "Niedrig", color: "bg-emerald-100 text-emerald-700 border-emerald-200", icon: "🟢" },
  };

  // Gruppiere Items nach Kategorie
  const groupedItems = items.reduce((acc, item) => {
    const cat = item.category || "Benutzerdefiniert";
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(item);
    return acc;
  }, {} as Record<string, EditableMaterial[]>);

  const sortedCategories = CATEGORY_ORDER.filter((cat) => groupedItems[cat]?.length > 0);
  const enabledCount = items.filter((i) => i.enabled).length;
  const customCount = items.filter((i) => i.origin === "custom").length;

  return (
    <div className="space-y-6">
      {/* Header Stats */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Shield className="w-5 h-5 text-primary" />
            Vergessene Posten Wächter
          </h3>
          <p className="text-sm text-muted-foreground">
            {enabledCount} Regeln aktiv • {customCount} benutzerdefiniert
          </p>
        </div>
        <div className="flex gap-2">
          <Button 
            variant={testMode ? "default" : "outline"} 
            size="sm" 
            onClick={() => setTestMode(!testMode)}
          >
            <Play className="w-4 h-4 mr-1" />
            Test
          </Button>
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} />
            Laden
          </Button>
          <Button size="sm" onClick={save} disabled={saving || loading}>
            <Save className="w-4 h-4 mr-1" />
            Speichern
          </Button>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Fehler</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {success && (
        <Alert className="border-emerald-200 bg-emerald-50">
          <Check className="h-4 w-4 text-emerald-600" />
          <AlertTitle className="text-emerald-700">Erfolg</AlertTitle>
          <AlertDescription className="text-emerald-600">{success}</AlertDescription>
        </Alert>
      )}

      {/* Test-Modus */}
      {testMode && (
        <Card className="p-4 border-primary/30 bg-primary/5">
          <h4 className="font-semibold mb-2 flex items-center gap-2">
            <Play className="w-4 h-4" />
            Test-Modus: Regeln prüfen
          </h4>
          <p className="text-sm text-muted-foreground mb-3">
            Gib Positionen ein (eine pro Zeile), um zu sehen welche Wächter-Regeln auslösen würden:
          </p>
          <Textarea
            rows={4}
            value={testPositions}
            onChange={(e) => setTestPositions(e.target.value)}
            placeholder="Dispersionsfarbe weiß 10L&#10;Tiefgrund 5L&#10;Abdeckfolie&#10;..."
            className="font-mono text-sm mb-3"
          />
          <div className="flex gap-2">
            <Button onClick={runTest} disabled={testing || !testPositions.trim()}>
              {testing ? (
                <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
              ) : (
                <Play className="w-4 h-4 mr-1" />
              )}
              Test starten
            </Button>
            <Button variant="outline" onClick={() => { setTestMode(false); setTestResult(null); }}>
              <X className="w-4 h-4 mr-1" />
              Schließen
            </Button>
          </div>

          {testResult && (
            <div className="mt-4 p-3 rounded-lg border bg-background">
              <div className={`font-semibold mb-2 ${testResult.passed ? "text-emerald-600" : "text-amber-600"}`}>
                {testResult.passed ? "✅ Alle Checks bestanden!" : `⚠️ ${testResult.missing.length} fehlende Posten gefunden:`}
              </div>
              {testResult.missing.length > 0 && (
                <ul className="space-y-1 text-sm">
                  {testResult.missing.map((m, idx) => (
                    <li key={idx} className="flex items-center gap-2">
                      <span className={severityConfig[m.severity as keyof typeof severityConfig]?.icon || "🟡"}>
                      </span>
                      <strong>{m.name}</strong>
                      <span className="text-muted-foreground">— {m.reason}</span>
                    </li>
                  ))}
                </ul>
              )}
              <div className="mt-3 text-xs text-muted-foreground">
                <strong>Geprüfte Regeln:</strong> {testResult.rules_fired.length} | 
                <strong className="ml-2">Ausgelöst:</strong> {testResult.rules_fired.filter(r => r.hit).length}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Info-Box */}
      <div className="p-3 rounded-lg bg-blue-50 border border-blue-200 text-blue-700 text-sm">
        <div className="flex items-start gap-2">
          <Info className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <div>
            <strong>So funktioniert's:</strong> Der Wächter prüft deine Angebotspositionen und 
            schlägt Alarm, wenn typische Materialien fehlen. Bei <strong>Standard-Regeln</strong> 
            basiert die Logik auf dem Kontext (Untergrund, Fläche etc.). Bei <strong>eigenen Regeln</strong> 
            wird geprüft, ob mindestens eines deiner Keywords in den Positionen vorkommt.
          </div>
        </div>
      </div>

      {/* Kategorisierte Regeln */}
      <div className="space-y-4">
        {sortedCategories.map((category) => (
          <Card key={category} className="overflow-hidden">
            <button
              type="button"
              onClick={() => toggleCategory(category)}
              className="w-full px-4 py-3 flex items-center justify-between bg-muted/30 hover:bg-muted/50 transition-colors"
            >
              <div className="flex items-center gap-2">
                <span className="text-lg">{CATEGORY_ICONS[category] || "📋"}</span>
                <span className="font-semibold">{category}</span>
                <Badge variant="secondary" className="ml-2">
                  {groupedItems[category].length}
                </Badge>
              </div>
              {expandedCategories.has(category) ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )}
            </button>
            
            {expandedCategories.has(category) && (
              <div className="divide-y">
                {groupedItems[category].map((item) => {
                  const isSelected = selectedId === item.id;
                  const isBuiltin = item.origin === "builtin";
                  const severity = severityConfig[item.severity as keyof typeof severityConfig] || severityConfig.medium;
                  
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => handleSelect(item.id)}
                      className={`w-full px-4 py-3 text-left transition-colors hover:bg-muted/30 ${
                        isSelected ? "bg-primary/5 border-l-2 border-l-primary" : ""
                      } ${!item.enabled ? "opacity-50" : ""}`}
                    >
                      <div className="flex flex-wrap items-center gap-2 mb-1">
                        <span className="font-medium">{item.name || "Unbenannt"}</span>
                        <Badge className={severity.color}>{severity.label}</Badge>
                        {!item.enabled && <Badge variant="outline">Deaktiviert</Badge>}
                        {isBuiltin ? (
                          <Badge variant="outline" className="text-xs">Standard</Badge>
                        ) : (
                          <Badge variant="default" className="text-xs">Custom</Badge>
                        )}
                      </div>
                      {item.description && (
                        <p className="text-sm text-muted-foreground line-clamp-1">{item.description}</p>
                      )}
                      {item.keywordsText && (
                        <p className="text-xs text-muted-foreground mt-1">
                          Keywords: {item.keywordsText.substring(0, 60)}{item.keywordsText.length > 60 ? "…" : ""}
                        </p>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </Card>
        ))}
      </div>

      {/* Custom Regel hinzufügen */}
      <Card className="p-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h4 className="font-semibold">Eigene Regel erstellen</h4>
            <p className="text-sm text-muted-foreground">
              Füge typische Materialien hinzu, die du nicht vergessen möchtest.
            </p>
          </div>
          <Button onClick={handleAddClick} variant="outline">
            <Plus className="w-4 h-4 mr-1" />
            Neue Regel
          </Button>
        </div>
      </Card>

      {/* Bearbeitungsformular */}
      {isFormVisible && (
        <Card className="p-5 border-primary/30">
          <div className="flex items-center justify-between mb-4">
            <h4 className="font-semibold flex items-center gap-2">
              <PencilLine className="w-4 h-4" />
              {selectedId ? "Regel bearbeiten" : "Neue Regel erstellen"}
            </h4>
            <Button variant="ghost" size="sm" onClick={() => { setIsFormVisible(false); setSelectedId(null); }}>
              <X className="w-4 h-4" />
            </Button>
          </div>

          <div className="space-y-4">
            {/* Name & Status */}
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">Bezeichnung *</Label>
                <Input
                  value={formItem.name}
                  onChange={(e) => handleFormChange({ name: e.target.value })}
                  placeholder="z.B. Brandschutzfarbe F30"
                  className="mt-1"
                />
              </div>
              <div className="flex gap-4">
                <div className="flex-1">
                  <Label className="text-xs uppercase tracking-wide text-muted-foreground">Priorität</Label>
                  <select
                    value={formItem.severity ?? "medium"}
                    onChange={(e) => handleFormChange({ severity: e.target.value as EditableMaterial["severity"] })}
                    className="w-full mt-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    <option value="high">🔴 Hoch (kritisch)</option>
                    <option value="medium">🟡 Mittel (wichtig)</option>
                    <option value="low">🟢 Niedrig (optional)</option>
                  </select>
                </div>
                <div className="flex flex-col items-center justify-end pb-2">
                  <Label className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Aktiv</Label>
                  <Switch 
                    checked={formItem.enabled ?? true} 
                    onCheckedChange={(checked) => handleFormChange({ enabled: checked })} 
                  />
                </div>
              </div>
            </div>

            {/* Keywords (nur für Custom) */}
            {formItem.origin === "custom" && (
              <div>
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                  Schlüsselwörter (für Keyword-Suche)
                </Label>
                <Textarea
                  rows={2}
                  value={formItem.keywordsText}
                  placeholder="brandschutz, f30, feuerschutz, brandschutzfarbe"
                  onChange={(e) => handleFormChange({ keywordsText: e.target.value })}
                  className="mt-1 font-mono text-sm"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Kommagetrennt. Wenn KEINES dieser Wörter in den Positionen vorkommt, wird diese Regel auslösen.
                </p>
              </div>
            )}

            {/* Beschreibung & Begründung */}
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">Beschreibung</Label>
                <Textarea
                  rows={2}
                  value={formItem.description ?? ""}
                  onChange={(e) => handleFormChange({ description: e.target.value })}
                  placeholder="Was prüft diese Regel?"
                  className="mt-1"
                />
              </div>
              <div>
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">Begründung / Hinweis</Label>
                <Textarea
                  rows={2}
                  value={formItem.reason ?? ""}
                  onChange={(e) => handleFormChange({ reason: e.target.value })}
                  placeholder="Warum ist das Material wichtig?"
                  className="mt-1"
                />
              </div>
            </div>

            {/* Kategorie, Einheit, Menge */}
            <div className="grid gap-4 md:grid-cols-3">
              <div>
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">Kategorie</Label>
                <select
                  value={formItem.category ?? "Benutzerdefiniert"}
                  onChange={(e) => handleFormChange({ category: e.target.value })}
                  className="w-full mt-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  {CATEGORY_ORDER.map((cat) => (
                    <option key={cat} value={cat}>{CATEGORY_ICONS[cat]} {cat}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">Einheit</Label>
                <Input
                  value={formItem.einheit ?? ""}
                  onChange={(e) => handleFormChange({ einheit: e.target.value })}
                  placeholder="z.B. L, kg, Stück, Rolle"
                  className="mt-1"
                />
              </div>
              <div>
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">Standard-Menge</Label>
                <Input
                  type="number"
                  step="0.1"
                  value={formItem.quantityText}
                  onChange={(e) => handleFormChange({ quantityText: e.target.value })}
                  placeholder="optional"
                  className="mt-1"
                />
              </div>
            </div>

            {/* Aktionen */}
            <div className="flex flex-wrap justify-between gap-3 pt-2 border-t">
              <div>
                {formItem.origin === "custom" && selectedId && (
                  <Button
                    variant="outline"
                    className="border-destructive/40 text-destructive hover:bg-destructive/10"
                    onClick={() => handleDelete(selectedId)}
                  >
                    <Trash2 className="w-4 h-4 mr-1" />
                    Löschen
                  </Button>
                )}
              </div>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => { setIsFormVisible(false); setSelectedId(null); }}>
                  Abbrechen
                </Button>
                <Button onClick={handleFormCommit}>
                  <Check className="w-4 h-4 mr-1" />
                  {selectedId ? "Übernehmen" : "Hinzufügen"}
                </Button>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Speichern-Hinweis */}
      <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50 border">
        <p className="text-sm text-muted-foreground">
          Änderungen werden erst wirksam, wenn du auf <strong>„Speichern"</strong> klickst.
        </p>
        <Button onClick={save} disabled={saving || loading}>
          <Save className="w-4 h-4 mr-1" />
          Alle Änderungen speichern
        </Button>
      </div>
    </div>
  );
};

export default GuardMaterialsEditor;
