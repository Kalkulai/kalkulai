import { useState, useEffect, useCallback } from "react";
import { Plus, Trash2, Save, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export type OfferPosition = {
  nr: number;
  name: string;
  menge: number;
  einheit: string;
  epreis: number;
  gesamtpreis?: number;
};

type Props = {
  positions: OfferPosition[];
  onSave: (positions: OfferPosition[]) => void;
  onCancel: () => void;
};

export default function OfferEditor({ positions: initialPositions, onSave, onCancel }: Props) {
  const [positions, setPositions] = useState<OfferPosition[]>([]);

  useEffect(() => {
    setPositions(
      initialPositions.map((p, idx) => ({
        ...p,
        nr: p.nr || idx + 1,
        gesamtpreis: (p.menge || 0) * (p.epreis || 0),
      }))
    );
  }, [initialPositions]);

  const recalculate = useCallback((pos: OfferPosition[]): OfferPosition[] => {
    return pos.map((p, idx) => ({
      ...p,
      nr: idx + 1,
      gesamtpreis: Math.round((p.menge || 0) * (p.epreis || 0) * 100) / 100,
    }));
  }, []);

  const updatePosition = (index: number, field: keyof OfferPosition, value: string | number) => {
    setPositions((prev) => {
      const updated = [...prev];
      const pos = { ...updated[index] };

      if (field === "menge" || field === "epreis") {
        const numVal = typeof value === "string" ? parseFloat(value) || 0 : value;
        (pos as any)[field] = numVal;
      } else if (field === "name" || field === "einheit") {
        (pos as any)[field] = String(value);
      }

      updated[index] = pos;
      return recalculate(updated);
    });
  };

  const addPosition = () => {
    setPositions((prev) =>
      recalculate([
        ...prev,
        {
          nr: prev.length + 1,
          name: "",
          menge: 1,
          einheit: "Stk",
          epreis: 0,
          gesamtpreis: 0,
        },
      ])
    );
  };

  const removePosition = (index: number) => {
    setPositions((prev) => recalculate(prev.filter((_, i) => i !== index)));
  };

  const handleSave = () => {
    onSave(recalculate(positions));
  };

  const nettoSum = positions.reduce((sum, p) => sum + (p.gesamtpreis || 0), 0);
  const vatRate = 0.19;
  const vatAmount = Math.round(nettoSum * vatRate * 100) / 100;
  const bruttoSum = Math.round((nettoSum + vatAmount) * 100) / 100;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-5 pb-4 border-b border-border">
        <h3 className="text-xl font-semibold text-foreground">Angebot bearbeiten</h3>
        <div className="flex gap-3">
          <Button variant="ghost" size="sm" onClick={onCancel} className="text-muted-foreground">
            <X className="w-4 h-4 mr-1.5" />
            Abbrechen
          </Button>
          <Button size="sm" onClick={handleSave} className="px-4">
            <Save className="w-4 h-4 mr-1.5" />
            Übernehmen
          </Button>
        </div>
      </div>

      {/* Scrollable Positions Area */}
      <div className="flex-1 overflow-y-auto space-y-3 pr-1">
        {positions.length === 0 ? (
          <div className="text-center text-muted-foreground py-12 border border-dashed rounded-lg">
            Keine Positionen vorhanden. Füge eine neue Position hinzu.
          </div>
        ) : (
          positions.map((pos, idx) => (
            <div
              key={`${pos.nr}-${idx}`}
              className="group border border-border rounded-lg p-4 hover:border-primary/30 hover:bg-muted/30 transition-colors"
            >
              {/* Row 1: Nr + Name + Delete */}
              <div className="flex items-start gap-3 mb-3">
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-muted flex items-center justify-center text-sm font-medium text-muted-foreground">
                  {pos.nr}
                </div>
                <div className="flex-1">
                  <Input
                    value={pos.name}
                    onChange={(e) => updatePosition(idx, "name", e.target.value)}
                    placeholder="Produktbezeichnung eingeben..."
                    className="h-10 text-base font-medium"
                  />
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 opacity-0 group-hover:opacity-100 text-destructive hover:text-destructive hover:bg-destructive/10 flex-shrink-0"
                  onClick={() => removePosition(idx)}
                  title="Position löschen"
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>

              {/* Row 2: Menge, Einheit, EP, GP */}
              <div className="grid grid-cols-4 gap-3 pl-11">
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">Menge</label>
                  <Input
                    type="number"
                    value={pos.menge}
                    onChange={(e) => updatePosition(idx, "menge", e.target.value)}
                    className="h-9 text-sm"
                    min={0}
                    step="0.01"
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">Einheit</label>
                  <Input
                    value={pos.einheit}
                    onChange={(e) => updatePosition(idx, "einheit", e.target.value)}
                    placeholder="Stk"
                    className="h-9 text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">Einzelpreis (€)</label>
                  <Input
                    type="number"
                    value={pos.epreis}
                    onChange={(e) => updatePosition(idx, "epreis", e.target.value)}
                    className="h-9 text-sm"
                    min={0}
                    step="0.01"
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">Gesamt (€)</label>
                  <div className="h-9 flex items-center px-3 bg-muted/50 rounded-md text-sm font-semibold tabular-nums">
                    {(pos.gesamtpreis || 0).toFixed(2)}
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Add Position Button */}
      <div className="mt-4 pt-3">
        <Button variant="outline" onClick={addPosition} className="w-full h-10">
          <Plus className="w-4 h-4 mr-2" />
          Position hinzufügen
        </Button>
      </div>

      {/* Summary */}
      <div className="mt-4 pt-4 border-t border-border">
        <div className="bg-muted/40 rounded-lg p-4 space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Netto</span>
            <span className="font-medium tabular-nums">{nettoSum.toFixed(2)} €</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">MwSt. (19%)</span>
            <span className="font-medium tabular-nums">{vatAmount.toFixed(2)} €</span>
          </div>
          <div className="flex justify-between text-lg font-bold pt-2 border-t border-border">
            <span>Brutto</span>
            <span className="tabular-nums">{bruttoSum.toFixed(2)} €</span>
          </div>
        </div>
      </div>
    </div>
  );
}
