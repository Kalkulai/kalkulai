import { ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ChevronDown,
  ChevronRight,
  User,
  Settings,
  LogOut,
  LayoutDashboard,
  FileText,
  CalendarDays,
  MessageCircle,
  Mail,
  Lock,
  Loader2,
  Eye,
  EyeOff,
  Check,
  Palette,
  Building2,
  ShieldCheck,
} from "lucide-react";
import DatabaseManager from "@/components/DatabaseManager";
import GuardMaterialsEditor from "@/components/GuardMaterialsEditor";
import { api } from "@/lib/api";
import type { OfferTemplateOption } from "@/lib/api";
import SettingsModal from "@/components/modals/SettingsModal";
import ProfileModal from "@/components/modals/ProfileModal";

interface MainLayoutProps {
  children: ReactNode;
}

const navItems = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard },
  { path: "/angebote", label: "Angebote & Rechnungen", icon: FileText },
  { path: "/plantafel", label: "Plantafel", icon: CalendarDays },
  { path: "/kommunikation", label: "Communication Hub", icon: MessageCircle },
];

export default function MainLayout({ children }: MainLayoutProps) {
  const { user, logout, changePassword, changeEmail, updateProfile } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  // Dialog states
  const [isProfileDialogOpen, setIsProfileDialogOpen] = useState(false);
  const [isSettingsDialogOpen, setIsSettingsDialogOpen] = useState(false);

  // Profile state
  const [profileName, setProfileName] = useState(user?.name || "");
  const [isUpdatingProfile, setIsUpdatingProfile] = useState(false);
  const [profileMessage, setProfileMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Password change state
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPasswords, setShowPasswords] = useState(false);
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Email change state
  const [newEmail, setNewEmail] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [isChangingEmail, setIsChangingEmail] = useState(false);
  const [emailMessage, setEmailMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // PDF-Template-Einstellungen (Layouts) – global im Einstellungsdialog
  const [offerTemplates, setOfferTemplates] = useState<OfferTemplateOption[]>([]);
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(false);
  const [templateError, setTemplateError] = useState<string | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);

  // Unternehmens-Einstellungen (rein clientseitig, Speicherung in localStorage)
  const [companySettings, setCompanySettings] = useState({
    name: "",
    street: "",
    zip: "",
    city: "",
    vatId: "",
    companyId: "",
  });
  const [companyMessage, setCompanyMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  type TeamMember = {
    id: string;
    name: string;
    role: "inhaber" | "projektleitung" | "ausführung" | "backoffice";
    active: boolean;
    canOffers: boolean;
    canInvoices: boolean;
    canDashboard: boolean;
    isAdmin: boolean;
  };

  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([
    {
      id: "owner",
      name: user?.name || "Inhaber",
      role: "inhaber",
      active: true,
      canOffers: true,
      canInvoices: true,
      canDashboard: true,
      isAdmin: true,
    },
  ]);
  const [teamMessage, setTeamMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Allgemeine UI-Einstellungen
  const [generalSettings, setGeneralSettings] = useState({
    language: "de",
    theme: "light" as "light" | "dark" | "system",
    timeFormat24h: true,
    showTips: true,
  });
  const [generalMessage, setGeneralMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Benachrichtigungen (nur lokal)
  const [notificationSettings, setNotificationSettings] = useState({
    email: true,
    inApp: true,
    teamWeekly: false,
  });

  // Abrechnung & Pläne (nur lokal, konzeptionell)
  const [billingSettings, setBillingSettings] = useState({
    paymentTermDays: "14",
    showNetTotals: true,
  });

  // Welche Übersichtskachel aktiv ist
  const [activeOverviewSection, setActiveOverviewSection] = useState<"general" | "notifications" | "billing">(
    "general",
  );

  const templateStorageKey = useMemo(
    () => (user?.id ? `kalkulai_offer_template_${user.id}` : "kalkulai_offer_template_guest"),
    [user?.id],
  );

  const handleTemplateSelect = useCallback(
    (templateId: string) => {
      setSelectedTemplateId(templateId);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(templateStorageKey, templateId);
        // Custom Event, damit z. B. die Angebotsansicht live reagieren kann
        window.dispatchEvent(new CustomEvent("kalkulai-template-changed", { detail: { templateId } }));
      }
    },
    [templateStorageKey],
  );

  const activeTemplate = useMemo(() => {
    if (!offerTemplates.length) {
      return selectedTemplateId
        ? {
            id: selectedTemplateId,
            label: selectedTemplateId,
            tagline: "",
            description: "",
            accent: "#0f172a",
            background: "#f4f4f5",
          }
        : null;
    }
    if (selectedTemplateId) {
      return offerTemplates.find((tpl) => tpl.id === selectedTemplateId) ?? null;
    }
    return offerTemplates.find((tpl) => tpl.is_default) ?? offerTemplates[0] ?? null;
  }, [offerTemplates, selectedTemplateId]);

  // Templates initial laden
  useEffect(() => {
    let isMounted = true;
    setIsLoadingTemplates(true);
    api
      .pdfTemplates()
      .then((res) => {
        if (!isMounted) return;
        setOfferTemplates(res.templates || []);
        setTemplateError(null);
      })
      .catch((err: any) => {
        if (!isMounted) return;
        setTemplateError(err?.message || "Layouts konnten nicht geladen werden.");
      })
      .finally(() => {
        if (isMounted) {
          setIsLoadingTemplates(false);
        }
      });
    return () => {
      isMounted = false;
    };
  }, []);

  // Auswahl aus localStorage übernehmen / Fallback auf Default setzen
  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(templateStorageKey);
    if (stored) {
      setSelectedTemplateId(stored);
      return;
    }
    if (offerTemplates.length) {
      const fallback = offerTemplates.find((tpl) => tpl.is_default) ?? offerTemplates[0];
      if (fallback) {
        handleTemplateSelect(fallback.id);
      }
    }
  }, [templateStorageKey, offerTemplates, handleTemplateSelect]);

  // Unternehmens-/Team-/Allgemein-Einstellungen aus localStorage laden
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const storedCompany = window.localStorage.getItem("kalkulai_company_profile");
      if (storedCompany) {
        const parsed = JSON.parse(storedCompany);
        setCompanySettings((prev) => ({ ...prev, ...parsed }));
      }
    } catch {
      // ignore parse errors
    }
    try {
      const storedTeam = window.localStorage.getItem("kalkulai_team_members");
      if (storedTeam) {
        const parsed = JSON.parse(storedTeam) as TeamMember[];
        if (Array.isArray(parsed) && parsed.length > 0) {
          setTeamMembers(parsed);
        }
      }
    } catch {
      // ignore
    }
    try {
      const storedGeneral = window.localStorage.getItem("kalkulai_general_settings");
      if (storedGeneral) {
        const parsed = JSON.parse(storedGeneral);
        setGeneralSettings((prev) => ({ ...prev, ...parsed }));
      }
    } catch {
      // ignore
    }
  }, []);

  const settingsCategories = [
    {
      title: "Allgemeine Einstellungen",
      description: "Sprache, Zeitformat und Darstellung der Oberfläche anpassen.",
    },
    {
      title: "Benachrichtigungen",
      description: "E-Mail-, In-App- und Team-Updates gezielt konfigurieren.",
    },
    {
      title: "Abrechnung & Pläne",
      description: "Tarifübersicht, Rechnungsarchiv und Zahlungsmethoden einsehen.",
    },
  ];

  const openProfileDialog = () => {
    setProfileName(user?.name || "");
    setProfileMessage(null);
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setPasswordMessage(null);
    setNewEmail("");
    setEmailPassword("");
    setEmailMessage(null);
    setIsProfileDialogOpen(true);
  };

  const openSettingsDialog = () => {
    setIsSettingsDialogOpen(true);
  };

  const handleSaveCompany = () => {
    try {
      if (typeof window !== "undefined") {
        window.localStorage.setItem("kalkulai_company_profile", JSON.stringify(companySettings));
      }
      setCompanyMessage({ type: "success", text: "Unternehmensdaten gespeichert (nur lokal)." });
    } catch (err: any) {
      setCompanyMessage({
        type: "error",
        text: err?.message || "Konnte die Daten nicht speichern.",
      });
    }
  };

  const handleSaveTeam = () => {
    try {
      if (typeof window !== "undefined") {
        window.localStorage.setItem("kalkulai_team_members", JSON.stringify(teamMembers));
      }
      setTeamMessage({ type: "success", text: "Team & Rechte gespeichert (nur lokal)." });
    } catch (err: any) {
      setTeamMessage({
        type: "error",
        text: err?.message || "Konnte die Daten nicht speichern.",
      });
    }
  };

  const handleAddTeamMember = () => {
    setTeamMembers((prev) => [
      ...prev,
      {
        id: `member-${Date.now()}`,
        name: "",
        role: "ausführung",
        active: true,
        canOffers: true,
        canInvoices: false,
        canDashboard: false,
        isAdmin: false,
      },
    ]);
  };

  const handleUpdateTeamMember = <K extends keyof TeamMember>(
    id: string,
    key: K,
    value: TeamMember[K],
  ) => {
    setTeamMembers((prev) => prev.map((m) => (m.id === id ? { ...m, [key]: value } : m)));
  };

  const handleRemoveTeamMember = (id: string) => {
    setTeamMembers((prev) => prev.filter((m) => m.id !== id));
  };

  const handleSaveGeneral = () => {
    try {
      if (typeof window !== "undefined") {
        window.localStorage.setItem("kalkulai_general_settings", JSON.stringify(generalSettings));
      }
      setGeneralMessage({ type: "success", text: "Allgemeine Einstellungen gespeichert (nur lokal)." });
    } catch (err: any) {
      setGeneralMessage({
        type: "error",
        text: err?.message || "Konnte die Einstellungen nicht speichern.",
      });
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-slate-50 to-blue-50/30">
      {/* Header / Navigation */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-xl border-b border-slate-200/60 shadow-sm">
        <div className="max-w-[1600px] mx-auto px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <Link to="/" className="flex items-center gap-3 group">
              <img
                src="/lovable-uploads/c512bb54-21ad-4d03-a77e-daa5f6a25264.png"
                alt="KalkulAI Logo"
                className="h-11 w-auto transition-transform group-hover:scale-105"
              />
            </Link>

            {/* Navigation */}
            <nav className="hidden md:flex items-center gap-1">
              {navItems.map((item) => {
                const isActive = location.pathname === item.path;
                const Icon = item.icon;
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={`relative flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                      isActive
                        ? "text-primary bg-primary/8"
                        : "text-slate-600 hover:text-slate-900 hover:bg-slate-100/70"
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                    <span>{item.label}</span>
                    {isActive && (
                      <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-8 h-0.5 bg-primary rounded-full" />
                    )}
                  </Link>
                );
              })}
            </nav>

            {/* User Menu */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  className="flex items-center gap-2.5 px-3 py-2 rounded-xl hover:bg-slate-100/80 transition-colors"
                >
                  <div className="w-9 h-9 rounded-full bg-gradient-to-br from-primary to-blue-600 flex items-center justify-center shadow-md shadow-primary/20">
                    <span className="text-sm font-bold text-white">
                      {(user?.name || user?.email || "U").charAt(0).toUpperCase()}
                    </span>
                  </div>
                  <div className="hidden sm:block text-left">
                    <p className="text-sm font-semibold text-slate-800 truncate max-w-[100px]">
                      {user?.name || "Benutzer"}
                    </p>
                  </div>
                  <ChevronDown className="h-4 w-4 text-slate-400" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56 p-1.5">
                <div className="px-3 py-2.5 mb-1">
                  <p className="text-sm font-semibold text-slate-900 truncate">{user?.name || "Benutzer"}</p>
                  <p className="text-xs text-slate-500 truncate">{user?.email}</p>
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={openProfileDialog} className="gap-2.5 py-2.5 cursor-pointer">
                  <User className="h-4 w-4 text-slate-500" />
                  <span>Mein Profil</span>
                </DropdownMenuItem>
                <DropdownMenuItem 
                  onSelect={openSettingsDialog} 
                  className="gap-2.5 py-2.5 cursor-pointer"
                >
                  <Settings className="h-4 w-4 text-slate-500" />
                  <span>Einstellungen</span>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={logout}
                  className="gap-2.5 py-2.5 cursor-pointer text-red-600 focus:text-red-600 focus:bg-red-50"
                >
                  <LogOut className="h-4 w-4" />
                  <span>Abmelden</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-[1600px] mx-auto px-6 lg:px-8 py-6">
        {children}
      </main>

      {/* Old Profile Dialog - Disabled, using ProfileModal instead */}
      {false && (
      <Dialog open={isProfileDialogOpen} onOpenChange={setIsProfileDialogOpen}>
        <DialogContent className="max-w-xl max-h-[85vh] overflow-y-auto">
          <DialogHeader className="space-y-1 text-left">
            <DialogTitle>Mein Profil</DialogTitle>
            <DialogDescription>
              Verwalte deine persönlichen Daten und Zugangsdaten.
            </DialogDescription>
          </DialogHeader>

          <Tabs defaultValue="profile" className="w-full">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="profile">Profil</TabsTrigger>
              <TabsTrigger value="password">Passwort</TabsTrigger>
              <TabsTrigger value="email">E-Mail</TabsTrigger>
            </TabsList>

            {/* Profile Tab */}
            <TabsContent value="profile" className="mt-4 space-y-4">
              <div className="flex items-center gap-4 p-4 bg-muted/40 rounded-lg">
                <div className="w-16 h-16 rounded-full bg-gradient-to-br from-primary to-blue-600 flex items-center justify-center">
                  <span className="text-2xl font-semibold text-white">
                    {(user?.name || user?.email || "U").charAt(0).toUpperCase()}
                  </span>
                </div>
                <div>
                  <p className="font-medium">{user?.name || "Kein Name"}</p>
                  <p className="text-sm text-muted-foreground">{user?.email}</p>
                </div>
              </div>

              <div className="space-y-3">
                <div className="space-y-2">
                  <Label htmlFor="profile-name">Name</Label>
                  <Input
                    id="profile-name"
                    value={profileName}
                    onChange={(e) => setProfileName(e.target.value)}
                    placeholder="Dein Name"
                  />
                </div>

                {profileMessage && (
                  <div className={`p-3 rounded-lg text-sm ${
                    profileMessage.type === "success"
                      ? "bg-green-50 border border-green-200 text-green-700"
                      : "bg-red-50 border border-red-200 text-red-700"
                  }`}>
                    {profileMessage.text}
                  </div>
                )}

                <Button
                  onClick={async () => {
                    setIsUpdatingProfile(true);
                    setProfileMessage(null);
                    try {
                      await updateProfile(profileName);
                      setProfileMessage({ type: "success", text: "Profil erfolgreich aktualisiert" });
                    } catch (err: any) {
                      setProfileMessage({ type: "error", text: err.message || "Fehler beim Aktualisieren" });
                    } finally {
                      setIsUpdatingProfile(false);
                    }
                  }}
                  disabled={isUpdatingProfile || profileName === user?.name}
                  className="w-full"
                >
                  {isUpdatingProfile ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Wird gespeichert...
                    </>
                  ) : (
                    <>
                      <Check className="mr-2 h-4 w-4" />
                      Name speichern
                    </>
                  )}
                </Button>
              </div>
            </TabsContent>

            {/* Password Tab */}
            <TabsContent value="password" className="mt-4 space-y-4">
              <div className="space-y-3">
                <div className="space-y-2">
                  <Label htmlFor="current-password">Aktuelles Passwort</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="current-password"
                      type={showPasswords ? "text" : "password"}
                      value={currentPassword}
                      onChange={(e) => setCurrentPassword(e.target.value)}
                      className="pl-10 pr-10"
                      placeholder="••••••••"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPasswords(!showPasswords)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                      {showPasswords ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="new-password">Neues Passwort</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="new-password"
                      type={showPasswords ? "text" : "password"}
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      className="pl-10"
                      placeholder="Mindestens 6 Zeichen"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="confirm-password">Passwort bestätigen</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="confirm-password"
                      type={showPasswords ? "text" : "password"}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      className="pl-10"
                      placeholder="Passwort wiederholen"
                    />
                  </div>
                </div>

                {passwordMessage && (
                  <div className={`p-3 rounded-lg text-sm ${
                    passwordMessage.type === "success"
                      ? "bg-green-50 border border-green-200 text-green-700"
                      : "bg-red-50 border border-red-200 text-red-700"
                  }`}>
                    {passwordMessage.text}
                  </div>
                )}

                <Button
                  onClick={async () => {
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
                    } catch (err: any) {
                      setPasswordMessage({ type: "error", text: err.message || "Fehler beim Ändern" });
                    } finally {
                      setIsChangingPassword(false);
                    }
                  }}
                  disabled={isChangingPassword || !currentPassword || !newPassword || !confirmPassword}
                  className="w-full"
                >
                  {isChangingPassword ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Wird geändert...
                    </>
                  ) : (
                    <>
                      <Lock className="mr-2 h-4 w-4" />
                      Passwort ändern
                    </>
                  )}
                </Button>
              </div>
            </TabsContent>

            {/* Email Tab */}
            <TabsContent value="email" className="mt-4 space-y-4">
              <div className="p-3 bg-muted/40 rounded-lg">
                <p className="text-sm text-muted-foreground">
                  Aktuelle E-Mail: <span className="font-medium text-foreground">{user?.email}</span>
                </p>
              </div>

              <div className="space-y-3">
                <div className="space-y-2">
                  <Label htmlFor="new-email">Neue E-Mail-Adresse</Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="new-email"
                      type="email"
                      value={newEmail}
                      onChange={(e) => setNewEmail(e.target.value)}
                      className="pl-10"
                      placeholder="neue@email.de"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="email-password">Passwort zur Bestätigung</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="email-password"
                      type="password"
                      value={emailPassword}
                      onChange={(e) => setEmailPassword(e.target.value)}
                      className="pl-10"
                      placeholder="Dein aktuelles Passwort"
                    />
                  </div>
                </div>

                {emailMessage && (
                  <div className={`p-3 rounded-lg text-sm ${
                    emailMessage.type === "success"
                      ? "bg-green-50 border border-green-200 text-green-700"
                      : "bg-red-50 border border-red-200 text-red-700"
                  }`}>
                    {emailMessage.text}
                  </div>
                )}

                <Button
                  onClick={async () => {
                    setEmailMessage(null);
                    setIsChangingEmail(true);
                    try {
                      await changeEmail(newEmail, emailPassword);
                      setEmailMessage({ type: "success", text: "E-Mail erfolgreich geändert" });
                      setNewEmail("");
                      setEmailPassword("");
                    } catch (err: any) {
                      setEmailMessage({ type: "error", text: err.message || "Fehler beim Ändern" });
                    } finally {
                      setIsChangingEmail(false);
                    }
                  }}
                  disabled={isChangingEmail || !newEmail || !emailPassword}
                  className="w-full"
                >
                  {isChangingEmail ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Wird geändert...
                    </>
                  ) : (
                    <>
                      <Mail className="mr-2 h-4 w-4" />
                      E-Mail ändern
                    </>
                  )}
                </Button>
              </div>
            </TabsContent>
          </Tabs>

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsProfileDialogOpen(false)}>
              Schließen
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      )}

      {/* Profile Modal */}
      <ProfileModal open={isProfileDialogOpen} onOpenChange={setIsProfileDialogOpen} />

      {/* Settings Modal */}
      <SettingsModal open={isSettingsDialogOpen} onOpenChange={setIsSettingsDialogOpen} />
                      </div>
  );
}
