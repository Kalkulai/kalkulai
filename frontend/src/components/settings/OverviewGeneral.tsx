import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/use-toast";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface OverviewGeneralProps {
  onBack: () => void;
}

interface GeneralSettings {
  language: string;
  timeFormat: "12h" | "24h";
  dateFormat: string;
  currency: string;
  theme: "light" | "dark" | "auto";
}

const defaultSettings: GeneralSettings = {
  language: "de",
  timeFormat: "24h",
  dateFormat: "DD.MM.YYYY",
  currency: "EUR",
  theme: "light",
};

export default function OverviewGeneral({ onBack }: OverviewGeneralProps) {
  const { toast } = useToast();
  const [settings, setSettings] = useState<GeneralSettings>(defaultSettings);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("kalkulai_settings_general");
    if (saved) {
      try {
        setSettings({ ...defaultSettings, ...JSON.parse(saved) });
      } catch (e) {
        console.error("Failed to load general settings", e);
      }
    }
  }, []);

  const handleSave = () => {
    localStorage.setItem("kalkulai_settings_general", JSON.stringify(settings));
    setHasChanges(false);
    toast({
      title: "Einstellungen gespeichert",
      description: "Deine allgemeinen Einstellungen wurden erfolgreich gespeichert.",
    });
  };

  const updateSetting = <K extends keyof GeneralSettings>(key: K, value: GeneralSettings[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-[#111827] mb-2">Allgemeine Einstellungen</h1>
        <p className="text-sm text-[#6B7280]">Sprache, Zeitformat und Darstellung der Oberfläche anpassen.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Basis-Einstellungen</CardTitle>
          <CardDescription>Gilt für dein gesamtes Konto – wirkt sich auf Darstellung und Hilfetexte aus.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <Label htmlFor="language">Sprache</Label>
              <Select value={settings.language} onValueChange={(value) => updateSetting("language", value)}>
                <SelectTrigger id="language">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="de">Deutsch</SelectItem>
                  <SelectItem value="en">Englisch</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="timeFormat">Zeitformat</Label>
              <Select value={settings.timeFormat} onValueChange={(value) => updateSetting("timeFormat", value as "12h" | "24h")}>
                <SelectTrigger id="timeFormat">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="12h">12 Stunden</SelectItem>
                  <SelectItem value="24h">24 Stunden</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="dateFormat">Datumsformat</Label>
              <Select value={settings.dateFormat} onValueChange={(value) => updateSetting("dateFormat", value)}>
                <SelectTrigger id="dateFormat">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="DD.MM.YYYY">DD.MM.YYYY</SelectItem>
                  <SelectItem value="MM/DD/YYYY">MM/DD/YYYY</SelectItem>
                  <SelectItem value="YYYY-MM-DD">YYYY-MM-DD</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="currency">Währung</Label>
              <Select value={settings.currency} onValueChange={(value) => updateSetting("currency", value)}>
                <SelectTrigger id="currency">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="EUR">EUR (€)</SelectItem>
                  <SelectItem value="USD">USD ($)</SelectItem>
                  <SelectItem value="CHF">CHF</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="theme">Oberflächenthema</Label>
              <Select value={settings.theme} onValueChange={(value) => updateSetting("theme", value as "light" | "dark" | "auto")}>
                <SelectTrigger id="theme">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="light">Hell</SelectItem>
                  <SelectItem value="dark">Dunkel</SelectItem>
                  <SelectItem value="auto">Automatisch</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex justify-end pt-4 border-t">
            <Button onClick={handleSave} disabled={!hasChanges}>
              Speichern
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

