import { useState, useRef, useEffect } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { Link } from "react-router-dom";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Switch } from "@/components/ui/switch";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  Calendar,
  Clock,
  Euro,
  TrendingUp,
  Users,
  Send,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  FileText,
  Plus,
  ChevronRight,
  Bot,
  GripVertical,
  Settings2,
  ChevronUp,
  ChevronDown,
  Eye,
  EyeOff,
  RotateCcw,
} from "lucide-react";

// Widget Definition
type WidgetId = "tasks" | "team" | "invoices" | "stats";

interface WidgetConfig {
  id: WidgetId;
  title: string;
  icon: typeof Clock;
  visible: boolean;
  order: number;
}

const defaultWidgetConfig: WidgetConfig[] = [
  { id: "stats", title: "Quick Stats", icon: TrendingUp, visible: true, order: 0 },
  { id: "tasks", title: "Anstehende Aufgaben", icon: Clock, visible: true, order: 1 },
  { id: "team", title: "Mitarbeiter Übersicht", icon: Users, visible: true, order: 2 },
  { id: "invoices", title: "Offene Forderungen", icon: Euro, visible: true, order: 3 },
];

// Demo data
const upcomingTasks = [
  { id: 1, title: "Malerei Wohnzimmer Familie Müller", date: "Heute, 14:00", status: "in_progress", priority: "high" },
  { id: 2, title: "Angebot Dachsanierung", date: "Heute, 16:30", status: "pending", priority: "medium" },
  { id: 3, title: "Fassadenanstrich Hauptstraße 12", date: "Morgen, 08:00", status: "pending", priority: "low" },
  { id: 4, title: "Rechnung Projekt Schulze abschließen", date: "Morgen, 10:00", status: "pending", priority: "high" },
];

const teamMembers = [
  { id: 1, name: "Max Mustermann", role: "Malermeister", status: "active", project: "Müller" },
  { id: 2, name: "Anna Schmidt", role: "Geselle", status: "active", project: "Fassade" },
  { id: 3, name: "Tom Weber", role: "Azubi", status: "break", project: "-" },
  { id: 4, name: "Lisa Bauer", role: "Geselle", status: "off", project: "-" },
];

const openInvoices = [
  { id: 1, customer: "Bau GmbH", amount: 4250.0, dueDate: "28.11.2024", status: "overdue" },
  { id: 2, customer: "Familie Weber", amount: 1890.5, dueDate: "05.12.2024", status: "pending" },
  { id: 3, customer: "Praxis Dr. Hoffmann", amount: 3120.0, dueDate: "10.12.2024", status: "pending" },
];

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
};

const STORAGE_KEY = "kalkulai_dashboard_widgets";

