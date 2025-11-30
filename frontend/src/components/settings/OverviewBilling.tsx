import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

interface OverviewBillingProps {
  onBack: () => void;
}

interface BillingSettings {
  currentPlan: {
    name: string;
    price: number;
    period: string;
  };
  paymentMethods: Array<{
    id: string;
    type: string;
    last4: string;
    expiry?: string;
  }>;
  invoices: Array<{
    id: string;
    date: string;
    amount: number;
    status: string;
  }>;
  usage: {
    documentsCreated: number;
    storageUsed: number;
    storageLimit: number;
  };
}

const defaultSettings: BillingSettings = {
  currentPlan: {
    name: "Pro",
    price: 29.99,
    period: "monatlich",
  },
  paymentMethods: [],
  invoices: [],
  usage: {
    documentsCreated: 0,
    storageUsed: 0,
    storageLimit: 1000,
  },
};

export default function OverviewBilling({ onBack }: OverviewBillingProps) {
  const { toast } = useToast();
  const [settings, setSettings] = useState<BillingSettings>(defaultSettings);

  useEffect(() => {
    const saved = localStorage.getItem("kalkulai_settings_billing");
    if (saved) {
      try {
        setSettings({ ...defaultSettings, ...JSON.parse(saved) });
      } catch (e) {
        console.error("Failed to load billing settings", e);
      }
    }
  }, []);

  const handleUpgrade = () => {
    toast({
      title: "Upgrade",
      description: "Upgrade-Funktion wird in Kürze verfügbar sein.",
    });
  };

  const handleAddPaymentMethod = () => {
    toast({
      title: "Zahlungsmethode hinzufügen",
      description: "Diese Funktion wird in Kürze verfügbar sein.",
    });
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-[#111827] mb-2">Abrechnung & Pläne</h1>
        <p className="text-sm text-[#6B7280]">Tarifübersicht, Rechnungsarchiv und Zahlungsmethoden einsehen.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Aktueller Plan</CardTitle>
          <CardDescription>Dein aktueller Tarif und Nutzungsübersicht</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-2xl font-semibold">{settings.currentPlan.name}</p>
              <p className="text-muted-foreground">
                {settings.currentPlan.price.toFixed(2)} € / {settings.currentPlan.period}
              </p>
            </div>
            <Button onClick={handleUpgrade}>Upgrade</Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Tarifübersicht</CardTitle>
          <CardDescription>Vergleiche die verfügbaren Pläne</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">Tarifvergleich wird in Kürze verfügbar sein.</div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Zahlungsmethoden</CardTitle>
              <CardDescription>Verwaltete Zahlungsmethoden</CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={handleAddPaymentMethod}>
              + Hinzufügen
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {settings.paymentMethods.length === 0 ? (
            <div className="text-sm text-muted-foreground">Noch keine Zahlungsmethoden hinterlegt.</div>
          ) : (
            <div className="space-y-2">
              {settings.paymentMethods.map((method) => (
                <div key={method.id} className="flex items-center justify-between p-3 border rounded-lg">
                  <div>
                    <p className="font-medium">{method.type}</p>
                    <p className="text-sm text-muted-foreground">•••• {method.last4}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Rechnungsarchiv</CardTitle>
          <CardDescription>Alle deine Rechnungen im Überblick</CardDescription>
        </CardHeader>
        <CardContent>
          {settings.invoices.length === 0 ? (
            <div className="text-sm text-muted-foreground">Noch keine Rechnungen vorhanden.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Datum</TableHead>
                  <TableHead>Betrag</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {settings.invoices.map((invoice) => (
                  <TableRow key={invoice.id}>
                    <TableCell>{invoice.date}</TableCell>
                    <TableCell>{invoice.amount.toFixed(2)} €</TableCell>
                    <TableCell>
                      <Badge variant={invoice.status === "bezahlt" ? "default" : "secondary"}>{invoice.status}</Badge>
                    </TableCell>
                    <TableCell>
                      <Button variant="ghost" size="sm">
                        Download
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
          <CardTitle>Nutzungsstatistiken</CardTitle>
          <CardDescription>Deine aktuelle Nutzung im Überblick</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <div className="flex items-center justify-between mb-2">
              <Label>Dokumente erstellt</Label>
              <span className="text-sm font-medium">{settings.usage.documentsCreated}</span>
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between mb-2">
              <Label>Speicher verwendet</Label>
              <span className="text-sm font-medium">
                {settings.usage.storageUsed} MB / {settings.usage.storageLimit} MB
              </span>
            </div>
            <div className="w-full bg-secondary rounded-full h-2">
              <div
                className="bg-primary h-2 rounded-full"
                style={{ width: `${(settings.usage.storageUsed / settings.usage.storageLimit) * 100}%` }}
              />
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

