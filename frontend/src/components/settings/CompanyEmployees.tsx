import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/components/ui/use-toast";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

interface CompanyEmployeesProps {
  onBack: () => void;
}

interface TeamMember {
  id: string;
  name: string;
  role: "inhaber" | "projektleitung" | "ausführung" | "backoffice";
  active: boolean;
  canOffers: boolean;
  canInvoices: boolean;
  canDashboard: boolean;
  isAdmin: boolean;
}

const defaultMembers: TeamMember[] = [
  {
    id: "owner",
    name: "Inhaber",
    role: "inhaber",
    active: true,
    canOffers: true,
    canInvoices: true,
    canDashboard: true,
    isAdmin: true,
  },
];

export default function CompanyEmployees({ onBack }: CompanyEmployeesProps) {
  const { toast } = useToast();
  const [members, setMembers] = useState<TeamMember[]>(defaultMembers);
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const [newMember, setNewMember] = useState<Omit<TeamMember, "id">>({
    name: "",
    role: "ausführung",
    active: true,
    canOffers: false,
    canInvoices: false,
    canDashboard: false,
    isAdmin: false,
  });

  useEffect(() => {
    const saved = localStorage.getItem("kalkulai_settings_company_employees");
    if (saved) {
      try {
        setMembers(JSON.parse(saved));
      } catch (e) {
        console.error("Failed to load employees", e);
      }
    }
  }, []);

  const handleSave = () => {
    localStorage.setItem("kalkulai_settings_company_employees", JSON.stringify(members));
    toast({
      title: "Einstellungen gespeichert",
      description: "Die Mitarbeiterliste wurde erfolgreich gespeichert.",
    });
  };

  const handleAddMember = () => {
    const member: TeamMember = {
      ...newMember,
      id: `member_${Date.now()}`,
    };
    setMembers([...members, member]);
    setNewMember({
      name: "",
      role: "ausführung",
      active: true,
      canOffers: false,
      canInvoices: false,
      canDashboard: false,
      isAdmin: false,
    });
    setIsAddDialogOpen(false);
    toast({
      title: "Mitarbeiter hinzugefügt",
      description: `${member.name} wurde zur Liste hinzugefügt.`,
    });
  };

  const handleUpdateMember = (id: string, field: keyof TeamMember, value: any) => {
    setMembers((prev) => prev.map((m) => (m.id === id ? { ...m, [field]: value } : m)));
  };

  const handleRemoveMember = (id: string) => {
    setMembers((prev) => prev.filter((m) => m.id !== id));
    toast({
      title: "Mitarbeiter entfernt",
      description: "Der Mitarbeiter wurde aus der Liste entfernt.",
    });
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-[#111827] mb-2">Mitarbeiter & Zugriffsrechte</h1>
        <p className="text-sm text-[#6B7280]">
          Lege fest, wer welche Bereiche nutzen darf. Diese Übersicht dient aktuell als Rechtekonzept und wird lokal gespeichert.
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Mitarbeiterliste</CardTitle>
              <CardDescription>Verwaltete Mitarbeiter und ihre Berechtigungen</CardDescription>
            </div>
            <Button onClick={() => setIsAddDialogOpen(true)}>+ Mitarbeiter hinzufügen</Button>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Rolle</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Berechtigungen</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map((member) => (
                <TableRow key={member.id}>
                  <TableCell>
                    <Input
                      value={member.name}
                      onChange={(e) => handleUpdateMember(member.id, "name", e.target.value)}
                      className="w-48"
                    />
                  </TableCell>
                  <TableCell>
                    <Select
                      value={member.role}
                      onValueChange={(value) => handleUpdateMember(member.id, "role", value as TeamMember["role"])}
                    >
                      <SelectTrigger className="w-40">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="inhaber">Inhaber</SelectItem>
                        <SelectItem value="projektleitung">Projektleitung</SelectItem>
                        <SelectItem value="ausführung">Ausführung</SelectItem>
                        <SelectItem value="backoffice">Backoffice</SelectItem>
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    <Switch checked={member.active} onCheckedChange={(v) => handleUpdateMember(member.id, "active", v)} />
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-3 text-sm">
                      <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={member.canOffers}
                          onChange={(e) => handleUpdateMember(member.id, "canOffers", e.target.checked)}
                          className="w-4 h-4"
                        />
                        <span>Angebote</span>
                      </label>
                      <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={member.canInvoices}
                          onChange={(e) => handleUpdateMember(member.id, "canInvoices", e.target.checked)}
                          className="w-4 h-4"
                        />
                        <span>Rechnungen</span>
                      </label>
                      <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={member.canDashboard}
                          onChange={(e) => handleUpdateMember(member.id, "canDashboard", e.target.checked)}
                          className="w-4 h-4"
                        />
                        <span>Dashboard</span>
                      </label>
                      <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={member.isAdmin}
                          onChange={(e) => handleUpdateMember(member.id, "isAdmin", e.target.checked)}
                          className="w-4 h-4"
                        />
                        <span>Admin</span>
                      </label>
                    </div>
                  </TableCell>
                  <TableCell>
                    {member.id !== "owner" && (
                      <Button variant="ghost" size="sm" onClick={() => handleRemoveMember(member.id)}>
                        Löschen
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="flex justify-between items-center">
        <p className="text-sm text-muted-foreground">Die hier definierten Rechte werden aktuell nur als Planungsgrundlage gespeichert.</p>
        <Button onClick={handleSave}>Rechte-Konzept sichern</Button>
      </div>

      <Dialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Mitarbeiter hinzufügen</DialogTitle>
            <DialogDescription>Füge einen neuen Mitarbeiter zur Liste hinzu.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="new-name">Name</Label>
              <Input
                id="new-name"
                value={newMember.name}
                onChange={(e) => setNewMember({ ...newMember, name: e.target.value })}
                placeholder="Max Mustermann"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-role">Rolle</Label>
              <Select
                value={newMember.role}
                onValueChange={(value) => setNewMember({ ...newMember, role: value as TeamMember["role"] })}
              >
                <SelectTrigger id="new-role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="inhaber">Inhaber</SelectItem>
                  <SelectItem value="projektleitung">Projektleitung</SelectItem>
                  <SelectItem value="ausführung">Ausführung</SelectItem>
                  <SelectItem value="backoffice">Backoffice</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsAddDialogOpen(false)}>
              Abbrechen
            </Button>
            <Button onClick={handleAddMember} disabled={!newMember.name}>
              Hinzufügen
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

