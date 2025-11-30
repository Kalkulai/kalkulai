import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import GuardMaterialsEditor from "@/components/GuardMaterialsEditor";
import { useState } from "react";

interface OffersGuardProps {
  onBack: () => void;
}

export default function OffersGuard({ onBack }: OffersGuardProps) {
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-[#111827] mb-2">Vergessener Wächter</h1>
        <p className="text-sm text-[#6B7280]">
          Lege fest, welche Posten dein Wächter bei der Angebotserstellung zusätzlich vorschlagen soll.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardDescription>
            Der Wächter prüft deine Angebotspositionen und schlägt Alarm, wenn typische Materialien fehlen. Bei Standard-Regeln basiert die Logik auf dem Kontext (Untergrund, Fläche etc.). Bei eigenen Regeln wird geprüft, ob mindestens eines deiner Keywords in den Positionen vorkommt.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="max-h-[65vh] overflow-y-auto pr-1">
            <GuardMaterialsEditor refreshSignal={refreshKey} />
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <p className="text-xs text-muted-foreground">
          Änderungen hier wirken sich direkt auf deine lokale Datenbank aus.
        </p>
      </div>
    </div>
  );
}

