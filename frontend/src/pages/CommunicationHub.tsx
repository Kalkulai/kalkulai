import { useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  MessageCircle,
  Mail,
  Phone,
  Send,
  Search,
  Plus,
  Star,
  Paperclip,
  MoreVertical,
  CheckCheck,
  Clock,
  User,
  Building,
  Filter,
  Bot,
  Sparkles,
  Zap,
} from "lucide-react";

// Demo Konversationen
const conversations = [
  {
    id: 1,
    name: "Familie Müller",
    type: "customer",
    lastMessage: "Vielen Dank für das Angebot! Wann können Sie anfangen?",
    timestamp: "vor 2 Std.",
    unread: 2,
    avatar: "FM",
    status: "active",
  },
  {
    id: 2,
    name: "Bau GmbH",
    type: "business",
    lastMessage: "Die Rechnung ist eingegangen, Zahlung erfolgt diese Woche.",
    timestamp: "vor 5 Std.",
    unread: 0,
    avatar: "BG",
    status: "active",
  },
  {
    id: 3,
    name: "Dr. Hoffmann Praxis",
    type: "customer",
    lastMessage: "Können Sie morgen vorbeikommen für eine Besichtigung?",
    timestamp: "Gestern",
    unread: 1,
    avatar: "DH",
    status: "pending",
  },
  {
    id: 4,
    name: "Großhandel Meyer",
    type: "supplier",
    lastMessage: "Ihre Bestellung ist versandbereit. LKW kommt Freitag.",
    timestamp: "Gestern",
    unread: 0,
    avatar: "GM",
    status: "active",
  },
  {
    id: 5,
    name: "Hotel Sonne",
    type: "business",
    lastMessage: "Wir benötigen ein Angebot für die Renovierung der Lobby.",
    timestamp: "vor 2 Tagen",
    unread: 0,
    avatar: "HS",
    status: "new",
  },
];

const messages = [
  {
    id: 1,
    sender: "Familie Müller",
    content: "Guten Tag! Wir haben Ihr Angebot für die Malerarbeiten erhalten.",
    timestamp: "10:30",
    isOwn: false,
  },
  {
    id: 2,
    sender: "Sie",
    content: "Freut mich! Haben Sie noch Fragen dazu?",
    timestamp: "10:45",
    isOwn: true,
    read: true,
  },
  {
    id: 3,
    sender: "Familie Müller",
    content: "Ja, könnten Sie den Farbton 'Alpinweiß Plus' anstatt des Standard-Weiß verwenden?",
    timestamp: "11:00",
    isOwn: false,
  },
  {
    id: 4,
    sender: "Sie",
    content: "Selbstverständlich! Das ist sogar unsere Empfehlung für langanhaltende Qualität. Der Aufpreis beträgt ca. 15% für das Material.",
    timestamp: "11:15",
    isOwn: true,
    read: true,
  },
  {
    id: 5,
    sender: "Familie Müller",
    content: "Vielen Dank für das Angebot! Wann können Sie anfangen?",
    timestamp: "14:20",
    isOwn: false,
  },
];

const aiSuggestions = [
  "Termin für nächste Woche vorschlagen",
  "Aktualisiertes Angebot senden",
  "Nach Präferenzen für Materialien fragen",
];

