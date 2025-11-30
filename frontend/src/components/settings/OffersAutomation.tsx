import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/components/ui/use-toast";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface OffersAutomationProps {
  onBack: () => void;
}

interface AutomationSettings {
  invoice: {
    autoNumbering: boolean;
    format: string;
    nextNumber: string;
  };
  offer: {
    autoNumbering: boolean;
    format: string;
    nextNumber: string;
  };
  paymentTerms: {
    defaultDays: number;
  };
  reminders: {
    autoSend: boolean;
    daysAfterDue: number;
  };
  dunning: {
    firstAfterDays: number;
    secondAfterDays: number;
  };
}

const defaultSettings: AutomationSettings = {
  invoice: {
    autoNumbering: true,
    format: "{YEAR}-{NUMBER}",
    nextNumber: "1",
  },
  offer: {
    autoNumbering: true,
    format: "{YEAR}-{NUMBER}",
    nextNumber: "1",
  },
  paymentTerms: {
    defaultDays: 14,
  },
  reminders: {
    autoSend: false,
    daysAfterDue: 7,
  },
  dunning: {
    firstAfterDays: 14,
    secondAfterDays: 28,
  },
};

export default function OffersAutomation({ onBack }: OffersAutomationProps) {
  const { toast } = useToast();
  const [settings, setSettings] = useState<AutomationSettings>(defaultSettings);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("kalkulai_settings_offers_automation");
    if (saved) {
      try {
        setSettings({ ...defaultSettings, ...JSON.parse(saved) });
      } catch (e) {
        console.error("Failed to load automation settings", e);
      }
    }
  }, []);

  const handleSave = () => {
    localStorage.setItem("kalkulai_settings_offers_automation", JSON.stringify(settings));
    setHasChanges(false);
    toast({
      title: "Einstellungen gespeichert",
      description: "Deine Automatisierungs-Einstellungen wurden erfolgreich gespeichert.",
    });
  };

  const updateSetting = <K extends keyof AutomationSettings>(key: K, value: AutomationSettings[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-[#111827] mb-2">Automatisierung</h1>
        <p className="text-sm text-[#6B7280]">
          Rechnungsnummern, Fälligkeitsfristen und automatische Mahnungen konfigurieren.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Rechnungsnummern</CardTitle>
          <CardDescription>Automatische Vergabe und Formatierung</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Automatische Vergabe</Label>
              <p className="text-sm text-muted-foreground">Rechnungsnummern automatisch generieren</p>
            </div>
            <Switch
              checked={settings.invoice.autoNumbering}
              onCheckedChange={(v) => updateSetting("invoice", { ...settings.invoice, autoNumbering: v })}
            />
          </div>
          {settings.invoice.autoNumbering && (
            <>
              <div className="space-y-2">
                <Label htmlFor="invoice-format">Format</Label>
                <Input
                  id="invoice-format"
                  value={settings.invoice.format}
                  onChange={(e) => updateSetting("invoice", { ...settings.invoice, format: e.target.value })}
                  placeholder="{YEAR}-{NUMBER}"
                />
                <p className="text-xs text-muted-foreground">Verfügbare Platzhalter: {"{YEAR}"}, {"{NUMBER}"}, {"{MONTH}"}</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="invoice-next">Nächste Nummer</Label>
                <Input
                  id="invoice-next"
                  value={settings.invoice.nextNumber}
                  onChange={(e) => updateSetting("invoice", { ...settings.invoice, nextNumber: e.target.value })}
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Angebotsnummern</CardTitle>
          <CardDescription>Automatische Vergabe und Formatierung</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Automatische Vergabe</Label>
              <p className="text-sm text-muted-foreground">Angebotsnummern automatisch generieren</p>
            </div>
            <Switch
              checked={settings.offer.autoNumbering}
              onCheckedChange={(v) => updateSetting("offer", { ...settings.offer, autoNumbering: v })}
            />
          </div>
          {settings.offer.autoNumbering && (
            <>
              <div className="space-y-2">
                <Label htmlFor="offer-format">Format</Label>
                <Input
                  id="offer-format"
                  value={settings.offer.format}
                  onChange={(e) => updateSetting("offer", { ...settings.offer, format: e.target.value })}
                  placeholder="{YEAR}-{NUMBER}"
                />
                <p className="text-xs text-muted-foreground">Verfügbare Platzhalter: {"{YEAR}"}, {"{NUMBER}"}, {"{MONTH}"}</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="offer-next">Nächste Nummer</Label>
                <Input
                  id="offer-next"
                  value={settings.offer.nextNumber}
                  onChange={(e) => updateSetting("offer", { ...settings.offer, nextNumber: e.target.value })}
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Fälligkeitsfristen</CardTitle>
          <CardDescription>Standard-Zahlungsziele</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <Label htmlFor="payment-terms">Standard-Fälligkeit</Label>
            <Select
              value={settings.paymentTerms.defaultDays.toString()}
              onValueChange={(v) => updateSetting("paymentTerms", { defaultDays: parseInt(v) })}
            >
              <SelectTrigger id="payment-terms">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7">7 Tage</SelectItem>
                <SelectItem value="14">14 Tage</SelectItem>
                <SelectItem value="30">30 Tage</SelectItem>
                <SelectItem value="60">60 Tage</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Zahlungserinnerungen</CardTitle>
          <CardDescription>Automatische Erinnerungen bei überfälligen Rechnungen</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Automatisch senden</Label>
              <p className="text-sm text-muted-foreground">Erinnerungen automatisch versenden</p>
            </div>
            <Switch
              checked={settings.reminders.autoSend}
              onCheckedChange={(v) => updateSetting("reminders", { ...settings.reminders, autoSend: v })}
            />
          </div>
          {settings.reminders.autoSend && (
            <div className="space-y-2">
              <Label htmlFor="reminder-days">Tage nach Fälligkeit</Label>
              <Input
                id="reminder-days"
                type="number"
                value={settings.reminders.daysAfterDue}
                onChange={(e) =>
                  updateSetting("reminders", { ...settings.reminders, daysAfterDue: parseInt(e.target.value) || 0 })
                }
              />
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Automatische Mahnungen</CardTitle>
          <CardDescription>Mahnungen automatisch versenden</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="dunning-first">1. Mahnung nach (Tagen)</Label>
            <Input
              id="dunning-first"
              type="number"
              value={settings.dunning.firstAfterDays}
              onChange={(e) =>
                updateSetting("dunning", { ...settings.dunning, firstAfterDays: parseInt(e.target.value) || 0 })
              }
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="dunning-second">2. Mahnung nach (Tagen)</Label>
            <Input
              id="dunning-second"
              type="number"
              value={settings.dunning.secondAfterDays}
              onChange={(e) =>
                updateSetting("dunning", { ...settings.dunning, secondAfterDays: parseInt(e.target.value) || 0 })
              }
            />
          </div>
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

