import { useState } from "react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Camera, X, Lock, Eye, EyeOff, Shield, LogOut } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/components/ui/use-toast";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";

interface ProfileModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function ProfileModal({ open, onOpenChange }: ProfileModalProps) {
  const { user, updateProfile, changePassword } = useAuth();
  const { toast } = useToast();
  const [displayName, setDisplayName] = useState(user?.name || "");
  const [isSaving, setIsSaving] = useState(false);
  
  // Password change state
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPasswords, setShowPasswords] = useState(false);
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  
  // 2FA state
  const [twoFactorEnabled, setTwoFactorEnabled] = useState(false);
  
  // Active sessions state
  const [activeSessions] = useState([
    { id: "1", device: "Chrome auf Mac", location: "München", time: "Heute, 14:30" },
  ]);

  const getInitials = () => {
    if (user?.name) {
      return user.name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2);
    }
    return "U";
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await updateProfile({ name: displayName });
      toast({
        title: "Profil gespeichert",
        description: "Deine Profiländerungen wurden erfolgreich gespeichert.",
      });
      onOpenChange(false);
    } catch (error) {
      toast({
        title: "Fehler",
        description: "Profil konnte nicht gespeichert werden.",
        variant: "destructive",
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    setDisplayName(user?.name || "");
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setPasswordMessage(null);
    onOpenChange(false);
  };
  
  const handlePasswordChange = async () => {
    setPasswordMessage(null);
    if (newPassword !== confirmPassword) {
      setPasswordMessage({ type: "error", text: "Passwörter stimmen nicht überein" });
      return;
    }
    if (newPassword.length < 6) {
      setPasswordMessage({ type: "error", text: "Passwort muss mindestens 6 Zeichen lang sein" });
      return;
    }
    setIsChangingPassword(true);
    try {
      await changePassword(currentPassword, newPassword);
      setPasswordMessage({ type: "success", text: "Passwort erfolgreich geändert" });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      toast({
        title: "Passwort geändert",
        description: "Dein Passwort wurde erfolgreich geändert.",
      });
    } catch (err: any) {
      setPasswordMessage({ type: "error", text: err.message || "Fehler beim Ändern" });
    } finally {
      setIsChangingPassword(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[600px] w-[90vw] max-h-[90vh] overflow-y-auto p-10 [&>button]:hidden">
        {/* Close button - top right */}
        <button
          onClick={() => onOpenChange(false)}
          className="absolute right-4 top-4 z-50 rounded-sm opacity-70 hover:opacity-100 transition-opacity text-[#6B7280] hover:text-[#111827] focus:outline-none focus:ring-2 focus:ring-[#3B82F6] focus:ring-offset-2"
        >
          <X className="h-5 w-5" />
          <span className="sr-only">Schließen</span>
        </button>
        
        <div className="space-y-8">
          {/* Header */}
          <h2 className="text-2xl font-bold text-[#111827]">Profil bearbeiten</h2>

          {/* Avatar */}
          <div className="flex flex-col items-center">
            <div className="relative">
              <div className="w-[120px] h-[120px] rounded-full bg-gradient-to-br from-[#3B82F6] to-[#8B5CF6] flex items-center justify-center text-white text-3xl font-semibold">
                {getInitials()}
              </div>
              <button className="absolute bottom-0 right-0 w-10 h-10 rounded-full bg-white border-2 border-[#E5E7EB] flex items-center justify-center hover:border-[#3B82F6] transition-colors">
                <Camera className="h-5 w-5 text-[#6B7280]" />
              </button>
            </div>
          </div>

          {/* Form Fields */}
          <div className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="display-name" className="text-sm font-medium text-[#6B7280]">
                Anzeigename
              </Label>
              <Input
                id="display-name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="h-12 border-[#E5E7EB] focus:border-[#3B82F6] focus:ring-[#3B82F6]"
                placeholder="Mega Knight"
              />
            </div>

          </div>

          {/* Info Text */}
          <p className="text-sm text-[#6B7280] leading-relaxed">
            Dein Profil hilft anderen, dich zu erkennen. Dein Name wird auch in der KalkulAI-App verwendet.
          </p>

          {/* Security Section */}
          <div className="space-y-6 pt-6 border-t border-[#E5E7EB]">
            <h3 className="text-xl font-bold text-[#111827]">Sicherheit & Datenschutz</h3>

            {/* Password Change */}
            <Card>
              <CardHeader>
                <CardTitle>Passwort ändern</CardTitle>
                <CardDescription>Ändere dein Passwort regelmäßig für mehr Sicherheit</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="current-password">Aktuelles Passwort</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#6B7280]" />
                    <Input
                      id="current-password"
                      type={showPasswords ? "text" : "password"}
                      value={currentPassword}
                      onChange={(e) => setCurrentPassword(e.target.value)}
                      className="pl-10 pr-10 h-12"
                      placeholder="••••••••"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPasswords(!showPasswords)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-[#6B7280] hover:text-[#111827]"
                    >
                      {showPasswords ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="new-password">Neues Passwort</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#6B7280]" />
                    <Input
                      id="new-password"
                      type={showPasswords ? "text" : "password"}
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      className="pl-10 h-12"
                      placeholder="Mindestens 6 Zeichen"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="confirm-password">Passwort bestätigen</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#6B7280]" />
                    <Input
                      id="confirm-password"
                      type={showPasswords ? "text" : "password"}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      className="pl-10 h-12"
                      placeholder="Passwort wiederholen"
                    />
                  </div>
                </div>

                {passwordMessage && (
                  <div
                    className={`p-3 rounded-lg text-sm ${
                      passwordMessage.type === "success"
                        ? "bg-green-50 border border-green-200 text-green-700"
                        : "bg-red-50 border border-red-200 text-red-700"
                    }`}
                  >
                    {passwordMessage.text}
                  </div>
                )}

                <Button
                  onClick={handlePasswordChange}
                  disabled={isChangingPassword || !currentPassword || !newPassword || !confirmPassword}
                  className="w-full h-12 bg-[#3B82F6] hover:bg-[#2563EB] text-white"
                >
                  {isChangingPassword ? (
                    <>
                      <Lock className="mr-2 h-4 w-4 animate-pulse" />
                      Wird geändert...
                    </>
                  ) : (
                    <>
                      <Lock className="mr-2 h-4 w-4" />
                      Passwort ändern
                    </>
                  )}
                </Button>
              </CardContent>
            </Card>

            {/* Two-Factor Authentication */}
            <Card>
              <CardHeader>
                <CardTitle>Zwei-Faktor-Authentifizierung</CardTitle>
                <CardDescription>Zusätzliche Sicherheitsebene für dein Konto</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <p className="text-sm font-medium text-[#111827]">2FA aktivieren</p>
                    <p className="text-xs text-[#6B7280]">
                      Schütze dein Konto mit einem zusätzlichen Sicherheitscode
                    </p>
                  </div>
                  <Switch checked={twoFactorEnabled} onCheckedChange={setTwoFactorEnabled} />
                </div>
              </CardContent>
            </Card>

            {/* Active Sessions */}
            <Card>
              <CardHeader>
                <CardTitle>Aktive Sitzungen</CardTitle>
                <CardDescription>Verwaltete Geräte und aktive Anmeldungen</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {activeSessions.map((session) => (
                    <div key={session.id} className="flex items-center justify-between p-3 rounded-lg border border-[#E5E7EB]">
                      <div>
                        <p className="text-sm font-medium text-[#111827]">{session.device}</p>
                        <p className="text-xs text-[#6B7280]">
                          {session.location} • {session.time}
                        </p>
                      </div>
                      <Button variant="outline" size="sm" className="h-9">
                        <LogOut className="h-4 w-4 mr-2" />
                        Abmelden
                      </Button>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Buttons */}
          <div className="flex justify-end gap-3 pt-4">
            <Button
              variant="outline"
              onClick={handleCancel}
              className="h-12 px-6 border-[#E5E7EB] text-[#111827] hover:bg-[#F9FAFB]"
            >
              Abbrechen
            </Button>
            <Button
              onClick={handleSave}
              disabled={isSaving}
              className="h-12 px-6 bg-[#111827] hover:bg-[#1F2937] text-white"
            >
              {isSaving ? "Speichern..." : "Speichern"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