export default function CommunicationHub() {
  const [selectedConversation, setSelectedConversation] = useState(conversations[0]);
  const [messageInput, setMessageInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  const getTypeColor = (type: string) => {
    switch (type) {
      case "customer":
        return "bg-blue-100 text-blue-700";
      case "business":
        return "bg-emerald-100 text-emerald-700";
      case "supplier":
        return "bg-violet-100 text-violet-700";
      default:
        return "bg-slate-100 text-slate-700";
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case "customer":
        return <User className="w-3 h-3" />;
      case "business":
        return <Building className="w-3 h-3" />;
      case "supplier":
        return <Building className="w-3 h-3" />;
      default:
        return <User className="w-3 h-3" />;
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Communication Hub</h1>
          <p className="text-slate-500 mt-1">Alle Nachrichten an einem Ort</p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" className="gap-2">
            <Filter className="w-4 h-4" />
            Filter
          </Button>
          <Button className="gap-2 shadow-lg shadow-primary/20">
            <Plus className="w-4 h-4" />
            Neue Nachricht
          </Button>
        </div>
      </div>

      {/* Main Layout */}
      <div className="grid lg:grid-cols-3 gap-6 h-[calc(100vh-220px)] min-h-[600px]">
        {/* Conversation List */}
        <Card className="lg:col-span-1 flex flex-col overflow-hidden">
          <div className="p-4 border-b border-slate-100">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Konversationen durchsuchen..."
                className="pl-10 bg-slate-50 border-slate-200"
              />
            </div>
          </div>

          <Tabs defaultValue="all" className="flex-1 flex flex-col">
            <div className="px-4 border-b border-slate-100">
              <TabsList className="w-full grid grid-cols-3 h-10">
                <TabsTrigger value="all" className="text-xs">Alle</TabsTrigger>
                <TabsTrigger value="unread" className="text-xs">Ungelesen</TabsTrigger>
                <TabsTrigger value="starred" className="text-xs">Markiert</TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="all" className="flex-1 m-0">
              <ScrollArea className="h-full">
                <div className="divide-y divide-slate-100">
                  {conversations.map((conv) => (
                    <button
                      key={conv.id}
                      onClick={() => setSelectedConversation(conv)}
                      className={`w-full p-4 text-left hover:bg-slate-50 transition-colors ${
                        selectedConversation.id === conv.id ? "bg-primary/5 border-l-2 border-l-primary" : ""
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div className="relative">
                          <div className="w-11 h-11 rounded-full bg-gradient-to-br from-slate-200 to-slate-300 flex items-center justify-center">
                            <span className="text-sm font-semibold text-slate-600">{conv.avatar}</span>
                          </div>
                          {conv.unread > 0 && (
                            <span className="absolute -top-1 -right-1 w-5 h-5 bg-primary text-white text-xs font-bold rounded-full flex items-center justify-center">
                              {conv.unread}
                            </span>
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <span className={`font-semibold truncate ${conv.unread > 0 ? "text-slate-900" : "text-slate-700"}`}>
                              {conv.name}
                            </span>
                            <span className="text-xs text-slate-400 flex-shrink-0">{conv.timestamp}</span>
                          </div>
                          <div className="flex items-center gap-2 mt-0.5">
                            <Badge variant="outline" className={`${getTypeColor(conv.type)} border-0 text-xs py-0`}>
                              {getTypeIcon(conv.type)}
                              <span className="ml-1">
                                {conv.type === "customer" ? "Kunde" : conv.type === "business" ? "Geschäft" : "Lieferant"}
                              </span>
                            </Badge>
                          </div>
                          <p className={`text-sm truncate mt-1 ${conv.unread > 0 ? "text-slate-700 font-medium" : "text-slate-500"}`}>
                            {conv.lastMessage}
                          </p>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </ScrollArea>
            </TabsContent>

            <TabsContent value="unread" className="flex-1 m-0">
              <ScrollArea className="h-full">
                <div className="divide-y divide-slate-100">
                  {conversations.filter((c) => c.unread > 0).map((conv) => (
                    <button
                      key={conv.id}
                      onClick={() => setSelectedConversation(conv)}
                      className="w-full p-4 text-left hover:bg-slate-50 transition-colors"
                    >
                      <div className="flex items-start gap-3">
                        <div className="relative">
                          <div className="w-11 h-11 rounded-full bg-gradient-to-br from-slate-200 to-slate-300 flex items-center justify-center">
                            <span className="text-sm font-semibold text-slate-600">{conv.avatar}</span>
                          </div>
                          <span className="absolute -top-1 -right-1 w-5 h-5 bg-primary text-white text-xs font-bold rounded-full flex items-center justify-center">
                            {conv.unread}
                          </span>
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-semibold text-slate-900 truncate">{conv.name}</span>
                            <span className="text-xs text-slate-400 flex-shrink-0">{conv.timestamp}</span>
                          </div>
                          <p className="text-sm text-slate-700 font-medium truncate mt-1">
                            {conv.lastMessage}
                          </p>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </ScrollArea>
            </TabsContent>

            <TabsContent value="starred" className="flex-1 m-0">
              <div className="flex items-center justify-center h-full text-slate-400">
                <div className="text-center">
                  <Star className="w-12 h-12 mx-auto mb-3 text-slate-300" />
                  <p>Keine markierten Konversationen</p>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </Card>

        {/* Chat Area */}
        <Card className="lg:col-span-2 flex flex-col overflow-hidden">
          {/* Chat Header */}
          <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between bg-gradient-to-r from-slate-50 to-transparent">
            <div className="flex items-center gap-3">
              <div className="w-11 h-11 rounded-full bg-gradient-to-br from-slate-200 to-slate-300 flex items-center justify-center">
                <span className="text-sm font-semibold text-slate-600">{selectedConversation.avatar}</span>
              </div>
              <div>
                <h2 className="font-semibold text-slate-900">{selectedConversation.name}</h2>
                <div className="flex items-center gap-2 text-sm text-slate-500">
                  <Badge variant="outline" className={`${getTypeColor(selectedConversation.type)} border-0 text-xs py-0`}>
                    {selectedConversation.type === "customer" ? "Kunde" : selectedConversation.type === "business" ? "Geschäft" : "Lieferant"}
                  </Badge>
                  <span>•</span>
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 bg-emerald-500 rounded-full"></span>
                    Online
                  </span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="icon">
                <Phone className="w-4 h-4" />
              </Button>
              <Button variant="ghost" size="icon">
                <Mail className="w-4 h-4" />
              </Button>
              <Button variant="ghost" size="icon">
                <Star className="w-4 h-4" />
              </Button>
              <Button variant="ghost" size="icon">
                <MoreVertical className="w-4 h-4" />
              </Button>
            </div>
          </div>

          {/* Messages */}
          <ScrollArea className="flex-1 p-5">
            <div className="space-y-4">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${message.isOwn ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[70%] px-4 py-3 rounded-2xl ${
                      message.isOwn
                        ? "bg-primary text-white rounded-br-md"
                        : "bg-slate-100 text-slate-800 rounded-bl-md"
                    }`}
                  >
                    <p className="text-sm leading-relaxed">{message.content}</p>
                    <div className={`flex items-center justify-end gap-1.5 mt-1.5 ${message.isOwn ? "text-white/60" : "text-slate-400"}`}>
                      <span className="text-xs">{message.timestamp}</span>
                      {message.isOwn && message.read && <CheckCheck className="w-3.5 h-3.5" />}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>

          {/* AI Suggestions */}
          <div className="px-5 py-3 border-t border-slate-100 bg-gradient-to-r from-primary/5 to-violet-50/50">
            <div className="flex items-center gap-2 mb-2">
              <div className="p-1 rounded bg-primary/10">
                <Bot className="w-3.5 h-3.5 text-primary" />
              </div>
              <span className="text-xs font-medium text-slate-600">AI-Vorschläge</span>
              <Sparkles className="w-3.5 h-3.5 text-amber-500" />
            </div>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {aiSuggestions.map((suggestion, i) => (
                <button
                  key={i}
                  onClick={() => setMessageInput(suggestion)}
                  className="flex-shrink-0 px-3 py-1.5 text-xs font-medium text-primary bg-primary/10 hover:bg-primary/20 rounded-full transition-colors flex items-center gap-1.5"
                >
                  <Zap className="w-3 h-3" />
                  {suggestion}
                </button>
              ))}
            </div>
          </div>

          {/* Input Area */}
          <div className="p-4 border-t border-slate-100 bg-white">
            <div className="flex items-end gap-3">
              <Button variant="ghost" size="icon" className="shrink-0 mb-0.5">
                <Paperclip className="w-5 h-5 text-slate-400" />
              </Button>
              <div className="flex-1 relative">
                <Input
                  value={messageInput}
                  onChange={(e) => setMessageInput(e.target.value)}
                  placeholder="Nachricht schreiben..."
                  className="pr-12 bg-slate-50 border-slate-200 focus:bg-white transition-colors"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      // Handle send
                    }
                  }}
                />
              </div>
              <Button
                size="icon"
                className="shrink-0 shadow-lg shadow-primary/20"
                disabled={!messageInput.trim()}
              >
                <Send className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

