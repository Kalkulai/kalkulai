import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface CompanyAccountingProps {
  onBack: () => void;
}

export default function CompanyAccounting({ onBack }: CompanyAccountingProps) {
  const { toast } = useToast();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-[#111827] mb-2">Buchhaltung</h1>
        <p className="text-sm text-[#6B7280]">Bankverbindungen, Steuereinstellungen und Kontenplan.</p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Bankverbindungen</CardTitle>
              <CardDescription>Verwaltete Bankverbindungen</CardDescription>
            </div>
            <Button>+ Hinzufügen</Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">Diese Funktion wird in Kürze verfügbar sein.</div>
        </CardContent>
      </Card>
    </div>
  );
}

