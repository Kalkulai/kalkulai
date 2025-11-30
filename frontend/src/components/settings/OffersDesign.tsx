import { useState, useEffect, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/components/ui/use-toast";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api, type OfferTemplateOption } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Check, Loader2 } from "lucide-react";

interface OffersDesignProps {
  onBack: () => void;
}

export default function OffersDesign({ onBack }: OffersDesignProps) {
  const { toast } = useToast();
  const { user } = useAuth();
  const [templates, setTemplates] = useState<OfferTemplateOption[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [colorScheme, setColorScheme] = useState("#3b82f6");
  const [fontFamily, setFontFamily] = useState("sans-serif");
  const [logoPosition, setLogoPosition] = useState("left");

  const templateStorageKey = useMemo(
    () => (user?.id ? `kalkulai_offer_template_${user.id}` : "kalkulai_offer_template_guest"),
    [user?.id],
  );

  useEffect(() => {
    setIsLoading(true);
    api
      .pdfTemplates()
      .then((res) => {
        setTemplates(res.templates || []);
        setError(null);
      })
      .catch((err: any) => {
        setError(err?.message || "Layouts konnten nicht geladen werden.");
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, []);

  useEffect(() => {
    const stored = localStorage.getItem(templateStorageKey);
    if (stored) {
      setSelectedTemplateId(stored);
    } else if (templates.length > 0) {
      const defaultTemplate = templates.find((t) => t.is_default) || templates[0];
      if (defaultTemplate) {
        setSelectedTemplateId(defaultTemplate.id);
      }
    }
  }, [templates, templateStorageKey]);

  useEffect(() => {
    const saved = localStorage.getItem("kalkulai_settings_offers_design");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setColorScheme(parsed.colorScheme || "#3b82f6");
        setFontFamily(parsed.fontFamily || "sans-serif");
        setLogoPosition(parsed.logoPosition || "left");
      } catch (e) {
        console.error("Failed to load design settings", e);
      }
    }
  }, []);

  const handleTemplateSelect = (templateId: string) => {
    setSelectedTemplateId(templateId);
    localStorage.setItem(templateStorageKey, templateId);
    window.dispatchEvent(new CustomEvent("kalkulai-template-changed", { detail: { templateId } }));
    toast({
      title: "Layout ausgewählt",
      description: "Das Layout wurde erfolgreich ausgewählt.",
    });
  };

  const handleSave = () => {
    const settings = {
      colorScheme,
      fontFamily,
      logoPosition,
    };
    localStorage.setItem("kalkulai_settings_offers_design", JSON.stringify(settings));
    toast({
      title: "Einstellungen gespeichert",
      description: "Deine Design-Einstellungen wurden erfolgreich gespeichert.",
    });
  };

  const activeTemplate = templates.find((t) => t.id === selectedTemplateId) || templates.find((t) => t.is_default) || templates[0];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-[#111827] mb-2">Dokument-Design</h1>
        <p className="text-sm text-[#6B7280]">Wähle das Layout, das am besten zu deiner Außendarstellung passt.</p>
      </div>

      {error && (
        <Card className="border-destructive">
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">{error}</p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>PDF-Grundgerüste</CardTitle>
          <CardDescription>Wähle das Layout für deine Angebote und Rechnungen</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Layouts werden geladen...
            </div>
          ) : templates.length === 0 ? (
            <div className="text-sm text-muted-foreground">Noch keine Layouts verfügbar.</div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {templates.map((template) => {
                const isActive = template.id === selectedTemplateId;
                return (
                  <button
                    key={template.id}
                    type="button"
                    onClick={() => handleTemplateSelect(template.id)}
                    className={`rounded-2xl border px-5 py-4 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 ${
                      isActive ? "border-primary bg-primary/5 ring-primary/40" : "border-border hover:border-primary/40 hover:bg-muted/40"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                          {template.label}
                        </div>
                        <p className="text-xs text-sm text-[#6B7280]">{template.tagline}</p>
                      </div>
                      {isActive && (
                        <Badge className="bg-primary/10 text-primary">
                          <Check className="h-3 w-3 mr-1" />
                          Aktiv
                        </Badge>
                      )}
                    </div>
                    <div
                      className="mt-3 h-20 rounded-xl border transition"
                      style={{
                        borderColor: template.accent,
                        background: `linear-gradient(135deg, ${template.background} 0%, #ffffff 100%)`,
                      }}
                    />
                    <p className="mt-3 text-sm text-muted-foreground leading-relaxed">{template.description}</p>
                  </button>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Design-Anpassungen</CardTitle>
          <CardDescription>Passe Farbschema, Schriftart und Logo-Position an</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="colorScheme">Farbschema</Label>
            <div className="flex items-center gap-3">
              <input
                id="colorScheme"
                type="color"
                value={colorScheme}
                onChange={(e) => setColorScheme(e.target.value)}
                className="w-20 h-10 rounded border"
              />
              <input
                type="text"
                value={colorScheme}
                onChange={(e) => setColorScheme(e.target.value)}
                className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
                placeholder="#3b82f6"
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="fontFamily">Schriftart</Label>
            <Select value={fontFamily} onValueChange={setFontFamily}>
              <SelectTrigger id="fontFamily">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="sans-serif">Sans-Serif</SelectItem>
                <SelectItem value="serif">Serif</SelectItem>
                <SelectItem value="monospace">Monospace</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="logoPosition">Logo-Positionierung</Label>
            <Select value={logoPosition} onValueChange={setLogoPosition}>
              <SelectTrigger id="logoPosition">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="left">Links</SelectItem>
                <SelectItem value="right">Rechts</SelectItem>
                <SelectItem value="center">Zentriert</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex justify-end pt-4 border-t">
            <Button onClick={handleSave}>Speichern</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

