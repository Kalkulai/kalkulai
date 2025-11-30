import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

interface OffersPricingProps {
  onBack: () => void;
}

interface Discount {
  id: string;
  name: string;
  percentage: number;
}

interface TaxRate {
  id: string;
  rate: number;
  name: string;
}

interface Surcharge {
  id: string;
  name: string;
  percentage: number;
}

export default function OffersPricing({ onBack }: OffersPricingProps) {
  const { toast } = useToast();
  const [discounts, setDiscounts] = useState<Discount[]>([]);
  const [taxRates, setTaxRates] = useState<TaxRate[]>([
    { id: "1", rate: 19, name: "Standard" },
    { id: "2", rate: 7, name: "Ermäßigt" },
    { id: "3", rate: 0, name: "Steuerfrei" },
  ]);
  const [surcharges, setSurcharges] = useState<Surcharge[]>([]);

  useEffect(() => {
    const saved = localStorage.getItem("kalkulai_settings_offers_pricing");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setDiscounts(parsed.discounts || []);
        setTaxRates(parsed.taxRates || taxRates);
        setSurcharges(parsed.surcharges || []);
      } catch (e) {
        console.error("Failed to load pricing settings", e);
      }
    }
  }, []);

  const handleSave = () => {
    const settings = {
      discounts,
      taxRates,
      surcharges,
    };
    localStorage.setItem("kalkulai_settings_offers_pricing", JSON.stringify(settings));
    toast({
      title: "Einstellungen gespeichert",
      description: "Deine Preisgestaltungs-Einstellungen wurden erfolgreich gespeichert.",
    });
  };

  const handleAddDiscount = () => {
    const newDiscount: Discount = {
      id: `discount_${Date.now()}`,
      name: "Neuer Rabatt",
      percentage: 0,
    };
    setDiscounts([...discounts, newDiscount]);
  };

  const handleAddTaxRate = () => {
    const newTaxRate: TaxRate = {
      id: `tax_${Date.now()}`,
      rate: 0,
      name: "Neuer Steuersatz",
    };
    setTaxRates([...taxRates, newTaxRate]);
  };

  const handleAddSurcharge = () => {
    const newSurcharge: Surcharge = {
      id: `surcharge_${Date.now()}`,
      name: "Neuer Zuschlag",
      percentage: 0,
    };
    setSurcharges([...surcharges, newSurcharge]);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-[#111827] mb-2">Preisgestaltung</h1>
        <p className="text-sm text-[#6B7280]">Standardrabatte, Mehrwertsteuersätze und Zuschläge definieren.</p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Standardrabatte</CardTitle>
              <CardDescription>Häufig verwendete Rabatte</CardDescription>
            </div>
            <Button onClick={handleAddDiscount}>+ Hinzufügen</Button>
          </div>
        </CardHeader>
        <CardContent>
          {discounts.length === 0 ? (
            <div className="text-sm text-muted-foreground">Noch keine Rabatte definiert.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Prozent</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {discounts.map((discount) => (
                  <TableRow key={discount.id}>
                    <TableCell>
                      <Input
                        value={discount.name}
                        onChange={(e) =>
                          setDiscounts(discounts.map((d) => (d.id === discount.id ? { ...d, name: e.target.value } : d)))
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        value={discount.percentage}
                        onChange={(e) =>
                          setDiscounts(
                            discounts.map((d) => (d.id === discount.id ? { ...d, percentage: parseFloat(e.target.value) || 0 } : d)),
                          )
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setDiscounts(discounts.filter((d) => d.id !== discount.id))}
                      >
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
              <CardTitle>Mehrwertsteuersätze</CardTitle>
              <CardDescription>Verfügbare MwSt-Sätze</CardDescription>
            </div>
            <Button onClick={handleAddTaxRate}>+ Hinzufügen</Button>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Satz (%)</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {taxRates.map((tax) => (
                <TableRow key={tax.id}>
                  <TableCell>
                    <Input
                      value={tax.name}
                      onChange={(e) => setTaxRates(taxRates.map((t) => (t.id === tax.id ? { ...t, name: e.target.value } : t)))}
                    />
                  </TableCell>
                  <TableCell>
                    <Input
                      type="number"
                      value={tax.rate}
                      onChange={(e) =>
                        setTaxRates(taxRates.map((t) => (t.id === tax.id ? { ...t, rate: parseFloat(e.target.value) || 0 } : t)))
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="sm" onClick={() => setTaxRates(taxRates.filter((t) => t.id !== tax.id))}>
                      Löschen
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Zuschläge & Aufschläge</CardTitle>
              <CardDescription>Zusätzliche Aufschläge</CardDescription>
            </div>
            <Button onClick={handleAddSurcharge}>+ Hinzufügen</Button>
          </div>
        </CardHeader>
        <CardContent>
          {surcharges.length === 0 ? (
            <div className="text-sm text-muted-foreground">Noch keine Zuschläge definiert.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Prozent</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {surcharges.map((surcharge) => (
                  <TableRow key={surcharge.id}>
                    <TableCell>
                      <Input
                        value={surcharge.name}
                        onChange={(e) =>
                          setSurcharges(surcharges.map((s) => (s.id === surcharge.id ? { ...s, name: e.target.value } : s)))
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        value={surcharge.percentage}
                        onChange={(e) =>
                          setSurcharges(
                            surcharges.map((s) => (s.id === surcharge.id ? { ...s, percentage: parseFloat(e.target.value) || 0 } : s)),
                          )
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setSurcharges(surcharges.filter((s) => s.id !== surcharge.id))}
                      >
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

      <div className="flex justify-end">
        <Button onClick={handleSave}>Speichern</Button>
      </div>
    </div>
  );
}

