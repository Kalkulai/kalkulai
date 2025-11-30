import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import DatabaseManager from "@/components/DatabaseManager";

interface OffersProductsProps {
  onBack: () => void;
}

export default function OffersProducts({ onBack }: OffersProductsProps) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-[#111827] mb-2">Produktverwaltung</h1>
        <p className="text-sm text-[#6B7280]">
          Verwalte Produkte und Katalogeinträge, die für Angebote & Rechnungen genutzt werden.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardDescription>Verwalten Sie Ihre Produktdatenbank. Synonyme und importieren Sie Daten per CSV.</CardDescription>
        </CardHeader>
        <CardContent>
          <DatabaseManager />
        </CardContent>
      </Card>
    </div>
  );
}

