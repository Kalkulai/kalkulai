import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/use-toast";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/contexts/AuthContext";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertTriangle } from "lucide-react";

interface OverviewSecurityProps {
  onBack: () => void;
}

export default function OverviewSecurity({ onBack }: OverviewSecurityProps) {
  const { toast } = useToast();
  const { changePassword } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [twoFactorEnabled, setTwoFactorEnabled] = useState(false);
  const [activeSessions, setActiveSessions] = useState([
    { id: "1", device: "Chrome auf Mac", location: "München", lastActive: "Heute, 14:30" },
  ]);
  const [dataSharing, setDataSharing] = useState({
    analytics: false,
    marketing: false,
  });

  const handlePasswordChange = async () => {
    if (newPassword !== confirmPassword) {
      toast({
        title: "Fehler",
        description: "Die Passwörter stimmen nicht überein.",
        variant: "destructive",
      });
      return;
    }
    if (newPassword.length < 8) {
      toast({
        title: "Fehler",
        description: "Das Passwort muss mindestens 8 Zeichen lang sein.",
        variant: "destructive",
      });
      return;
    }
    try {
      await changePassword(currentPassword, newPassword);
      toast({
        title: "Erfolg",
        description: "Passwort wurde erfolgreich geändert.",
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (error) {
      toast({
        title: "Fehler",
        description: "Passwort konnte nicht geändert werden.",
        variant: "destructive",
      });
    }
  };

  const handleDeleteAccount = () => {
    toast({
      title: "Account löschen",
      description: "Diese Funktion wird in Kürze verfügbar sein.",
      variant: "destructive",
    });
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-[#111827] mb-2">Sicherheit & Datenschutz</h1>
        <p className="text-sm text-[#6B7280]">Passwort, Zwei-Faktor-Authentifizierung und Datenschutzeinstellungen verwalten.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Passwort ändern</CardTitle>
          <CardDescription>Ändere dein Passwort regelmäßig für mehr Sicherheit</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="currentPassword">Aktuelles Passwort</Label>
            <Input
              id="currentPassword"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="newPassword">Neues Passwort</Label>
            <Input
              id="newPassword"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirmPassword">Passwort bestätigen</Label>
            <Input
              id="confirmPassword"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          </div>
          <Button onClick={handlePasswordChange}>Passwort ändern</Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Zwei-Faktor-Authentifizierung</CardTitle>
          <CardDescription>Zusätzliche Sicherheitsebene für dein Konto</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>2FA aktivieren</Label>
              <p className="text-sm text-muted-foreground">Schütze dein Konto mit einem zusätzlichen Sicherheitscode</p>
            </div>
            <Switch checked={twoFactorEnabled} onCheckedChange={setTwoFactorEnabled} />
          </div>
          {twoFactorEnabled && (
            <div className="mt-4 p-4 border rounded-lg bg-muted/50">
              <p className="text-sm text-muted-foreground">QR-Code Setup wird in Kürze verfügbar sein.</p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Aktive Sitzungen</CardTitle>
          <CardDescription>Verwaltete Geräte und aktive Anmeldungen</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {activeSessions.map((session) => (
            <div key={session.id} className="flex items-center justify-between p-3 border rounded-lg">
              <div>
                <p className="font-medium">{session.device}</p>
                <p className="text-sm text-muted-foreground">
                  {session.location} • {session.lastActive}
                </p>
              </div>
              <Button variant="ghost" size="sm">
                Abmelden
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Datenschutzeinstellungen</CardTitle>
          <CardDescription>Kontrolliere, welche Daten geteilt werden</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Analytics-Daten</Label>
              <p className="text-sm text-muted-foreground">Hilf uns, die App zu verbessern</p>
            </div>
            <Switch checked={dataSharing.analytics} onCheckedChange={(v) => setDataSharing({ ...dataSharing, analytics: v })} />
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Marketing-E-Mails</Label>
              <p className="text-sm text-muted-foreground">Erhalte Updates und Angebote</p>
            </div>
            <Switch checked={dataSharing.marketing} onCheckedChange={(v) => setDataSharing({ ...dataSharing, marketing: v })} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Datenexport DSGVO</CardTitle>
          <CardDescription>Lade alle deine Daten herunter</CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline">Daten exportieren</Button>
        </CardContent>
      </Card>

      <Card className="border-destructive">
        <CardHeader>
          <CardTitle className="text-destructive">Account löschen</CardTitle>
          <CardDescription>Diese Aktion kann nicht rückgängig gemacht werden</CardDescription>
        </CardHeader>
        <CardContent>
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>
              Wenn du deinen Account löschst, werden alle deine Daten dauerhaft entfernt. Diese Aktion kann nicht rückgängig gemacht werden.
            </AlertDescription>
          </Alert>
          <Button variant="destructive" className="mt-4" onClick={handleDeleteAccount}>
            Account löschen
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

