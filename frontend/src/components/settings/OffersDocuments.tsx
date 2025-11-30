import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/components/ui/use-toast";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface OffersDocumentsProps {
  onBack: () => void;
}

interface DocumentSettings {
  archive: {
    autoArchiveDays: number;
  };
  retention: {
    offers: number;
    invoices: number;
  };
}

const defaultSettings: DocumentSettings = {
  archive: {
    autoArchiveDays: 30,
  },
  retention: {
    offers: 2,
    invoices: 10,
  },
};

export default function OffersDocuments({ onBack }: OffersDocumentsProps) {
  const { toast } = useToast();
  const [settings, setSettings] = useState<DocumentSettings>(defaultSettings);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("kalkulai_settings_offers_documents");
    if (saved) {
      try {
        setSettings({ ...defaultSettings, ...JSON.parse(saved) });
      } catch (e) {
        console.error("Failed to load document settings", e);
      }
    }
  }, []);

  const handleSave = () => {
    localStorage.setItem("kalkulai_settings_offers_documents", JSON.stringify(settings));
    setHasChanges(false);
    toast({
      title: "Einstellungen gespeichert",
      description: "Deine Dokumentenverwaltungs-Einstellungen wurden erfolgreich gespeichert.",
    });
  };

  const updateSetting = <K extends keyof DocumentSettings>(key: K, value: DocumentSettings[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-[#111827] mb-2">Dokumentenverwaltung</h1>
        <p className="text-sm text-[#6B7280]">Archivierung, Standardordner und Aufbewahrungsfristen.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Archivierungseinstellungen</CardTitle>
          <CardDescription>Automatische Archivierung von Dokumenten</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="archive-days">Automatisch archivieren nach (Tagen)</Label>
            <Input
              id="archive-days"
              type="number"
              value={settings.archive.autoArchiveDays}
              onChange={(e) =>
                updateSetting("archive", { autoArchiveDays: parseInt(e.target.value) || 0 })
              }
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Aufbewahrungsfristen</CardTitle>
          <CardDescription>Gesetzliche und betriebliche Aufbewahrungsfristen</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="retention-offers">Angebote (Jahre)</Label>
            <Select
              value={settings.retention.offers.toString()}
              onValueChange={(v) => updateSetting("retention", { ...settings.retention, offers: parseInt(v) })}
            >
              <SelectTrigger id="retention-offers">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1">1 Jahr</SelectItem>
                <SelectItem value="2">2 Jahre</SelectItem>
                <SelectItem value="5">5 Jahre</SelectItem>
                <SelectItem value="10">10 Jahre</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="retention-invoices">Rechnungen (Jahre)</Label>
            <Select
              value={settings.retention.invoices.toString()}
              onValueChange={(v) => updateSetting("retention", { ...settings.retention, invoices: parseInt(v) })}
            >
              <SelectTrigger id="retention-invoices">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="10">Gesetzlich 10 Jahre</SelectItem>
                <SelectItem value="5">5 Jahre</SelectItem>
                <SelectItem value="2">2 Jahre</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Standardordner-Struktur</CardTitle>
          <CardDescription>Organisation deiner Dokumente</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">Diese Funktion wird in Kürze verfügbar sein.</div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Dokumenten-Tags</CardTitle>
          <CardDescription>Verwaltete Tags für die Kategorisierung</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">Diese Funktion wird in Kürze verfügbar sein.</div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={!hasChanges}>
          Speichern
        </Button>
      </div>
    </div>
  );
}

