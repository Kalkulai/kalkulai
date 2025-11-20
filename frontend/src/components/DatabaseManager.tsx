import { useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/use-toast";
import { api, type AdminProduct, type SynonymMap } from "@/lib/api";

const emptyProduct = { sku: "", name: "", description: "", active: true };

const DatabaseManager = () => {
  const [companyId, setCompanyId] = useState("demo");
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [products, setProducts] = useState<AdminProduct[]>([]);
  const [synonyms, setSynonyms] = useState<SynonymMap>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createForm, setCreateForm] = useState(emptyProduct);
  const [editForm, setEditForm] = useState<AdminProduct | null>(null);
  const [synForm, setSynForm] = useState({ canon: "", variants: "" });
  const { toast } = useToast();

  const adminConfigured = Boolean(import.meta.env.VITE_ADMIN_API_KEY);

  const loadData = async () => {
    if (!companyId) return;
    try {
      setLoading(true);
      setError(null);
      const [prod, syn] = await Promise.all([
        api.admin.listProducts(companyId, includeDeleted),
        api.admin.listSynonyms(companyId),
      ]);
      setProducts(prod);
      setSynonyms(syn);
    } catch (e: any) {
      const msg = e?.message || "Unbekannter Fehler beim Laden.";
      setError(msg);
      toast({ title: "Fehler beim Laden", description: msg, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const submitProduct = async (payload: { sku: string; name: string; description?: string; active?: boolean }, isEdit = false) => {
    if (!companyId) return;
    try {
      setLoading(true);
      await api.admin.upsertProduct(companyId, payload);
      await loadData();
      toast({
        title: isEdit ? "Produkt aktualisiert" : "Produkt angelegt",
        description: `${payload.name} (${payload.sku}) wurde gespeichert.`,
      });
    } catch (e: any) {
      toast({
        title: "Fehler beim Speichern",
        description: e?.message || "Unbekannter Fehler.",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (sku: string) => {
    if (!companyId) return;
    try {
      setLoading(true);
      await api.admin.deleteProduct(companyId, sku);
      await loadData();
      toast({ title: "Produkt deaktiviert", description: `${sku} wurde deaktiviert.` });
    } catch (e: any) {
      toast({
        title: "Fehler beim Löschen",
        description: e?.message || "Unbekannter Fehler.",
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
    if (!variants.length) return;
    try {
      setLoading(true);
      await api.admin.addSynonyms(companyId, synForm.canon, variants);
      await loadData();
      setSynForm({ canon: "", variants: "" });
      toast({ title: "Synonyme gespeichert", description: "Die Einträge wurden übernommen." });
    } catch (e: any) {
      toast({
        title: "Fehler bei Synonymen",
        description: e?.message || "Unbekannter Fehler.",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const productList = products.length ? (
    <div className="space-y-3 max-h-[320px] overflow-y-auto pr-1">
      {products.map((product) => (
        <div
          key={`${product.company_id}-${product.sku}`}
          className="flex items-start justify-between rounded-lg border border-border/60 p-3"
        >
          <div>
            <p className="font-semibold text-sm md:text-base">
              {product.name} <span className="text-muted-foreground font-normal">({product.sku})</span>
            </p>
            {product.description && <p className="text-sm text-muted-foreground mt-1">{product.description}</p>}
            <p className="text-xs mt-2 text-muted-foreground">
              Status: {product.active ? "aktiv" : "inaktiv"} · Aktualisiert: {product.updated_at ?? "—"}
            </p>
          </div>
          <div className="flex flex-col gap-2">
            <Button
              size="sm"
              variant="secondary"
              onClick={() =>
                setEditForm({
                  ...product,
                  description: product.description ?? "",
                })
              }
            >
              Bearbeiten
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleDelete(product.sku)}
              disabled={!product.active || loading}
            >
              Deaktivieren
            </Button>
          </div>
        </div>
      ))}
    </div>
  ) : (
    <p className="text-sm text-muted-foreground">Noch keine Produkte geladen.</p>
  );

  if (!adminConfigured) {
    return (
      <Card className="p-4 bg-muted/40 border-dashed">
        <p className="font-medium mb-1">Admin-API-Schlüssel fehlt</p>
        <p className="text-sm text-muted-foreground">
          Setze <code>VITE_ADMIN_API_KEY</code> im Frontend und <code>ADMIN_API_KEY</code> im Backend, um die Datenbankverwaltung
          zu aktivieren.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="p-4 space-y-4">
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-[200px]">
            <Label htmlFor="company">Company ID</Label>
            <Input id="company" value={companyId} onChange={(e) => setCompanyId(e.target.value)} placeholder="z. B. demo" />
          </div>
          <div className="flex items-center gap-2">
            <Switch id="include-deleted" checked={includeDeleted} onCheckedChange={setIncludeDeleted} />
            <Label htmlFor="include-deleted">Inaktive anzeigen</Label>
          </div>
          <Button onClick={loadData} disabled={!companyId || loading}>
            {loading ? "Lädt…" : "Daten laden"}
          </Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-4 space-y-4">
          <div>
            <h3 className="font-semibold text-lg">Produkte</h3>
            <p className="text-sm text-muted-foreground">Bestehende Einträge prüfen, bearbeiten oder deaktivieren.</p>
          </div>
          {productList}
        </Card>

        <Card className="p-4 space-y-4">
          <div>
            <h3 className="font-semibold text-lg">Neues Produkt hinzufügen</h3>
            <p className="text-sm text-muted-foreground">Pflichtfelder: SKU und Name.</p>
          </div>
          <div className="space-y-3">
            <div>
              <Label>SKU</Label>
              <Input
                value={createForm.sku}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, sku: e.target.value }))}
                placeholder="SKU-123"
              />
            </div>
            <div>
              <Label>Name</Label>
              <Input
                value={createForm.name}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, name: e.target.value }))}
                placeholder="Produktname"
              />
            </div>
            <div>
              <Label>Beschreibung</Label>
              <Textarea
                value={createForm.description}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, description: e.target.value }))}
                placeholder="Optionale Beschreibung"
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
            <Button
              onClick={() => {
                if (!createForm.sku.trim() || !createForm.name.trim()) return;
                submitProduct(createForm, false);
                setCreateForm(emptyProduct);
              }}
              disabled={!createForm.sku.trim() || !createForm.name.trim() || loading}
            >
              Speichern
            </Button>
          </div>
        </Card>
      </div>

      <Card className="p-4 space-y-4">
        <div>
          <h3 className="font-semibold text-lg">Synonyme verwalten</h3>
          <p className="text-sm text-muted-foreground">Füge kanonische Begriffe mit Varianten hinzu.</p>
        </div>
        <div className="space-y-3">
          <div>
            <Label>Kanoneintrag</Label>
            <Input value={synForm.canon} onChange={(e) => setSynForm((prev) => ({ ...prev, canon: e.target.value }))} />
          </div>
          <div>
            <Label>Varianten (durch Komma getrennt)</Label>
            <Textarea
              rows={2}
              value={synForm.variants}
              onChange={(e) => setSynForm((prev) => ({ ...prev, variants: e.target.value }))}
              placeholder="z. B. Haftgrundierung, Grundierung tief"
            />
          </div>
          <Button onClick={handleSynonymSubmit} disabled={!synForm.canon.trim() || !synForm.variants.trim() || loading}>
            Synonyme speichern
          </Button>
        </div>
        <div className="space-y-2 max-h-[240px] overflow-y-auto pr-1">
          {Object.keys(synonyms).length === 0 && (
            <p className="text-sm text-muted-foreground">Noch keine Synonyme geladen.</p>
          )}
          {Object.entries(synonyms).map(([canon, variants]) => (
            <div key={canon} className="rounded border border-border/60 p-3">
              <p className="font-semibold text-sm">{canon}</p>
              <p className="text-sm text-muted-foreground">{variants.join(", ")}</p>
            </div>
          ))}
        </div>
      </Card>

      <Dialog open={Boolean(editForm)} onOpenChange={(open) => !open && setEditForm(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Produkt bearbeiten</DialogTitle>
          </DialogHeader>
          {editForm && (
            <div className="space-y-3">
              <div>
                <Label>SKU</Label>
                <Input value={editForm.sku} disabled />
              </div>
              <div>
                <Label>Name</Label>
                <Input
                  value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                />
              </div>
              <div>
                <Label>Beschreibung</Label>
                <Textarea
                  value={editForm.description ?? ""}
                  onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                />
              </div>
              <div className="flex items-center justify-between">
                <Label htmlFor="edit-active">Aktiv</Label>
                <Switch
                  id="edit-active"
                  checked={editForm.active}
                  onCheckedChange={(checked) => setEditForm({ ...editForm, active: checked })}
                />
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setEditForm(null)}>
                  Abbrechen
                </Button>
                <Button
                  onClick={() => {
                    submitProduct(
                      {
                        sku: editForm.sku,
                        name: editForm.name,
                        description: editForm.description ?? "",
                        active: editForm.active,
                      },
                      true,
                    );
                    setEditForm(null);
                  }}
                  disabled={!editForm.name.trim() || loading}
                >
                  Änderungen speichern
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default DatabaseManager;
