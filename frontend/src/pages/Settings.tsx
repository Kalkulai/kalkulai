import { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";
import { X } from "lucide-react";

// Import sub-pages
import OverviewGeneral from "@/components/settings/OverviewGeneral";
import OverviewNotifications from "@/components/settings/OverviewNotifications";
import OverviewBilling from "@/components/settings/OverviewBilling";
import OverviewSecurity from "@/components/settings/OverviewSecurity";
import OverviewIntegrations from "@/components/settings/OverviewIntegrations";
import CompanyProfile from "@/components/settings/CompanyProfile";
import CompanyEmployees from "@/components/settings/CompanyEmployees";
import CompanyLocations from "@/components/settings/CompanyLocations";
import CompanyAccounting from "@/components/settings/CompanyAccounting";
import OffersDesign from "@/components/settings/OffersDesign";
import OffersProducts from "@/components/settings/OffersProducts";
import OffersPricing from "@/components/settings/OffersPricing";
import OffersAutomation from "@/components/settings/OffersAutomation";
import OffersGuard from "@/components/settings/OffersGuard";
import OffersTemplates from "@/components/settings/OffersTemplates";
import OffersDocuments from "@/components/settings/OffersDocuments";

type TabType = "overview" | "company" | "offers";
type OverviewCategory = "general" | "notifications" | "billing" | "security" | "integrations";
type CompanyCategory = "profile" | "employees" | "locations" | "accounting";
type OffersCategory = "design" | "products" | "pricing" | "automation" | "guard" | "templates" | "documents";

interface CategoryCard {
  id: string;
  title: string;
  description: string;
}

const overviewCategories: CategoryCard[] = [
  {
    id: "general",
    title: "Allgemeine Einstellungen",
    description: "Sprache, Zeitformat und Darstellung der Oberfläche anpassen.",
  },
  {
    id: "notifications",
    title: "Benachrichtigungen",
    description: "E-Mail-, In-App- und Team-Updates gezielt konfigurieren.",
  },
  {
    id: "billing",
    title: "Abrechnung & Pläne",
    description: "Tarifübersicht, Rechnungsarchiv und Zahlungsmethoden einsehen.",
  },
  {
    id: "security",
    title: "Sicherheit & Datenschutz",
    description: "Passwort, Zwei-Faktor-Authentifizierung und Datenschutzeinstellungen verwalten.",
  },
  {
    id: "integrations",
    title: "Integrationen",
    description: "Verbundene Apps, API-Zugriff und Webhooks konfigurieren.",
  },
];

const companyCategories: CategoryCard[] = [
  {
    id: "profile",
    title: "Unternehmensprofil",
    description: "Stammdaten deines Betriebs. Diese Angaben werden perspektivisch für Kopfzeilen und Dokumente verwendet.",
  },
  {
    id: "employees",
    title: "Mitarbeiter & Zugriffsrechte",
    description: "Lege fest, wer welche Bereiche nutzen darf. Diese Übersicht dient aktuell als Rechtekonzept und wird lokal gespeichert.",
  },
  {
    id: "locations",
    title: "Standorte & Filialen",
    description: "Verwalte mehrere Standorte, Lager und Lieferadressen.",
  },
  {
    id: "accounting",
    title: "Buchhaltung",
    description: "Bankverbindungen, Steuereinstellungen und Kontenplan.",
  },
];

const offersCategories: CategoryCard[] = [
  {
    id: "design",
    title: "Dokument-Design",
    description: "Wähle das Layout, das am besten zu deiner Außendarstellung passt.",
  },
  {
    id: "products",
    title: "Produktverwaltung",
    description: "Verwalte Produkte und Katalogeinträge, die für Angebote & Rechnungen genutzt werden.",
  },
  {
    id: "pricing",
    title: "Preisgestaltung",
    description: "Standardrabatte, Mehrwertsteuersätze und Zuschläge definieren.",
  },
  {
    id: "automation",
    title: "Automatisierung",
    description: "Rechnungsnummern, Fälligkeitsfristen und automatische Mahnungen konfigurieren.",
  },
  {
    id: "guard",
    title: "Vergessener Wächter",
    description: "Lege fest, welche Posten dein Wächter bei der Angebotserstellung zusätzlich vorschlagen soll.",
  },
  {
    id: "templates",
    title: "Textbausteine & Vorlagen",
    description: "Begrüßungstexte, Zahlungsbedingungen und E-Mail-Vorlagen.",
  },
  {
    id: "documents",
    title: "Dokumentenverwaltung",
    description: "Archivierung, Standardordner und Aufbewahrungsfristen.",
  },
];

export default function Settings() {
  const navigate = useNavigate();
  const location = useLocation();
  const { toast } = useToast();
  
  // Initialize from URL
  const pathParts = location.pathname.split("/").filter(Boolean);
  const getInitialTab = (): TabType => {
    if (pathParts[0] === "settings" && pathParts[1]) {
      if (pathParts[1] === "overview" || pathParts[1] === "company" || pathParts[1] === "offers") {
        return pathParts[1] as TabType;
      }
    }
    return "overview";
  };
  
  const [activeTab, setActiveTab] = useState<TabType>(getInitialTab());
  const [activeCategory, setActiveCategory] = useState<string | null>(
    pathParts[0] === "settings" && pathParts[2] ? pathParts[2] : null
  );

  // Parse URL to determine active tab and category
  useEffect(() => {
    const pathParts = location.pathname.split("/").filter(Boolean);
    if (pathParts[0] === "settings") {
      if (pathParts[1] === "overview" || pathParts[1] === "company" || pathParts[1] === "offers") {
        setActiveTab(pathParts[1] as TabType);
        if (pathParts[2]) {
          setActiveCategory(pathParts[2]);
        } else {
          setActiveCategory(null);
        }
      } else if (!pathParts[1] || pathParts[1] === "") {
        // If no tab specified, redirect to overview
        navigate("/settings/overview", { replace: true });
      } else {
        // Invalid tab, redirect to overview
        navigate("/settings/overview", { replace: true });
      }
    }
  }, [location.pathname, navigate]);

  const handleCategoryClick = (categoryId: string) => {
    navigate(`/settings/${activeTab}/${categoryId}`);
    setActiveCategory(categoryId);
  };

  const handleBackToOverview = () => {
    navigate(`/settings/${activeTab}`);
    setActiveCategory(null);
  };

  const getBreadcrumbs = () => {
    const crumbs = ["Einstellungen"];
    if (activeTab === "overview") {
      crumbs.push("Übersicht");
      if (activeCategory) {
        const category = overviewCategories.find((c) => c.id === activeCategory);
        if (category) crumbs.push(category.title);
      }
    } else if (activeTab === "company") {
      crumbs.push("Unternehmen");
      if (activeCategory) {
        const category = companyCategories.find((c) => c.id === activeCategory);
        if (category) crumbs.push(category.title);
      }
    } else if (activeTab === "offers") {
      crumbs.push("Angebote & Rechnungen");
      if (activeCategory) {
        const category = offersCategories.find((c) => c.id === activeCategory);
        if (category) crumbs.push(category.title);
      }
    }
    return crumbs;
  };

  const handleTabChange = (value: string) => {
    setActiveTab(value as TabType);
    setActiveCategory(null);
    navigate(`/settings/${value}`);
  };

  const renderCategoryContent = () => {
    if (!activeCategory) return null;

    if (activeTab === "overview") {
      switch (activeCategory as OverviewCategory) {
        case "general":
          return <OverviewGeneral onBack={handleBackToOverview} />;
        case "notifications":
          return <OverviewNotifications onBack={handleBackToOverview} />;
        case "billing":
          return <OverviewBilling onBack={handleBackToOverview} />;
        case "security":
          return <OverviewSecurity onBack={handleBackToOverview} />;
        case "integrations":
          return <OverviewIntegrations onBack={handleBackToOverview} />;
        default:
          return null;
      }
    } else if (activeTab === "company") {
      switch (activeCategory as CompanyCategory) {
        case "profile":
          return <CompanyProfile onBack={handleBackToOverview} />;
        case "employees":
          return <CompanyEmployees onBack={handleBackToOverview} />;
        case "locations":
          return <CompanyLocations onBack={handleBackToOverview} />;
        case "accounting":
          return <CompanyAccounting onBack={handleBackToOverview} />;
        default:
          return null;
      }
    } else if (activeTab === "offers") {
      switch (activeCategory as OffersCategory) {
        case "design":
          return <OffersDesign onBack={handleBackToOverview} />;
        case "products":
          return <OffersProducts onBack={handleBackToOverview} />;
        case "pricing":
          return <OffersPricing onBack={handleBackToOverview} />;
        case "automation":
          return <OffersAutomation onBack={handleBackToOverview} />;
        case "guard":
          return <OffersGuard onBack={handleBackToOverview} />;
        case "templates":
          return <OffersTemplates onBack={handleBackToOverview} />;
        case "documents":
          return <OffersDocuments onBack={handleBackToOverview} />;
        default:
          return null;
      }
    }
    return null;
  };

  const renderCategoryOverview = () => {
    const categories = activeTab === "overview" ? overviewCategories : activeTab === "company" ? companyCategories : offersCategories;

    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {categories.map((category) => (
          <Card
            key={category.id}
            className="cursor-pointer transition-all hover:border-primary/40 hover:shadow-md"
            onClick={() => handleCategoryClick(category.id)}
          >
            <CardHeader>
              <CardTitle className="text-base">{category.title}</CardTitle>
              <CardDescription className="text-sm">{category.description}</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </div>
    );
  };

  const breadcrumbs = getBreadcrumbs();

  return (
    <div className="w-full space-y-6">
      {/* Header with Close Button */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Einstellungen</h1>
          <p className="text-muted-foreground mt-1">Richte KalkulAI nach deinen Arbeitsabläufen aus</p>
        </div>
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
          <X className="h-5 w-5" />
        </Button>
      </div>

      {/* Breadcrumbs */}
      {breadcrumbs.length > 1 && (
        <nav className="flex items-center gap-2 text-sm text-muted-foreground">
          {breadcrumbs.map((crumb, index) => (
            <div key={index} className="flex items-center gap-2">
              {index > 0 && <span>/</span>}
              {index === breadcrumbs.length - 1 ? (
                <span className="text-foreground font-medium">{crumb}</span>
              ) : (
                <button
                  onClick={() => {
                    if (index === 0) {
                      navigate("/settings/overview");
                    } else if (index === 1) {
                      navigate(`/settings/${activeTab}`);
                    }
                  }}
                  className="hover:text-foreground transition-colors"
                >
                  {crumb}
                </button>
              )}
            </div>
          ))}
        </nav>
      )}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <TabsList className="grid w-full grid-cols-3 rounded-xl bg-slate-100 p-1">
          <TabsTrigger value="overview">Übersicht</TabsTrigger>
          <TabsTrigger value="company">Unternehmen</TabsTrigger>
          <TabsTrigger value="offers">Angebote & Rechnungen</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-6 space-y-4">
          {activeCategory ? renderCategoryContent() : renderCategoryOverview()}
        </TabsContent>

        <TabsContent value="company" className="mt-6 space-y-4">
          {activeCategory ? renderCategoryContent() : renderCategoryOverview()}
        </TabsContent>

        <TabsContent value="offers" className="mt-6 space-y-4">
          {activeCategory ? renderCategoryContent() : renderCategoryOverview()}
        </TabsContent>
      </Tabs>
    </div>
  );
}

