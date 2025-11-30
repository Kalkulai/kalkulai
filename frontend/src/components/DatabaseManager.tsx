import { useState, useEffect } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/use-toast";
import { api, type AdminProduct, type SynonymMap } from "@/lib/api";
import { 
  Search, 
  Plus, 
  Edit2, 
  Trash2, 
  Upload, 
  Download,
  Package,
  Tag,
  FileUp,
  X,
  Check,
  AlertCircle
} from "lucide-react";

const emptyProduct = { 
  sku: "", 
  name: "", 
  description: "", 
  price_eur: null as number | null,
  unit: null as string | null,
  volume_l: null as number | null,
  category: null as string | null,
  material_type: null as string | null,
  unit_package: null as string | null,
  tags: null as string | null,
  active: true 
};

const DatabaseManager = () => {
  const [companyId, setCompanyId] = useState("demo");
  const [products, setProducts] = useState<AdminProduct[]>([]);
  const [filteredProducts, setFilteredProducts] = useState<AdminProduct[]>([]);
  const [synonyms, setSynonyms] = useState<SynonymMap>({});
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [editForm, setEditForm] = useState<AdminProduct | null>(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [createForm, setCreateForm] = useState(emptyProduct);
  const [synForm, setSynForm] = useState({ canon: "", variants: "" });
  const [csvContent, setCsvContent] = useState("");
  const { toast } = useToast();

  const adminConfigured = Boolean(import.meta.env.VITE_ADMIN_API_KEY);

  // Load data on mount and when companyId changes
  useEffect(() => {
    if (companyId && adminConfigured) {
      loadData();
    }
  }, [companyId]);

  // Filter products based on search and inactive toggle
  useEffect(() => {
    let filtered = products;
    
    // Filter by active status
    if (!showInactive) {
      filtered = filtered.filter(p => p.active);
    }
    
    // Filter by search query
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(p => 
        p.name.toLowerCase().includes(query) ||
        p.sku.toLowerCase().includes(query) ||
        (p.description && p.description.toLowerCase().includes(query))
      );
    }
    
    setFilteredProducts(filtered);
  }, [products, searchQuery, showInactive]);

  const loadData = async () => {
    if (!companyId) return;
    try {
      setLoading(true);
      const [prod, syn] = await Promise.all([
        api.admin.listProducts(companyId, true),
        api.admin.listSynonyms(companyId),
      ]);
      setProducts(prod);
      setSynonyms(syn);
    } catch (e: any) {
      toast({ 
        title: "Fehler beim Laden", 
        description: e?.message || "Daten konnten nicht geladen werden.",
        variant: "destructive" 
      });
    } finally {
      setLoading(false);
    }
  };

  const submitProduct = async (
    payload: { 
      sku: string; 
      name: string; 
      description?: string; 
      price_eur?: number | null;
      unit?: string | null;
      volume_l?: number | null;
      category?: string | null;
      material_type?: string | null;
      unit_package?: string | null;
      tags?: string | null;
      active?: boolean;
    }, 
    isEdit = false
  ) => {
    if (!companyId) return;
    try {
      setLoading(true);
      await api.admin.upsertProduct(companyId, payload);
      
      // Auto-rebuild index after product change
      try {
        await api.admin.rebuildIndex(companyId);
      } catch (indexError) {
        console.warn("Index rebuild failed:", indexError);
        // Don't fail the whole operation if index rebuild fails
      }
      
      await loadData();
      toast({
        title: isEdit ? "✓ Produkt aktualisiert" : "✓ Produkt hinzugefügt",
        description: `${payload.name} wurde erfolgreich gespeichert.`,
      });
      setEditForm(null);
      setCreateDialogOpen(false);
      setCreateForm(emptyProduct);
    } catch (e: any) {
      toast({
        title: "Fehler",
        description: e?.message || "Produkt konnte nicht gespeichert werden.",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (sku: string, name: string) => {
    if (!companyId || !confirm(`"${name}" wirklich deaktivieren?`)) return;
    try {
      setLoading(true);
      await api.admin.deleteProduct(companyId, sku);
      
      // Auto-rebuild index after product deletion
      try {
        await api.admin.rebuildIndex(companyId);
      } catch (indexError) {
        console.warn("Index rebuild failed:", indexError);
      }
      
      await loadData();
      toast({ 
        title: "✓ Produkt deaktiviert", 
        description: `${name} wurde deaktiviert.` 
      });
    } catch (e: any) {
      toast({
        title: "Fehler",
        description: e?.message || "Produkt konnte nicht deaktiviert werden.",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleSynonymSubmit = async () => {
    if (!companyId || !synForm.canon.trim()) return;
    const variants = synForm.variants
      .split(",")
      .map((entry) => entry.trim())
      .filter(Boolean);
    if (!variants.length) {
      toast({
        title: "Fehler",
        description: "Bitte geben Sie mindestens ein Synonym ein.",
        variant: "destructive",
      });
      return;
    }
    try {
      setLoading(true);
      await api.admin.addSynonyms(companyId, synForm.canon, variants);
      await loadData();
      setSynForm({ canon: "", variants: "" });
      toast({ 
        title: "✓ Synonyme gespeichert", 
        description: "Die Synonyme wurden erfolgreich hinzugefügt." 
      });
    } catch (e: any) {
      toast({
        title: "Fehler",
        description: e?.message || "Synonyme konnten nicht gespeichert werden.",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCsvImport = async () => {
    if (!csvContent.trim()) {
      toast({
        title: "Fehler",
        description: "Bitte fügen Sie CSV-Daten ein.",
        variant: "destructive",
      });
      return;
    }

    const lines = csvContent.trim().split("\n");
    if (lines.length < 2) {
      toast({
        title: "Fehler",
        description: "CSV muss mindestens Header und eine Zeile enthalten.",
        variant: "destructive",
      });
      return;
    }

    try {
      setLoading(true);
      let imported = 0;
      let errors = 0;

      // Parse header to get column names
      const header = lines[0].split(",").map(h => h.trim().toLowerCase().replace(/^"|"$/g, ""));
      
      // Skip header, process data rows
      for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;

        const parts = line.split(",").map(p => p.trim().replace(/^"|"$/g, ""));
        if (parts.length < 2) {
          errors++;
          continue;
        }

        // Map CSV columns to product object
        const product: any = {};
        header.forEach((col, idx) => {
          const value = parts[idx];
          if (!value) return;
          
          // Map column names to product fields
          if (col === "sku") product.sku = value;
          else if (col === "name") product.name = value;
          else if (col === "description") product.description = value;
          else if (col === "price_eur" || col === "price") product.price_eur = parseFloat(value) || null;
          else if (col === "unit") product.unit = value;
          else if (col === "volume_l" || col === "volume") product.volume_l = parseFloat(value) || null;
          else if (col === "category") product.category = value;
          else if (col === "material_type") product.material_type = value;
          else if (col === "unit_package") product.unit_package = value;
          else if (col === "tags") product.tags = value;
          else if (col === "active") product.active = value.toLowerCase() === "true" || value === "1";
        });

        if (!product.sku || !product.name) {
          errors++;
          continue;
        }

        // Set defaults
        if (product.active === undefined) product.active = true;

        try {
          await api.admin.upsertProduct(companyId, product);
          imported++;
        } catch (e) {
          errors++;
        }
      }

    // Auto-rebuild index after CSV import
    try {
      await api.admin.rebuildIndex(companyId);
    } catch (indexError) {
      console.warn("Index rebuild failed:", indexError);
    }

    await loadData();
    setCsvContent("");

    toast({
      title: `✓ Import abgeschlossen`,
      description: `${imported} Produkte importiert${errors > 0 ? `, ${errors} Fehler` : ""}.`,
    });
    } catch (e: any) {
      toast({
        title: "Fehler beim Import",
        description: e?.message || "CSV konnte nicht importiert werden.",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const exportCsv = async () => {
    try {
      setLoading(true);
      // Lade alle Produkte direkt für den Export (ohne Limit)
      const allProducts = await api.admin.listProducts(companyId, true, 10000);
      
      const csv = [
        "sku,name,description,unit,volume_l,price_eur,active,category,material_type,unit_package,tags",
        ...allProducts.map(p => 
          `"${p.sku}","${p.name}","${p.description || ""}","${p.unit || ""}",${p.volume_l || ""},${p.price_eur || ""},${p.active},"${p.category || ""}","${p.material_type || ""}","${p.unit_package || ""}","${p.tags || ""}"`
        )
      ].join("\n");

      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `produkte_${companyId}_${new Date().toISOString().split("T")[0]}.csv`;
      link.click();
      
      toast({
        title: "✓ Export erfolgreich",
        description: `${allProducts.length} Produkte wurden exportiert.`,
      });
    } catch (e: any) {
      toast({
        title: "Fehler beim Export",
        description: e?.message || "Export konnte nicht durchgeführt werden.",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  // Admin not configured view
  if (!adminConfigured) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Card className="p-8 max-w-md text-center space-y-4 border-dashed">
          <AlertCircle className="w-12 h-12 mx-auto text-muted-foreground" />
          <div>
            <h3 className="font-semibold text-lg mb-2">Admin-Zugriff erforderlich</h3>
            <p className="text-sm text-muted-foreground">
              Setzen Sie <code className="bg-muted px-2 py-1 rounded">VITE_ADMIN_API_KEY</code> im Frontend 
              und <code className="bg-muted px-2 py-1 rounded">ADMIN_API_KEY</code> im Backend, 
              um die Produktverwaltung zu aktivieren.
            </p>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="space-y-2">
        <h2 className="text-2xl font-semibold tracking-tight">Produktverwaltung</h2>
        <p className="text-muted-foreground">
          Verwalten Sie Ihre Produktdatenbank, Synonyme und importieren Sie Daten per CSV.
        </p>
      </div>

      {/* Main Tabs */}
      <Tabs defaultValue="products" className="space-y-6">
        <TabsList className="grid w-full grid-cols-3 max-w-md">
          <TabsTrigger value="products" className="flex items-center gap-2">
            <Package className="w-4 h-4" />
            <span className="hidden sm:inline">Produkte</span>
          </TabsTrigger>
          <TabsTrigger value="synonyms" className="flex items-center gap-2">
            <Tag className="w-4 h-4" />
            <span className="hidden sm:inline">Synonyme</span>
          </TabsTrigger>
          <TabsTrigger value="import" className="flex items-center gap-2">
            <FileUp className="w-4 h-4" />
            <span className="hidden sm:inline">Import</span>
          </TabsTrigger>
        </TabsList>

        {/* Products Tab */}
        <TabsContent value="products" className="space-y-4">
          {/* Statistics */}
          <Card className="p-4">
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <div className="flex items-center gap-2">
                <Package className="w-4 h-4 text-muted-foreground" />
                <span className="text-muted-foreground">Gesamt:</span>
                <span className="font-semibold">{products.length} Produkte</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">Aktiv:</span>
                <span className="font-semibold text-green-600">
                  {products.filter(p => p.active).length}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">Inaktiv:</span>
                <span className="font-semibold text-muted-foreground">
                  {products.filter(p => !p.active).length}
                </span>
              </div>
              {searchQuery && (
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground">Gefiltert:</span>
                  <span className="font-semibold">{filteredProducts.length}</span>
                </div>
              )}
            </div>
          </Card>

          {/* Search & Actions */}
          <Card className="p-4">
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder="Produkte durchsuchen..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10"
                />
              </div>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 text-sm">
                  <Switch
                    id="show-inactive"
                    checked={showInactive}
                    onCheckedChange={setShowInactive}
                  />
                  <Label htmlFor="show-inactive" className="cursor-pointer">
                    Inaktive
                  </Label>
                </div>
                <Button
                  onClick={() => setCreateDialogOpen(true)}
                  className="gap-2"
                >
                  <Plus className="w-4 h-4" />
                  Neu
                </Button>
                <Button
                  variant="outline"
                  onClick={exportCsv}
                  disabled={products.length === 0}
                  className="gap-2"
                >
                  <Download className="w-4 h-4" />
                  <span className="hidden sm:inline">Export</span>
                </Button>
              </div>
            </div>
          </Card>

          {/* Products List */}
          {loading ? (
            <Card className="p-12 text-center">
              <div className="animate-spin w-8 h-8 border-4 border-primary border-t-transparent rounded-full mx-auto mb-4"></div>
              <p className="text-muted-foreground">Lädt Produkte...</p>
            </Card>
          ) : filteredProducts.length === 0 ? (
            <Card className="p-12 text-center border-dashed">
              <Package className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
              <h3 className="font-semibold mb-2">Keine Produkte gefunden</h3>
              <p className="text-sm text-muted-foreground mb-4">
                {searchQuery ? "Versuchen Sie einen anderen Suchbegriff." : "Fügen Sie Ihr erstes Produkt hinzu."}
              </p>
              {!searchQuery && (
                <Button onClick={() => setCreateDialogOpen(true)} variant="outline" className="gap-2">
                  <Plus className="w-4 h-4" />
                  Produkt hinzufügen
                </Button>
              )}
            </Card>
          ) : (
            <div className="grid gap-3">
              {filteredProducts.map((product) => (
                <Card
                  key={`${product.company_id}-${product.sku}`}
                  className={`p-4 transition-all hover:shadow-md ${
                    !product.active ? "opacity-50" : ""
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-semibold truncate">{product.name}</h3>
                        {!product.active && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                            Inaktiv
                          </span>
                        )}
                        {product.category && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                            {product.category}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 mb-2 text-sm text-muted-foreground">
                        <span>SKU: {product.sku}</span>
                        {product.price_eur && (
                          <span className="font-medium text-foreground">
                            {product.price_eur.toFixed(2)} €
                          </span>
                        )}
                        {product.volume_l && product.unit && (
                          <span>
                            {product.volume_l} {product.unit}
                          </span>
                        )}
                      </div>
                      {product.description && (
                        <p className="text-sm text-muted-foreground line-clamp-2">
                          {product.description}
                        </p>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setEditForm({ ...product, description: product.description ?? "" })}
                        className="gap-2"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleDelete(product.sku, product.name)}
                        disabled={!product.active || loading}
                        className="gap-2 text-destructive hover:text-destructive"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* Synonyms Tab */}
        <TabsContent value="synonyms" className="space-y-4">
          <Card className="p-6 space-y-4">
            <div>
              <h3 className="font-semibold mb-1">Neue Synonyme hinzufügen</h3>
              <p className="text-sm text-muted-foreground">
                Definieren Sie alternative Begriffe für besseres Matching.
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Hauptbegriff</Label>
                <Input
                  value={synForm.canon}
                  onChange={(e) => setSynForm((prev) => ({ ...prev, canon: e.target.value }))}
                  placeholder="z.B. Dispersionsfarbe"
                />
              </div>
              <div className="space-y-2">
                <Label>Synonyme (kommagetrennt)</Label>
                <Input
                  value={synForm.variants}
                  onChange={(e) => setSynForm((prev) => ({ ...prev, variants: e.target.value }))}
                  placeholder="z.B. Farbe, Wandfarbe, Innenfarbe"
                />
              </div>
            </div>
            <Button
              onClick={handleSynonymSubmit}
              disabled={!synForm.canon.trim() || !synForm.variants.trim() || loading}
              className="w-full sm:w-auto"
            >
              <Check className="w-4 h-4 mr-2" />
              Synonyme speichern
            </Button>
          </Card>

          {/* Existing Synonyms */}
          <Card className="p-6">
            <h3 className="font-semibold mb-4">Vorhandene Synonyme</h3>
            {Object.keys(synonyms).length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">
                Noch keine Synonyme definiert.
              </p>
            ) : (
              <div className="space-y-3">
                {Object.entries(synonyms).map(([canon, variants]) => (
                  <div key={canon} className="p-3 rounded-lg border border-border/60">
                    <p className="font-medium text-sm mb-1">{canon}</p>
                    <div className="flex flex-wrap gap-1.5">
                      {variants.map((variant, idx) => (
                        <span
                          key={idx}
                          className="text-xs px-2 py-1 rounded-full bg-primary/10 text-primary"
                        >
                          {variant}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </TabsContent>

        {/* Import Tab */}
        <TabsContent value="import" className="space-y-4">
          <Card className="p-6 space-y-4">
            <div>
              <h3 className="font-semibold mb-1">CSV Import</h3>
              <p className="text-sm text-muted-foreground">
                Format: SKU, Name, Beschreibung (eine Zeile pro Produkt)
              </p>
            </div>
            
            <div className="space-y-2">
              <Label>CSV-Daten</Label>
              <Textarea
                value={csvContent}
                onChange={(e) => setCsvContent(e.target.value)}
                placeholder="sku,name,description,unit,volume_l,price_eur,active,category,material_type,unit_package,tags&#10;P001,Dispersionsfarbe weiß matt 10L,Hochdeckende Innenfarbe,l,10,59.9,true,paint,dispersion_paint_white,Eimer,innen;weiß;wand&#10;P002,Tiefgrund 10L,Grundierung für saugende Untergründe,l,10,24.5,true,primer,primer_wall,Eimer,innen;grundierung"
                rows={12}
                className="font-mono text-sm"
              />
            </div>

            <div className="flex gap-3">
              <Button
                onClick={handleCsvImport}
                disabled={!csvContent.trim() || loading}
                className="gap-2"
              >
                <Upload className="w-4 h-4" />
                Importieren
              </Button>
              <Button
                variant="outline"
                onClick={() => setCsvContent("")}
                disabled={!csvContent.trim()}
                className="gap-2"
              >
                <X className="w-4 h-4" />
                Leeren
              </Button>
            </div>

            <div className="p-4 rounded-lg bg-muted/50 border border-border/60">
              <h4 className="font-medium text-sm mb-2">💡 Hinweise zum Import</h4>
              <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside">
                <li>Erste Zeile muss Header sein (sku,name,description,unit,volume_l,price_eur,...)</li>
                <li>SKU und Name sind Pflichtfelder, alle anderen optional</li>
                <li>Preis und Volumen als Zahlen (Punkt als Dezimaltrennzeichen)</li>
                <li>Tags mit Semikolon trennen (z.B. innen;weiß;wand)</li>
                <li>Bestehende Produkte (gleiche SKU) werden aktualisiert</li>
              </ul>
            </div>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Create Product Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Neues Produkt hinzufügen</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>SKU *</Label>
              <Input
                value={createForm.sku}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, sku: e.target.value }))}
                placeholder="z.B. P001"
              />
            </div>
            <div className="space-y-2">
              <Label>Produktname *</Label>
              <Input
                value={createForm.name}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, name: e.target.value }))}
                placeholder="z.B. Dispersionsfarbe weiß, matt, 10 L"
              />
            </div>
            <div className="space-y-2">
              <Label>Beschreibung</Label>
              <Textarea
                value={createForm.description}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, description: e.target.value }))}
                placeholder="Optionale Produktbeschreibung"
                rows={3}
              />
            </div>
            
            {/* Pricing & Units */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label>Preis (EUR)</Label>
                <Input
                  type="number"
                  step="0.01"
                  value={createForm.price_eur ?? ""}
                  onChange={(e) => setCreateForm((prev) => ({ ...prev, price_eur: e.target.value ? parseFloat(e.target.value) : null }))}
                  placeholder="z.B. 59.90"
                />
              </div>
              <div className="space-y-2">
                <Label>Einheit</Label>
                <Input
                  value={createForm.unit ?? ""}
                  onChange={(e) => setCreateForm((prev) => ({ ...prev, unit: e.target.value || null }))}
                  placeholder="z.B. l, kg, m, m², stk"
                />
              </div>
            </div>
            
            <div className="space-y-2">
              <Label>Volumen/Menge</Label>
              <Input
                type="number"
                step="0.01"
                value={createForm.volume_l ?? ""}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, volume_l: e.target.value ? parseFloat(e.target.value) : null }))}
                placeholder="z.B. 10 (für 10L)"
              />
            </div>
            
            {/* Classification */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label>Kategorie</Label>
                <Input
                  value={createForm.category ?? ""}
                  onChange={(e) => setCreateForm((prev) => ({ ...prev, category: e.target.value || null }))}
                  placeholder="z.B. paint, primer, tools"
                />
              </div>
              <div className="space-y-2">
                <Label>Material-Typ</Label>
                <Input
                  value={createForm.material_type ?? ""}
                  onChange={(e) => setCreateForm((prev) => ({ ...prev, material_type: e.target.value || null }))}
                  placeholder="z.B. dispersion_paint_white"
                />
              </div>
            </div>
            
            <div className="space-y-2">
              <Label>Verpackung</Label>
              <Input
                value={createForm.unit_package ?? ""}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, unit_package: e.target.value || null }))}
                placeholder="z.B. Eimer, Dose, Rolle, Stück"
              />
            </div>
            
            <div className="space-y-2">
              <Label>Tags (Semikolon-getrennt)</Label>
              <Input
                value={createForm.tags ?? ""}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, tags: e.target.value || null }))}
                placeholder="z.B. innen;weiß;wand;dispersionsfarbe"
              />
            </div>
            
            <div className="flex items-center justify-between">
              <Label htmlFor="create-active">Aktiv</Label>
              <Switch
                id="create-active"
                checked={createForm.active}
                onCheckedChange={(checked) => setCreateForm((prev) => ({ ...prev, active: checked }))}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setCreateDialogOpen(false);
                setCreateForm(emptyProduct);
              }}
            >
              Abbrechen
            </Button>
            <Button
              onClick={() => submitProduct(createForm, false)}
              disabled={!createForm.sku.trim() || !createForm.name.trim() || loading}
            >
              Speichern
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Product Dialog */}
      <Dialog open={!!editForm} onOpenChange={(open) => !open && setEditForm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Produkt bearbeiten</DialogTitle>
          </DialogHeader>
          {editForm && (
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label>SKU</Label>
                <Input value={editForm.sku} disabled className="bg-muted" />
              </div>
              <div className="space-y-2">
                <Label>Produktname *</Label>
                <Input
                  value={editForm.name}
                  onChange={(e) => setEditForm((prev) => prev ? ({ ...prev, name: e.target.value }) : null)}
                />
              </div>
              <div className="space-y-2">
                <Label>Beschreibung</Label>
                <Textarea
                  value={editForm.description || ""}
                  onChange={(e) => setEditForm((prev) => prev ? ({ ...prev, description: e.target.value }) : null)}
                  rows={3}
                />
              </div>
              
              {/* Pricing & Units */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label>Preis (EUR)</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={editForm.price_eur ?? ""}
                    onChange={(e) => setEditForm((prev) => prev ? ({ ...prev, price_eur: e.target.value ? parseFloat(e.target.value) : null }) : null)}
                    placeholder="z.B. 59.90"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Einheit</Label>
                  <Input
                    value={editForm.unit ?? ""}
                    onChange={(e) => setEditForm((prev) => prev ? ({ ...prev, unit: e.target.value || null }) : null)}
                    placeholder="z.B. l, kg, m, m², stk"
                  />
                </div>
              </div>
              
              <div className="space-y-2">
                <Label>Volumen/Menge</Label>
                <Input
                  type="number"
                  step="0.01"
                  value={editForm.volume_l ?? ""}
                  onChange={(e) => setEditForm((prev) => prev ? ({ ...prev, volume_l: e.target.value ? parseFloat(e.target.value) : null }) : null)}
                  placeholder="z.B. 10 (für 10L)"
                />
              </div>
              
              {/* Classification */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label>Kategorie</Label>
                  <Input
                    value={editForm.category ?? ""}
                    onChange={(e) => setEditForm((prev) => prev ? ({ ...prev, category: e.target.value || null }) : null)}
                    placeholder="z.B. paint, primer, tools"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Material-Typ</Label>
                  <Input
                    value={editForm.material_type ?? ""}
                    onChange={(e) => setEditForm((prev) => prev ? ({ ...prev, material_type: e.target.value || null }) : null)}
                    placeholder="z.B. dispersion_paint_white"
                  />
                </div>
              </div>
              
              <div className="space-y-2">
                <Label>Verpackung</Label>
                <Input
                  value={editForm.unit_package ?? ""}
                  onChange={(e) => setEditForm((prev) => prev ? ({ ...prev, unit_package: e.target.value || null }) : null)}
                  placeholder="z.B. Eimer, Dose, Rolle, Stück"
                />
              </div>
              
              <div className="space-y-2">
                <Label>Tags (Semikolon-getrennt)</Label>
                <Input
                  value={editForm.tags ?? ""}
                  onChange={(e) => setEditForm((prev) => prev ? ({ ...prev, tags: e.target.value || null }) : null)}
                  placeholder="z.B. innen;weiß;wand;dispersionsfarbe"
                />
              </div>
              
              <div className="flex items-center justify-between">
                <Label htmlFor="edit-active">Aktiv</Label>
                <Switch
                  id="edit-active"
                  checked={editForm.active}
                  onCheckedChange={(checked) => setEditForm((prev) => prev ? ({ ...prev, active: checked }) : null)}
                />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditForm(null)}>
              Abbrechen
            </Button>
            <Button
              onClick={() => editForm && submitProduct(editForm, true)}
              disabled={!editForm?.name.trim() || loading}
            >
              Aktualisieren
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default DatabaseManager;