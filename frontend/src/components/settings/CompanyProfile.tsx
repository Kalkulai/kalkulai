import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface CompanyProfileProps {
  onBack: () => void;
}

interface CompanyProfileData {
  name: string;
  companyId: string;
  street: string;
  zip: string;
  city: string;
  vatId: string;
  phone: string;
  email: string;
  website: string;
  logoUrl: string;
  brandColor: string;
}

const defaultData: CompanyProfileData = {
  name: "",
  companyId: "",
  street: "",
  zip: "",
  city: "",
  vatId: "",
  phone: "",
  email: "",
  website: "",
  logoUrl: "",
  brandColor: "#3b82f6",
};

export default function CompanyProfile({ onBack }: CompanyProfileProps) {
  const { toast } = useToast();
  const [data, setData] = useState<CompanyProfileData>(defaultData);
  const [hasChanges, setHasChanges] = useState(false);
  const [logoPreview, setLogoPreview] = useState<string | null>(null);

  useEffect(() => {
    const saved = localStorage.getItem("kalkulai_settings_company_profile");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setData({ ...defaultData, ...parsed });
        if (parsed.logoUrl) setLogoPreview(parsed.logoUrl);
      } catch (e) {
        console.error("Failed to load company profile", e);
      }
    }
  }, []);

  const handleSave = () => {
    localStorage.setItem("kalkulai_settings_company_profile", JSON.stringify(data));
    setHasChanges(false);
    toast({
      title: "Einstellungen gespeichert",
      description: "Dein Unternehmensprofil wurde erfolgreich gespeichert.",
    });
  };

  const handleLogoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        const result = reader.result as string;
        setLogoPreview(result);
        setData((prev) => ({ ...prev, logoUrl: result }));
        setHasChanges(true);
      };
      reader.readAsDataURL(file);
    }
  };

  const updateField = <K extends keyof CompanyProfileData>(key: K, value: CompanyProfileData[K]) => {
    setData((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-[#111827] mb-2">Unternehmensprofil</h1>
        <p className="text-sm text-[#6B7280]">
          Stammdaten deines Betriebs. Diese Angaben werden perspektivisch für Kopfzeilen und Dokumente verwendet.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Firmendaten</CardTitle>
          <CardDescription>Grundlegende Informationen zu deinem Unternehmen</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="name">Firmenname</Label>
              <Input
                id="name"
                value={data.name}
                onChange={(e) => updateField("name", e.target.value)}
                placeholder="Malerbetrieb Beispiel GmbH"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="companyId">Interne Firmen-ID</Label>
              <Input
                id="companyId"
                value={data.companyId}
                onChange={(e) => updateField("companyId", e.target.value)}
                placeholder="z. B. demo, firma-123"
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="street">Straße & Hausnummer</Label>
              <Input
                id="street"
                value={data.street}
                onChange={(e) => updateField("street", e.target.value)}
                placeholder="Hauptstraße 1"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="zip">PLZ</Label>
              <Input
                id="zip"
                value={data.zip}
                onChange={(e) => updateField("zip", e.target.value)}
                placeholder="12345"
                className="w-24"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="city">Ort</Label>
              <Input
                id="city"
                value={data.city}
                onChange={(e) => updateField("city", e.target.value)}
                placeholder="Stadt"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="vatId">USt-IdNr.</Label>
              <Input
                id="vatId"
                value={data.vatId}
                onChange={(e) => updateField("vatId", e.target.value)}
                placeholder="DE123456789"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Kontaktdaten</CardTitle>
          <CardDescription>Telefon, E-Mail und Website</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="phone">Telefon</Label>
              <Input
                id="phone"
                value={data.phone}
                onChange={(e) => updateField("phone", e.target.value)}
                placeholder="+49 123 456789"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">E-Mail</Label>
              <Input
                id="email"
                type="email"
                value={data.email}
                onChange={(e) => updateField("email", e.target.value)}
                placeholder="info@beispiel.de"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="website">Website</Label>
              <Input
                id="website"
                value={data.website}
                onChange={(e) => updateField("website", e.target.value)}
                placeholder="https://www.beispiel.de"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Logo & Branding</CardTitle>
          <CardDescription>Lade dein Logo hoch und wähle deine Markenfarben</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Logo hochladen</Label>
            <div className="border-2 border-dashed rounded-lg p-6 text-center">
              <input
                type="file"
                accept="image/*"
                onChange={handleLogoUpload}
                className="hidden"
                id="logo-upload"
              />
              <label htmlFor="logo-upload" className="cursor-pointer">
                {logoPreview ? (
                  <div className="space-y-2">
                    <img src={logoPreview} alt="Logo" className="max-h-32 mx-auto" />
                    <p className="text-sm text-muted-foreground">Klicken zum Ändern</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className="text-sm text-muted-foreground">Logo hier ablegen oder klicken zum Auswählen</p>
                    <Button variant="outline" size="sm" type="button" onClick={() => document.getElementById("logo-upload")?.click()}>
                      Datei auswählen
                    </Button>
                  </div>
                )}
              </label>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="brandColor">Branding-Farbe</Label>
            <div className="flex items-center gap-3">
              <Input
                id="brandColor"
                type="color"
                value={data.brandColor}
                onChange={(e) => updateField("brandColor", e.target.value)}
                className="w-20 h-10"
              />
              <Input
                value={data.brandColor}
                onChange={(e) => updateField("brandColor", e.target.value)}
                placeholder="#3b82f6"
                className="flex-1"
              />
            </div>
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