export default function Dashboard() {
  const { user } = useAuth();
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content: `Hallo ${user?.name?.split(" ")[0] || ""}! 👋 Ich bin dein KalkulAI Assistent. Ich kenne dein gesamtes System – frag mich zu Angeboten, Terminen, Finanzen oder was auch immer du wissen möchtest.`,
      timestamp: new Date(),
    },
  ]);
  const [isTyping, setIsTyping] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Widget configuration state
  const [widgets, setWidgets] = useState<WidgetConfig[]>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch {
        return defaultWidgetConfig;
      }
    }
    return defaultWidgetConfig;
  });

  // Save to localStorage when widgets change
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(widgets));
  }, [widgets]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  const handleSendMessage = async () => {
    if (!chatInput.trim() || isTyping) return;

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: chatInput,
      timestamp: new Date(),
    };

    setChatMessages((prev) => [...prev, userMessage]);
    setChatInput("");
    setIsTyping(true);

    setTimeout(() => {
      const responses = [
        "Ich schaue mir das gleich für dich an! Basierend auf deinen aktuellen Projekten...",
        "Gute Frage! Lass mich kurz in deinen Daten nachschauen...",
        "Das kann ich dir schnell sagen. Einen Moment...",
      ];
      const assistantMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: responses[Math.floor(Math.random() * responses.length)] + "\n\n*Diese Funktion wird bald vollständig integriert.*",
        timestamp: new Date(),
      };
      setChatMessages((prev) => [...prev, assistantMessage]);
      setIsTyping(false);
    }, 1500);
  };

  const toggleWidget = (id: WidgetId) => {
    setWidgets((prev) =>
      prev.map((w) => (w.id === id ? { ...w, visible: !w.visible } : w))
    );
  };

  const moveWidget = (id: WidgetId, direction: "up" | "down") => {
    setWidgets((prev) => {
      const sorted = [...prev].sort((a, b) => a.order - b.order);
      const index = sorted.findIndex((w) => w.id === id);
      if (
        (direction === "up" && index === 0) ||
        (direction === "down" && index === sorted.length - 1)
      ) {
        return prev;
      }
      const swapIndex = direction === "up" ? index - 1 : index + 1;
      const newOrder = sorted[swapIndex].order;
      sorted[swapIndex].order = sorted[index].order;
      sorted[index].order = newOrder;
      return sorted;
    });
  };

  const resetWidgets = () => {
    setWidgets(defaultWidgetConfig);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "active":
        return "bg-emerald-100 text-emerald-700 border-emerald-200";
      case "break":
        return "bg-amber-100 text-amber-700 border-amber-200";
      case "off":
        return "bg-slate-100 text-slate-500 border-slate-200";
      default:
        return "bg-slate-100 text-slate-600 border-slate-200";
    }
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case "high":
        return "bg-rose-500";
      case "medium":
        return "bg-amber-500";
      case "low":
        return "bg-emerald-500";
      default:
        return "bg-slate-400";
    }
  };

  const totalOpen = openInvoices.reduce((sum, inv) => sum + inv.amount, 0);
  const sortedWidgets = [...widgets].sort((a, b) => a.order - b.order);

  // Widget Components
  const StatsWidget = () => (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <Card className="p-4 bg-gradient-to-br from-primary/5 to-primary/10 border-primary/20">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-primary/10">
            <FileText className="w-5 h-5 text-primary" />
          </div>
          <div>
            <p className="text-2xl font-bold text-slate-900">12</p>
            <p className="text-sm text-slate-500">Offene Angebote</p>
          </div>
        </div>
      </Card>
      <Card className="p-4 bg-gradient-to-br from-emerald-50 to-emerald-100/50 border-emerald-200/50">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-emerald-100">
            <TrendingUp className="w-5 h-5 text-emerald-600" />
          </div>
          <div>
            <p className="text-2xl font-bold text-slate-900">€24.5k</p>
            <p className="text-sm text-slate-500">Umsatz November</p>
          </div>
        </div>
      </Card>
      <Card className="p-4 bg-gradient-to-br from-amber-50 to-amber-100/50 border-amber-200/50">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-amber-100">
            <Calendar className="w-5 h-5 text-amber-600" />
          </div>
          <div>
            <p className="text-2xl font-bold text-slate-900">8</p>
            <p className="text-sm text-slate-500">Projekte aktiv</p>
          </div>
        </div>
      </Card>
      <Card className="p-4 bg-gradient-to-br from-violet-50 to-violet-100/50 border-violet-200/50">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-violet-100">
            <Users className="w-5 h-5 text-violet-600" />
          </div>
          <div>
            <p className="text-2xl font-bold text-slate-900">4</p>
            <p className="text-sm text-slate-500">Team Mitglieder</p>
          </div>
        </div>
      </Card>
    </div>
  );

  const TasksWidget = () => (
    <Card className="overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between bg-gradient-to-r from-slate-50 to-transparent">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10">
            <Clock className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h2 className="font-semibold text-slate-900">Anstehende Aufgaben</h2>
            <p className="text-sm text-slate-500">Deine nächsten To-Dos</p>
          </div>
        </div>
        <Link to="/plantafel">
          <Button variant="ghost" size="sm" className="gap-1.5 text-slate-600 hover:text-primary">
            Zur Plantafel
            <ChevronRight className="w-4 h-4" />
          </Button>
        </Link>
      </div>
      <div className="divide-y divide-slate-100">
        {upcomingTasks.map((task) => (
          <div
            key={task.id}
            className="px-5 py-3.5 flex items-center gap-4 hover:bg-slate-50/50 transition-colors group"
          >
            <div className={`w-1.5 h-10 rounded-full ${getPriorityColor(task.priority)}`} />
            <div className="flex-1 min-w-0">
              <p className="font-medium text-slate-800 truncate group-hover:text-primary transition-colors">
                {task.title}
              </p>
              <div className="flex items-center gap-2 mt-0.5">
                <Clock className="w-3.5 h-3.5 text-slate-400" />
                <span className="text-sm text-slate-500">{task.date}</span>
              </div>
            </div>
            <Badge
              variant="outline"
              className={`${
                task.status === "in_progress"
                  ? "bg-blue-50 text-blue-700 border-blue-200"
                  : "bg-slate-50 text-slate-600 border-slate-200"
              }`}
            >
              {task.status === "in_progress" ? "In Arbeit" : "Ausstehend"}
            </Badge>
          </div>
        ))}
      </div>
    </Card>
  );

  const TeamWidget = () => (
    <Card className="overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between bg-gradient-to-r from-slate-50 to-transparent">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-violet-100">
            <Users className="w-4 h-4 text-violet-600" />
          </div>
          <div>
            <h2 className="font-semibold text-slate-900">Mitarbeiter Übersicht</h2>
            <p className="text-sm text-slate-500">Wer arbeitet gerade woran</p>
          </div>
        </div>
      </div>
      <div className="p-4">
        <div className="grid sm:grid-cols-2 gap-3">
          {teamMembers.map((member) => (
            <div
              key={member.id}
              className="flex items-center gap-3 p-3 rounded-xl bg-slate-50/50 hover:bg-slate-100/50 transition-colors"
            >
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-slate-200 to-slate-300 flex items-center justify-center">
                <span className="text-sm font-semibold text-slate-600">
                  {member.name.split(" ").map((n) => n[0]).join("")}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-medium text-slate-800 truncate">{member.name}</p>
                <p className="text-sm text-slate-500 truncate">{member.role}</p>
              </div>
              <div className="text-right">
                <Badge variant="outline" className={getStatusColor(member.status)}>
                  {member.status === "active" ? "Aktiv" : member.status === "break" ? "Pause" : "Frei"}
                </Badge>
                {member.project !== "-" && (
                  <p className="text-xs text-slate-400 mt-1">{member.project}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );

  const InvoicesWidget = () => (
    <Card className="overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between bg-gradient-to-r from-slate-50 to-transparent">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-emerald-100">
            <Euro className="w-4 h-4 text-emerald-600" />
          </div>
          <div>
            <h2 className="font-semibold text-slate-900">Offene Forderungen</h2>
            <p className="text-sm text-slate-500">
              Gesamt: <span className="font-semibold text-emerald-600">{totalOpen.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}</span>
            </p>
          </div>
        </div>
      </div>
      <div className="divide-y divide-slate-100">
        {openInvoices.map((invoice) => (
          <div
            key={invoice.id}
            className="px-5 py-3.5 flex items-center justify-between hover:bg-slate-50/50 transition-colors"
          >
            <div className="flex items-center gap-3">
              {invoice.status === "overdue" ? (
                <AlertCircle className="w-5 h-5 text-rose-500" />
              ) : (
                <CheckCircle2 className="w-5 h-5 text-slate-300" />
              )}
              <div>
                <p className="font-medium text-slate-800">{invoice.customer}</p>
                <p className="text-sm text-slate-500">Fällig: {invoice.dueDate}</p>
              </div>
            </div>
            <div className="text-right">
              <p className="font-semibold text-slate-900">
                {invoice.amount.toLocaleString("de-DE", { style: "currency", currency: "EUR" })}
              </p>
              <Badge
                variant="outline"
                className={`${
                  invoice.status === "overdue"
                    ? "bg-rose-50 text-rose-700 border-rose-200"
                    : "bg-amber-50 text-amber-700 border-amber-200"
                }`}
              >
                {invoice.status === "overdue" ? "Überfällig" : "Offen"}
              </Badge>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );

  const renderWidget = (widgetId: WidgetId) => {
    switch (widgetId) {
      case "stats":
        return <StatsWidget />;
      case "tasks":
        return <TasksWidget />;
      case "team":
        return <TeamWidget />;
      case "invoices":
        return <InvoicesWidget />;
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Header Section */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Guten {new Date().getHours() < 12 ? "Morgen" : new Date().getHours() < 18 ? "Tag" : "Abend"}, {user?.name?.split(" ")[0] || ""}!
          </h1>
          <p className="text-slate-500 mt-1">
            Hier ist dein Überblick für {new Date().toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long" })}
          </p>
        </div>
        <div className="flex gap-3">
          {/* Widget Configuration Sheet */}
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="outline" className="gap-2">
                <Settings2 className="w-4 h-4" />
                Anpassen
              </Button>
            </SheetTrigger>
            <SheetContent>
              <SheetHeader>
                <SheetTitle>Dashboard anpassen</SheetTitle>
                <SheetDescription>
                  Wähle aus welche Widgets angezeigt werden sollen und passe die Reihenfolge an.
                </SheetDescription>
              </SheetHeader>
              <div className="mt-6 space-y-4">
                <div className="flex justify-end">
                  <Button variant="ghost" size="sm" onClick={resetWidgets} className="gap-2 text-slate-500">
                    <RotateCcw className="w-4 h-4" />
                    Zurücksetzen
                  </Button>
                </div>
                <div className="space-y-2">
                  {sortedWidgets.map((widget, index) => {
                    const Icon = widget.icon;
                    return (
                      <div
                        key={widget.id}
                        className={`flex items-center gap-3 p-3 rounded-lg border transition-colors ${
                          widget.visible
                            ? "bg-white border-slate-200"
                            : "bg-slate-50 border-slate-100 opacity-60"
                        }`}
                      >
                        <GripVertical className="w-4 h-4 text-slate-400" />
                        <div className="p-2 rounded-lg bg-slate-100">
                          <Icon className="w-4 h-4 text-slate-600" />
                        </div>
                        <span className="flex-1 font-medium text-slate-700">{widget.title}</span>
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => moveWidget(widget.id, "up")}
                            disabled={index === 0}
                          >
                            <ChevronUp className="w-4 h-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => moveWidget(widget.id, "down")}
                            disabled={index === sortedWidgets.length - 1}
                          >
                            <ChevronDown className="w-4 h-4" />
                          </Button>
                        </div>
                        <Switch
                          checked={widget.visible}
                          onCheckedChange={() => toggleWidget(widget.id)}
                        />
                      </div>
                    );
                  })}
                </div>
                <p className="text-xs text-slate-500 mt-4">
                  Deine Einstellungen werden automatisch gespeichert.
                </p>
              </div>
            </SheetContent>
          </Sheet>

          <Link to="/angebote">
            <Button className="gap-2 shadow-lg shadow-primary/20 hover:shadow-xl hover:shadow-primary/30 transition-all">
              <Plus className="w-4 h-4" />
              Neues Angebot
            </Button>
          </Link>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid lg:grid-cols-3 gap-6">
        {/* Left Column - Dynamic Widgets */}
        <div className="lg:col-span-2 space-y-6">
          {sortedWidgets
            .filter((w) => w.visible)
            .map((widget) => (
              <div key={widget.id}>{renderWidget(widget.id)}</div>
            ))}
          
          {sortedWidgets.filter((w) => w.visible).length === 0 && (
            <Card className="p-12 flex flex-col items-center justify-center text-center">
              <EyeOff className="w-12 h-12 text-slate-300 mb-4" />
              <h3 className="font-semibold text-slate-700 mb-2">Keine Widgets aktiviert</h3>
              <p className="text-sm text-slate-500 mb-4">
                Klicke auf "Anpassen" um Widgets einzublenden.
              </p>
            </Card>
          )}
        </div>

        {/* Right Column - AI Chat */}
        <div className="lg:col-span-1">
          <Card className="h-[calc(100vh-280px)] min-h-[500px] flex flex-col overflow-hidden bg-gradient-to-b from-white to-slate-50/30">
            {/* Chat Header */}
            <div className="px-5 py-4 border-b border-slate-100 bg-gradient-to-r from-primary/5 to-violet-50/50">
              <div className="flex items-center gap-3">
                <div className="relative">
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-violet-600 flex items-center justify-center shadow-lg shadow-primary/20">
                    <Bot className="w-5 h-5 text-white" />
                  </div>
                  <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-emerald-500 rounded-full border-2 border-white" />
                </div>
                <div>
                  <h2 className="font-semibold text-slate-900 flex items-center gap-2">
                    KalkulAI Assistent
                    <Sparkles className="w-4 h-4 text-amber-500" />
                  </h2>
                  <p className="text-sm text-slate-500">Dein intelligenter Helfer</p>
                </div>
              </div>
            </div>

            {/* Chat Messages */}
            <ScrollArea className="flex-1 p-4">
              <div className="space-y-4">
                {chatMessages.map((message) => (
                  <div
                    key={message.id}
                    className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[85%] px-4 py-3 rounded-2xl ${
                        message.role === "user"
                          ? "bg-primary text-white rounded-br-md"
                          : "bg-white border border-slate-200 shadow-sm rounded-bl-md"
                      }`}
                    >
                      <p className={`text-sm leading-relaxed ${message.role === "user" ? "text-white" : "text-slate-700"}`}>
                        {message.content}
                      </p>
                      <p className={`text-xs mt-1.5 ${message.role === "user" ? "text-white/60" : "text-slate-400"}`}>
                        {message.timestamp.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}
                      </p>
                    </div>
                  </div>
                ))}
                {isTyping && (
                  <div className="flex justify-start">
                    <div className="bg-white border border-slate-200 shadow-sm rounded-2xl rounded-bl-md px-4 py-3">
                      <div className="flex gap-1.5">
                        <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                        <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                        <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                      </div>
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
            </ScrollArea>

            {/* Quick Actions */}
            <div className="px-4 py-2 border-t border-slate-100 bg-white/50">
              <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
                {["Offene Angebote?", "Wer arbeitet heute?", "Umsatz diese Woche?"].map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => setChatInput(suggestion)}
                    className="flex-shrink-0 px-3 py-1.5 text-xs font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-full transition-colors"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>

            {/* Chat Input */}
            <div className="p-4 border-t border-slate-100 bg-white">
              <div className="flex gap-2">
                <Input
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSendMessage();
                    }
                  }}
                  placeholder="Frag mich etwas..."
                  className="flex-1 bg-slate-50 border-slate-200 focus:bg-white transition-colors"
                />
                <Button
                  onClick={handleSendMessage}
                  disabled={!chatInput.trim() || isTyping}
                  size="icon"
                  className="shrink-0 shadow-lg shadow-primary/20"
                >
                  <Send className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
