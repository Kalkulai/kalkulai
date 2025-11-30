import { useState } from "react";
import { Dialog, DialogContent, DialogOverlay } from "@/components/ui/dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

// Import settings components
import OverviewGeneral from "@/components/settings/OverviewGeneral";
import OverviewNotifications from "@/components/settings/OverviewNotifications";
import OverviewBilling from "@/components/settings/OverviewBilling";
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

type CategoryId =
  | "general"
  | "notifications"
  | "billing"
  | "integrations"
  | "company-profile"
  | "employees"
  | "locations"
  | "accounting"
  | "design"
  | "products"
  | "pricing"
  | "automation"
  | "guard"
  | "templates"
  | "documents";

interface Category {
  id: CategoryId;
  label: string;
  section: "overview" | "company" | "offers";
}

const categories: Category[] = [
  // Übersicht
  { id: "general", label: "Allgemeine Einstellungen", section: "overview" },
  { id: "notifications", label: "Benachrichtigungen", section: "overview" },
  { id: "billing", label: "Abrechnung & Pläne", section: "overview" },
  { id: "integrations", label: "Integrationen", section: "overview" },
  // Unternehmen
  { id: "company-profile", label: "Unternehmensprofil", section: "company" },
  { id: "employees", label: "Mitarbeiter & Zugriffsrechte", section: "company" },
  { id: "locations", label: "Standorte & Filialen", section: "company" },
  { id: "accounting", label: "Buchhaltung", section: "company" },
  // Angebote & Rechnungen
  { id: "design", label: "Dokument-Design", section: "offers" },
  { id: "products", label: "Produktverwaltung", section: "offers" },
  { id: "pricing", label: "Preisgestaltung", section: "offers" },
  { id: "automation", label: "Automatisierung", section: "offers" },
  { id: "guard", label: "Vergessener Wächter", section: "offers" },
  { id: "templates", label: "Textbausteine & Vorlagen", section: "offers" },
  { id: "documents", label: "Dokumentenverwaltung", section: "offers" },
];

interface SettingsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function SettingsModal({ open, onOpenChange }: SettingsModalProps) {
  const [activeCategory, setActiveCategory] = useState<CategoryId>("general");

  const activeCategoryData = categories.find((c) => c.id === activeCategory);
  const overviewCategories = categories.filter((c) => c.section === "overview");
  const companyCategories = categories.filter((c) => c.section === "company");
  const offersCategories = categories.filter((c) => c.section === "offers");

  const renderContent = () => {
    switch (activeCategory) {
      case "general":
        return <OverviewGeneral onBack={() => {}} />;
      case "notifications":
        return <OverviewNotifications onBack={() => {}} />;
      case "billing":
        return <OverviewBilling onBack={() => {}} />;
      case "integrations":
        return <OverviewIntegrations onBack={() => {}} />;
      case "company-profile":
        return <CompanyProfile onBack={() => {}} />;
      case "employees":
        return <CompanyEmployees onBack={() => {}} />;
      case "locations":
        return <CompanyLocations onBack={() => {}} />;
      case "accounting":
        return <CompanyAccounting onBack={() => {}} />;
      case "design":
        return <OffersDesign onBack={() => {}} />;
      case "products":
        return <OffersProducts onBack={() => {}} />;
      case "pricing":
        return <OffersPricing onBack={() => {}} />;
      case "automation":
        return <OffersAutomation onBack={() => {}} />;
      case "guard":
        return <OffersGuard onBack={() => {}} />;
      case "templates":
        return <OffersTemplates onBack={() => {}} />;
      case "documents":
        return <OffersDocuments onBack={() => {}} />;
      default:
        return null;
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-[1200px] w-[90vw] h-[90vh] max-h-[90vh] p-0 gap-0 overflow-hidden rounded-2xl border-0 shadow-xl [&>button]:hidden"
      >
        {/* Close button - top right */}
        <button
          onClick={() => onOpenChange(false)}
          className="absolute right-4 top-4 z-50 rounded-sm opacity-70 hover:opacity-100 transition-opacity text-[#6B7280] hover:text-[#111827] focus:outline-none focus:ring-2 focus:ring-[#3B82F6] focus:ring-offset-2"
        >
          <X className="h-5 w-5" />
          <span className="sr-only">Schließen</span>
        </button>

        <div className="flex h-full max-h-[90vh]">
          {/* Sidebar */}
          <div className="w-[300px] bg-[#F9FAFB] border-r border-[#E5E7EB] overflow-y-auto flex-shrink-0 h-full">
            <div className="p-6">
              <h2 className="text-lg font-semibold text-[#111827] mb-6">Einstellungen</h2>

              {/* Übersicht Section */}
              <div className="mb-8">
                <h3 className="text-[11px] font-bold text-[#374151] uppercase tracking-widest mb-4 px-4">
                  Übersicht
                </h3>
                <div className="space-y-1">
                  {overviewCategories.map((category) => (
                    <button
                      key={category.id}
                      onClick={() => setActiveCategory(category.id)}
                      className={cn(
                        "w-full text-left px-4 py-3 text-sm font-medium rounded-lg transition-colors",
                        activeCategory === category.id
                          ? "bg-white text-[#3B82F6] font-semibold"
                          : "text-[#111827] hover:bg-white/50"
                      )}
                    >
                      {category.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Unternehmen Section */}
              <div className="mb-8">
                <h3 className="text-[11px] font-bold text-[#374151] uppercase tracking-widest mb-4 px-4">
                  Unternehmen
                </h3>
                <div className="space-y-1">
                  {companyCategories.map((category) => (
                    <button
                      key={category.id}
                      onClick={() => setActiveCategory(category.id)}
                      className={cn(
                        "w-full text-left px-4 py-3 text-sm font-medium rounded-lg transition-colors",
                        activeCategory === category.id
                          ? "bg-white text-[#3B82F6] font-semibold"
                          : "text-[#111827] hover:bg-white/50"
                      )}
                    >
                      {category.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Angebote & Rechnungen Section */}
              <div>
                <h3 className="text-[11px] font-bold text-[#374151] uppercase tracking-widest mb-4 px-4">
                  Angebote & Rechnungen
                </h3>
                <div className="space-y-1">
                  {offersCategories.map((category) => (
                    <button
                      key={category.id}
                      onClick={() => setActiveCategory(category.id)}
                      className={cn(
                        "w-full text-left px-4 py-3 text-sm font-medium rounded-lg transition-colors",
                        activeCategory === category.id
                          ? "bg-white text-[#3B82F6] font-semibold"
                          : "text-[#111827] hover:bg-white/50"
                      )}
                    >
                      {category.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Content Area */}
          <div className="flex-1 overflow-y-auto bg-white flex-shrink min-w-0 h-full">
            <div className="p-8">
              <div className="space-y-6">{renderContent()}</div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

