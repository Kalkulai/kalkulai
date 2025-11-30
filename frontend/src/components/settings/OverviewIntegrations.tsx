import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

interface OverviewIntegrationsProps {
  onBack: () => void;
}

interface ConnectedApp {
  id: string;
  name: string;
  description: string;
  connected: boolean;
}

const availableApps: ConnectedApp[] = [
  { id: "datev", name: "DATEV", description: "Buchhaltungssoftware", connected: false },
  { id: "zapier", name: "Zapier", description: "Automatisierung", connected: false },
  { id: "make", name: "Make", description: "Automatisierung", connected: false },
];

export default function OverviewIntegrations({ onBack }: OverviewIntegrationsProps) {
  const { toast } = useToast();
  const [apps, setApps] = useState<ConnectedApp[]>(availableApps);
  const [apiKeys, setApiKeys] = useState<Array<{ id: string; name: string; key: string; created: string }>>([]);
  const [webhooks, setWebhooks] = useState<Array<{ id: string; url: string; events: string[]; active: boolean }>>([]);

  const handleConnect = (appId: string) => {
    setApps((prev) => prev.map((app) => (app.id === appId ? { ...app, connected: true } : app)));
    toast({
      title: "Verbunden",
      description: "Die App wurde erfolgreich verbunden.",
    });
  };

  const handleDisconnect = (appId: string) => {
    setApps((prev) => prev.map((app) => (app.id === appId ? { ...app, connected: false } : app)));
    toast({
      title: "Getrennt",
      description: "Die App wurde erfolgreich getrennt.",
    });
  };

  const handleGenerateApiKey = () => {
    const newKey = {
      id: Date.now().toString(),
      name: `API Key ${apiKeys.length + 1}`,
      key: `kalkulai_${Math.random().toString(36).substring(2, 15)}${Math.random().toString(36).substring(2, 15)}`,
      created: new Date().toLocaleDateString("de-DE"),
    };
    setApiKeys([...apiKeys, newKey]);
    toast({
      title: "API-Key erstellt",
      description: "Der neue API-Key wurde erfolgreich generiert.",
    });
  };

  const handleAddWebhook = () => {
    toast({
      title: "Webhook hinzufügen",
      description: "Diese Funktion wird in Kürze verfügbar sein.",
    });
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-[#111827] mb-2">Integrationen</h1>
        <p className="text-sm text-[#6B7280]">Verbundene Apps, API-Zugriff und Webhooks konfigurieren.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Verbundene Apps</CardTitle>
          <CardDescription>Verwaltete Integrationen mit externen Diensten</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {apps.map((app) => (
              <Card key={app.id} className={app.connected ? "border-primary" : ""}>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">{app.name}</CardTitle>
                    {app.connected && <Badge>Verbunden</Badge>}
                  </div>
                  <CardDescription>{app.description}</CardDescription>
                </CardHeader>
                <CardContent>
                  {app.connected ? (
                    <Button variant="outline" size="sm" onClick={() => handleDisconnect(app.id)}>
                      Trennen
                    </Button>
                  ) : (
                    <Button size="sm" onClick={() => handleConnect(app.id)}>
                      Verbinden
                    </Button>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>API-Zugriff</CardTitle>
              <CardDescription>Verwaltete API-Keys für programmatischen Zugriff</CardDescription>
            </div>
            <Button onClick={handleGenerateApiKey}>API-Key generieren</Button>
          </div>
        </CardHeader>
        <CardContent>
          {apiKeys.length === 0 ? (
            <div className="text-sm text-muted-foreground">Noch keine API-Keys vorhanden.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Key</TableHead>
                  <TableHead>Erstellt</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {apiKeys.map((key) => (
                  <TableRow key={key.id}>
                    <TableCell>{key.name}</TableCell>
                    <TableCell className="font-mono text-xs">{key.key}</TableCell>
                    <TableCell>{key.created}</TableCell>
                    <TableCell>
                      <Button variant="ghost" size="sm">
                        Löschen
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Webhooks</CardTitle>
              <CardDescription>Automatische Benachrichtigungen an externe URLs</CardDescription>
            </div>
            <Button onClick={handleAddWebhook}>Webhook hinzufügen</Button>
          </div>
        </CardHeader>
        <CardContent>
          {webhooks.length === 0 ? (
            <div className="text-sm text-muted-foreground">Noch keine Webhooks konfiguriert.</div>
          ) : (
            <div className="space-y-2">
              {webhooks.map((webhook) => (
                <div key={webhook.id} className="flex items-center justify-between p-3 border rounded-lg">
                  <div>
                    <p className="font-medium">{webhook.url}</p>
                    <p className="text-sm text-muted-foreground">{webhook.events.join(", ")}</p>
                  </div>
                  <Badge variant={webhook.active ? "default" : "secondary"}>{webhook.active ? "Aktiv" : "Inaktiv"}</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Zapier / Make Integration</CardTitle>
          <CardDescription>Automatisiere deine Workflows</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">Zapier- und Make-Integrationen werden in Kürze verfügbar sein.</div>
        </CardContent>
      </Card>
    </div>
  );
}

