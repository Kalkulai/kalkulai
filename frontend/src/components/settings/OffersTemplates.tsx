import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/use-toast";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface OffersTemplatesProps {
  onBack: () => void;
}

interface TemplateSettings {
  offerGreeting: string;
  invoiceGreeting: string;
  paymentTerms: string;
  agb: string;
  footer: string;
  emailOffer: string;
  emailInvoice: string;
  emailReminder: string;
}

const defaultSettings: TemplateSettings = {
  offerGreeting: "",
  invoiceGreeting: "",
  paymentTerms: "",
  agb: "",
  footer: "",
  emailOffer: "",
  emailInvoice: "",
  emailReminder: "",
};

export default function OffersTemplates({ onBack }: OffersTemplatesProps) {
  const { toast } = useToast();
  const [settings, setSettings] = useState<TemplateSettings>(defaultSettings);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("kalkulai_settings_offers_templates");
    if (saved) {
      try {
        setSettings({ ...defaultSettings, ...JSON.parse(saved) });
      } catch (e) {
        console.error("Failed to load template settings", e);
      }
    }
  }, []);

  const handleSave = () => {
    localStorage.setItem("kalkulai_settings_offers_templates", JSON.stringify(settings));
    setHasChanges(false);
    toast({
      title: "Einstellungen gespeichert",
      description: "Deine Textbausteine wurden erfolgreich gespeichert.",
    });
  };

  const updateSetting = <K extends keyof TemplateSettings>(key: K, value: TemplateSettings[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-[#111827] mb-2">Textbausteine & Vorlagen</h1>
        <p className="text-sm text-[#6B7280]">Begrüßungstexte, Zahlungsbedingungen und E-Mail-Vorlagen.</p>
      </div>

      <Tabs defaultValue="documents" className="w-full">
        <TabsList>
          <TabsTrigger value="documents">Dokumente</TabsTrigger>
          <TabsTrigger value="emails">E-Mails</TabsTrigger>
        </TabsList>

        <TabsContent value="documents" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Begrüßungstexte für Angebote</CardTitle>
              <CardDescription>Text, der am Anfang jedes Angebots erscheint</CardDescription>
            </CardHeader>
            <CardContent>
              <Textarea
                value={settings.offerGreeting}
                onChange={(e) => updateSetting("offerGreeting", e.target.value)}
                placeholder="Sehr geehrte Damen und Herren,&#10;&#10;vielen Dank für Ihre Anfrage..."
                rows={6}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Begrüßungstexte für Rechnungen</CardTitle>
              <CardDescription>Text, der am Anfang jeder Rechnung erscheint</CardDescription>
            </CardHeader>
            <CardContent>
              <Textarea
                value={settings.invoiceGreeting}
                onChange={(e) => updateSetting("invoiceGreeting", e.target.value)}
                placeholder="Sehr geehrte Damen und Herren,&#10;&#10;hiermit stellen wir Ihnen folgende Leistungen in Rechnung..."
                rows={6}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Zahlungsbedingungen</CardTitle>
              <CardDescription>Standard-Zahlungsbedingungen für Dokumente</CardDescription>
            </CardHeader>
            <CardContent>
              <Textarea
                value={settings.paymentTerms}
                onChange={(e) => updateSetting("paymentTerms", e.target.value)}
                placeholder="Zahlungsziel: 14 Tage nach Rechnungsdatum&#10;Bei Zahlungsverzug werden Verzugszinsen in Höhe von 9 Prozentpunkten über dem Basiszinssatz berechnet."
                rows={6}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>AGB</CardTitle>
              <CardDescription>Allgemeine Geschäftsbedingungen</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Textarea
                value={settings.agb}
                onChange={(e) => updateSetting("agb", e.target.value)}
                placeholder="Hier können Sie Ihre AGB eingeben oder hochladen..."
                rows={8}
              />
              <Button variant="outline">AGB hochladen</Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Fußzeilen</CardTitle>
              <CardDescription>Text, der am Ende jedes Dokuments erscheint</CardDescription>
            </CardHeader>
            <CardContent>
              <Textarea
                value={settings.footer}
                onChange={(e) => updateSetting("footer", e.target.value)}
                placeholder="Mit freundlichen Grüßen&#10;Ihr Team"
                rows={4}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="emails" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Angebotsversand</CardTitle>
              <CardDescription>E-Mail-Vorlage beim Versenden von Angeboten</CardDescription>
            </CardHeader>
            <CardContent>
              <Textarea
                value={settings.emailOffer}
                onChange={(e) => updateSetting("emailOffer", e.target.value)}
                placeholder="Betreff: Ihr Angebot&#10;&#10;Sehr geehrte Damen und Herren,&#10;&#10;anbei erhalten Sie unser Angebot..."
                rows={8}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Rechnungsversand</CardTitle>
              <CardDescription>E-Mail-Vorlage beim Versenden von Rechnungen</CardDescription>
            </CardHeader>
            <CardContent>
              <Textarea
                value={settings.emailInvoice}
                onChange={(e) => updateSetting("emailInvoice", e.target.value)}
                placeholder="Betreff: Rechnung&#10;&#10;Sehr geehrte Damen und Herren,&#10;&#10;anbei erhalten Sie unsere Rechnung..."
                rows={8}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Zahlungserinnerung</CardTitle>
              <CardDescription>E-Mail-Vorlage für Zahlungserinnerungen</CardDescription>
            </CardHeader>
            <CardContent>
              <Textarea
                value={settings.emailReminder}
                onChange={(e) => updateSetting("emailReminder", e.target.value)}
                placeholder="Betreff: Zahlungserinnerung&#10;&#10;Sehr geehrte Damen und Herren,&#10;&#10;leider haben wir noch keinen Zahlungseingang für die Rechnung..."
                rows={8}
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={!hasChanges}>
          Speichern
        </Button>
      </div>
    </div>
  );
}

