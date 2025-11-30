import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/use-toast";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

interface OverviewNotificationsProps {
  onBack: () => void;
}

interface NotificationSettings {
  email: {
    newOrders: boolean;
    payments: boolean;
    dueInvoices: boolean;
    teamMentions: boolean;
  };
  inApp: boolean;
  teamUpdates: boolean;
  push: boolean;
  doNotDisturb: {
    enabled: boolean;
    startTime: string;
    endTime: string;
  };
}

const defaultSettings: NotificationSettings = {
  email: {
    newOrders: true,
    payments: true,
    dueInvoices: true,
    teamMentions: true,
  },
  inApp: true,
  teamUpdates: true,
  push: false,
  doNotDisturb: {
    enabled: false,
    startTime: "22:00",
    endTime: "08:00",
  },
};

export default function OverviewNotifications({ onBack }: OverviewNotificationsProps) {
  const { toast } = useToast();
  const [settings, setSettings] = useState<NotificationSettings>(defaultSettings);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("kalkulai_settings_notifications");
    if (saved) {
      try {
        setSettings({ ...defaultSettings, ...JSON.parse(saved) });
      } catch (e) {
        console.error("Failed to load notification settings", e);
      }
    }
  }, []);

  const handleSave = () => {
    localStorage.setItem("kalkulai_settings_notifications", JSON.stringify(settings));
    setHasChanges(false);
    toast({
      title: "Einstellungen gespeichert",
      description: "Deine Benachrichtigungseinstellungen wurden erfolgreich gespeichert.",
    });
  };

  const updateEmailSetting = (key: keyof NotificationSettings["email"], value: boolean) => {
    setSettings((prev) => ({
      ...prev,
      email: { ...prev.email, [key]: value },
    }));
    setHasChanges(true);
  };

  const updateSetting = <K extends keyof NotificationSettings>(key: K, value: NotificationSettings[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-[#111827] mb-2">Benachrichtigungen</h1>
        <p className="text-sm text-[#6B7280]">E-Mail-, In-App- und Team-Updates gezielt konfigurieren.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>E-Mail-Benachrichtigungen</CardTitle>
          <CardDescription>Wähle aus, bei welchen Events du per E-Mail benachrichtigt werden möchtest.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Neue Aufträge</Label>
              <p className="text-sm text-muted-foreground">Benachrichtigung bei neuen Aufträgen</p>
            </div>
            <Switch checked={settings.email.newOrders} onCheckedChange={(v) => updateEmailSetting("newOrders", v)} />
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Zahlungseingänge</Label>
              <p className="text-sm text-muted-foreground">Benachrichtigung bei erhaltenen Zahlungen</p>
            </div>
            <Switch checked={settings.email.payments} onCheckedChange={(v) => updateEmailSetting("payments", v)} />
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Fällige Rechnungen</Label>
              <p className="text-sm text-muted-foreground">Erinnerung bei fälligen Rechnungen</p>
            </div>
            <Switch checked={settings.email.dueInvoices} onCheckedChange={(v) => updateEmailSetting("dueInvoices", v)} />
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Team-Erwähnungen</Label>
              <p className="text-sm text-muted-foreground">Benachrichtigung bei Erwähnungen im Team</p>
            </div>
            <Switch checked={settings.email.teamMentions} onCheckedChange={(v) => updateEmailSetting("teamMentions", v)} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>In-App-Benachrichtigungen</CardTitle>
          <CardDescription>Dezente Hinweise direkt in der Anwendung</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>In-App-Hinweise aktivieren</Label>
              <p className="text-sm text-muted-foreground">Zeige Benachrichtigungen in der Anwendung</p>
            </div>
            <Switch checked={settings.inApp} onCheckedChange={(v) => updateSetting("inApp", v)} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Team-Updates</CardTitle>
          <CardDescription>Wöchentliche Zusammenfassungen und Team-Aktivitäten</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Team-Updates aktivieren</Label>
              <p className="text-sm text-muted-foreground">Wöchentliche Zusammenfassung per E-Mail</p>
            </div>
            <Switch checked={settings.teamUpdates} onCheckedChange={(v) => updateSetting("teamUpdates", v)} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Push-Benachrichtigungen</CardTitle>
          <CardDescription>Browser-Benachrichtigungen aktivieren</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Push-Benachrichtigungen aktivieren</Label>
              <p className="text-sm text-muted-foreground">Erhalte Benachrichtigungen auch außerhalb der App</p>
            </div>
            <Switch checked={settings.push} onCheckedChange={(v) => updateSetting("push", v)} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Benachrichtigungs-Zeitplan</CardTitle>
          <CardDescription>Nicht stören-Zeiten festlegen</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Nicht stören aktivieren</Label>
              <p className="text-sm text-muted-foreground">Pausiere Benachrichtigungen in bestimmten Zeiten</p>
            </div>
            <Switch
              checked={settings.doNotDisturb.enabled}
              onCheckedChange={(v) => updateSetting("doNotDisturb", { ...settings.doNotDisturb, enabled: v })}
            />
          </div>
          {settings.doNotDisturb.enabled && (
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="startTime">Von</Label>
                <Input
                  id="startTime"
                  type="time"
                  value={settings.doNotDisturb.startTime}
                  onChange={(e) =>
                    updateSetting("doNotDisturb", { ...settings.doNotDisturb, startTime: e.target.value })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="endTime">Bis</Label>
                <Input
                  id="endTime"
                  type="time"
                  value={settings.doNotDisturb.endTime}
                  onChange={(e) => updateSetting("doNotDisturb", { ...settings.doNotDisturb, endTime: e.target.value })}
                />
              </div>
            </div>
          )}
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

