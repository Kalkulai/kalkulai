import { useState, useEffect } from "react";
import { 
  Plus, Search, FileText, Calendar, Euro, MoreVertical, 
  Pencil, Copy, Trash2, Download, Eye, Filter, Loader2,
  CheckCircle, Clock, XCircle, Send
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/contexts/AuthContext";
import { api, Offer, OfferPosition } from "@/lib/api";

type Props = {
  onEditOffer: (offer: Offer) => void;
  onNewOffer: () => void;
};

const STATUS_CONFIG = {
  draft: { label: "Entwurf", icon: Clock, color: "bg-gray-100 text-gray-700" },
  sent: { label: "Gesendet", icon: Send, color: "bg-blue-100 text-blue-700" },
  accepted: { label: "Angenommen", icon: CheckCircle, color: "bg-green-100 text-green-700" },
  rejected: { label: "Abgelehnt", icon: XCircle, color: "bg-red-100 text-red-700" },
};

export default function OfferLibrary({ onEditOffer, onNewOffer }: Props) {
  const { token } = useAuth();
  const [offers, setOffers] = useState<Offer[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [offerToDelete, setOfferToDelete] = useState<Offer | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Load offers
  useEffect(() => {
    loadOffers();
  }, [token]);

  const loadOffers = async () => {
    if (!token) return;
    setIsLoading(true);
    try {
      const response = await api.offers.list(token);
      setOffers(response.offers);
    } catch (err) {
      console.error("Failed to load offers:", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDuplicate = async (offer: Offer) => {
    if (!token) return;
    try {
      await api.offers.duplicate(token, offer.id);
      loadOffers();
    } catch (err) {
      console.error("Failed to duplicate offer:", err);
    }
  };

  const handleDelete = async () => {
    if (!token || !offerToDelete) return;
    setIsDeleting(true);
    try {
      await api.offers.delete(token, offerToDelete.id);
      setOffers(offers.filter(o => o.id !== offerToDelete.id));
      setDeleteDialogOpen(false);
      setOfferToDelete(null);
    } catch (err) {
      console.error("Failed to delete offer:", err);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleStatusChange = async (offer: Offer, newStatus: string) => {
    if (!token) return;
    try {
      const response = await api.offers.update(token, offer.id, { status: newStatus });
      setOffers(offers.map(o => o.id === offer.id ? response.offer : o));
    } catch (err) {
      console.error("Failed to update status:", err);
    }
  };

  // Filter offers
  const filteredOffers = offers.filter(offer => {
    const matchesSearch = searchQuery === "" || 
      offer.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (offer.kunde?.toLowerCase().includes(searchQuery.toLowerCase()));
    
    const matchesStatus = statusFilter === "all" || offer.status === statusFilter;
    
    return matchesSearch && matchesStatus;
  });

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString("de-DE", { 
      day: "2-digit", 
      month: "2-digit", 
      year: "numeric" 
    });
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat("de-DE", {
      style: "currency",
      currency: "EUR",
    }).format(amount);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary mx-auto mb-4" />
          <p className="text-muted-foreground">Angebote werden geladen...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-foreground">Bibliothek</h2>
          <p className="text-muted-foreground text-sm mt-1">
            {offers.length} Angebot{offers.length !== 1 ? "e" : ""} gespeichert
          </p>
        </div>
        <Button onClick={onNewOffer} className="gap-2">
          <Plus className="h-4 w-4" />
          Neues Angebot
        </Button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Suche nach Titel oder Kunde..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[180px]">
            <Filter className="h-4 w-4 mr-2" />
            <SelectValue placeholder="Status filtern" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle Status</SelectItem>
            <SelectItem value="draft">Entwurf</SelectItem>
            <SelectItem value="sent">Gesendet</SelectItem>
            <SelectItem value="accepted">Angenommen</SelectItem>
            <SelectItem value="rejected">Abgelehnt</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Offers List */}
      <div className="flex-1 overflow-y-auto space-y-3">
        {filteredOffers.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <FileText className="h-12 w-12 text-muted-foreground/50 mb-4" />
            <h3 className="text-lg font-medium text-foreground mb-2">
              {searchQuery || statusFilter !== "all" 
                ? "Keine Angebote gefunden" 
                : "Noch keine Angebote"}
            </h3>
            <p className="text-muted-foreground text-sm mb-4">
              {searchQuery || statusFilter !== "all"
                ? "Versuche andere Suchkriterien"
                : "Erstelle dein erstes Angebot, um loszulegen"}
            </p>
            {!searchQuery && statusFilter === "all" && (
              <Button onClick={onNewOffer} variant="outline" className="gap-2">
                <Plus className="h-4 w-4" />
                Angebot erstellen
              </Button>
            )}
          </div>
        ) : (
          filteredOffers.map((offer) => {
            const statusConfig = STATUS_CONFIG[offer.status] || STATUS_CONFIG.draft;
            const StatusIcon = statusConfig.icon;
            
            return (
              <Card
                key={offer.id}
                className="p-4 hover:border-primary/50 transition-colors cursor-pointer group"
                onClick={() => onEditOffer(offer)}
              >
                <div className="flex items-start justify-between gap-4">
                  {/* Left: Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-semibold text-foreground truncate">
                        {offer.title}
                      </h3>
                      <Badge variant="secondary" className={`${statusConfig.color} flex-shrink-0`}>
                        <StatusIcon className="h-3 w-3 mr-1" />
                        {statusConfig.label}
                      </Badge>
                    </div>
                    
                    {offer.kunde && (
                      <p className="text-sm text-muted-foreground truncate mb-2">
                        {offer.kunde}
                      </p>
                    )}
                    
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        {formatDate(offer.updated_at)}
                      </span>
                      <span className="flex items-center gap-1">
                        <FileText className="h-3 w-3" />
                        {offer.positions.length} Position{offer.positions.length !== 1 ? "en" : ""}
                      </span>
                    </div>
                  </div>

                  {/* Right: Amount + Actions */}
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <p className="font-semibold text-foreground tabular-nums">
                        {formatCurrency(offer.netto_summe)}
                      </p>
                      <p className="text-xs text-muted-foreground">Netto</p>
                    </div>
                    
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                        <Button 
                          variant="ghost" 
                          size="icon" 
                          className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
                        <DropdownMenuItem onClick={() => onEditOffer(offer)}>
                          <Pencil className="h-4 w-4 mr-2" />
                          Bearbeiten
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleDuplicate(offer)}>
                          <Copy className="h-4 w-4 mr-2" />
                          Duplizieren
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem 
                          onClick={() => handleStatusChange(offer, "sent")}
                          disabled={offer.status === "sent"}
                        >
                          <Send className="h-4 w-4 mr-2" />
                          Als gesendet markieren
                        </DropdownMenuItem>
                        <DropdownMenuItem 
                          onClick={() => handleStatusChange(offer, "accepted")}
                          disabled={offer.status === "accepted"}
                        >
                          <CheckCircle className="h-4 w-4 mr-2" />
                          Als angenommen markieren
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          className="text-destructive focus:text-destructive"
                          onClick={() => {
                            setOfferToDelete(offer);
                            setDeleteDialogOpen(true);
                          }}
                        >
                          <Trash2 className="h-4 w-4 mr-2" />
                          Löschen
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              </Card>
            );
          })
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Angebot löschen?</DialogTitle>
            <DialogDescription>
              Möchtest du das Angebot "{offerToDelete?.title}" wirklich löschen? 
              Diese Aktion kann nicht rückgängig gemacht werden.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button 
              variant="outline" 
              onClick={() => setDeleteDialogOpen(false)}
              disabled={isDeleting}
            >
              Abbrechen
            </Button>
            <Button 
              variant="destructive" 
              onClick={handleDelete}
              disabled={isDeleting}
            >
              {isDeleting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Wird gelöscht...
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4 mr-2" />
                  Löschen
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

