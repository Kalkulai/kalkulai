import { useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Calendar,
  ChevronLeft,
  ChevronRight,
  Plus,
  Clock,
  MapPin,
  User,
  MoreHorizontal,
  Layers,
  Grid3X3,
  List,
} from "lucide-react";

// Demo Projekte
const projects = [
  {
    id: 1,
    title: "Malerei Wohnzimmer Familie Müller",
    client: "Familie Müller",
    address: "Hauptstraße 42, 12345 Musterstadt",
    assignee: "Max Mustermann",
    startTime: "08:00",
    endTime: "16:00",
    day: 0, // Montag
    status: "confirmed",
    color: "bg-blue-500",
  },
  {
    id: 2,
    title: "Fassadenanstrich",
    client: "Gebäudeverwaltung Schmidt",
    address: "Industrieweg 15",
    assignee: "Anna Schmidt",
    startTime: "07:30",
    endTime: "17:00",
    day: 0,
    status: "in_progress",
    color: "bg-emerald-500",
  },
  {
    id: 3,
    title: "Tapezierarbeiten Büro",
    client: "Dr. med. Hoffmann",
    address: "Praxisstraße 8",
    assignee: "Max Mustermann",
    startTime: "09:00",
    endTime: "14:00",
    day: 1, // Dienstag
    status: "confirmed",
    color: "bg-violet-500",
  },
  {
    id: 4,
    title: "Lackierarbeiten Türen",
    client: "Hotel Sonne",
    address: "Marktplatz 1",
    assignee: "Tom Weber",
    startTime: "08:00",
    endTime: "12:00",
    day: 2, // Mittwoch
    status: "pending",
    color: "bg-amber-500",
  },
  {
    id: 5,
    title: "Renovierung Flur",
    client: "Wohnbau eG",
    address: "Parkweg 22",
    assignee: "Anna Schmidt",
    startTime: "13:00",
    endTime: "18:00",
    day: 2,
    status: "confirmed",
    color: "bg-rose-500",
  },
];

const weekDays = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
const fullWeekDays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"];

export default function Plantafel() {
  const [view, setView] = useState<"week" | "day" | "list">("week");
  const [currentWeek, setCurrentWeek] = useState(0);

  // Berechne Wochentage basierend auf aktuellem Datum
  const getWeekDates = (weekOffset: number) => {
    const today = new Date();
    const dayOfWeek = today.getDay();
    const mondayOffset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek;
    
    const monday = new Date(today);
    monday.setDate(today.getDate() + mondayOffset + (weekOffset * 7));
    
    return Array.from({ length: 7 }, (_, i) => {
      const date = new Date(monday);
      date.setDate(monday.getDate() + i);
      return date;
    });
  };

  const weekDates = getWeekDates(currentWeek);
  const today = new Date();

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "confirmed":
        return <Badge className="bg-emerald-100 text-emerald-700 border-0">Bestätigt</Badge>;
      case "in_progress":
        return <Badge className="bg-blue-100 text-blue-700 border-0">In Arbeit</Badge>;
      case "pending":
        return <Badge className="bg-amber-100 text-amber-700 border-0">Ausstehend</Badge>;
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Plantafel</h1>
          <p className="text-slate-500 mt-1">Projekte und Einsätze planen</p>
        </div>
        <div className="flex items-center gap-3">
          {/* View Toggle */}
          <div className="flex items-center bg-slate-100 rounded-lg p-1">
            <button
              onClick={() => setView("week")}
              className={`p-2 rounded-md transition-colors ${
                view === "week" ? "bg-white shadow-sm text-primary" : "text-slate-500 hover:text-slate-700"
              }`}
            >
              <Grid3X3 className="w-4 h-4" />
            </button>
            <button
              onClick={() => setView("day")}
              className={`p-2 rounded-md transition-colors ${
                view === "day" ? "bg-white shadow-sm text-primary" : "text-slate-500 hover:text-slate-700"
              }`}
            >
              <Layers className="w-4 h-4" />
            </button>
            <button
              onClick={() => setView("list")}
              className={`p-2 rounded-md transition-colors ${
                view === "list" ? "bg-white shadow-sm text-primary" : "text-slate-500 hover:text-slate-700"
              }`}
            >
              <List className="w-4 h-4" />
            </button>
          </div>
          <Button className="gap-2 shadow-lg shadow-primary/20">
            <Plus className="w-4 h-4" />
            Neuer Eintrag
          </Button>
        </div>
      </div>

      {/* Week Navigation */}
      <Card className="p-4">
        <div className="flex items-center justify-between">
          <Button variant="ghost" size="icon" onClick={() => setCurrentWeek((w) => w - 1)}>
            <ChevronLeft className="w-5 h-5" />
          </Button>
          <div className="text-center">
            <h2 className="text-lg font-semibold text-slate-900">
              {weekDates[0].toLocaleDateString("de-DE", { day: "numeric", month: "long" })} - {weekDates[6].toLocaleDateString("de-DE", { day: "numeric", month: "long", year: "numeric" })}
            </h2>
            {currentWeek === 0 && (
              <p className="text-sm text-primary font-medium">Diese Woche</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            {currentWeek !== 0 && (
              <Button variant="outline" size="sm" onClick={() => setCurrentWeek(0)}>
                Heute
              </Button>
            )}
            <Button variant="ghost" size="icon" onClick={() => setCurrentWeek((w) => w + 1)}>
              <ChevronRight className="w-5 h-5" />
            </Button>
          </div>
        </div>
      </Card>

      {/* Calendar Grid */}
      <Card className="overflow-hidden">
        {/* Week Header */}
        <div className="grid grid-cols-7 border-b border-slate-200">
          {weekDates.map((date, i) => {
            const isToday = date.toDateString() === today.toDateString();
            return (
              <div
                key={i}
                className={`p-4 text-center border-r last:border-r-0 border-slate-100 ${
                  isToday ? "bg-primary/5" : ""
                }`}
              >
                <p className="text-sm text-slate-500">{weekDays[i]}</p>
                <p
                  className={`text-2xl font-bold mt-1 ${
                    isToday
                      ? "w-10 h-10 bg-primary text-white rounded-full flex items-center justify-center mx-auto"
                      : "text-slate-900"
                  }`}
                >
                  {date.getDate()}
                </p>
              </div>
            );
          })}
        </div>

        {/* Calendar Body */}
        <div className="grid grid-cols-7 min-h-[400px]">
          {weekDates.map((date, dayIndex) => {
            const dayProjects = projects.filter((p) => p.day === dayIndex);
            const isToday = date.toDateString() === today.toDateString();
            return (
              <div
                key={dayIndex}
                className={`border-r last:border-r-0 border-slate-100 p-2 space-y-2 ${
                  isToday ? "bg-primary/5" : ""
                }`}
              >
                {dayProjects.map((project) => (
                  <div
                    key={project.id}
                    className={`group relative p-3 rounded-lg ${project.color} text-white cursor-pointer hover:opacity-95 transition-opacity`}
                  >
                    <button className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <MoreHorizontal className="w-4 h-4" />
                    </button>
                    <p className="font-medium text-sm leading-tight pr-6">{project.title}</p>
                    <div className="mt-2 space-y-1">
                      <div className="flex items-center gap-1.5 text-xs text-white/80">
                        <Clock className="w-3 h-3" />
                        <span>{project.startTime} - {project.endTime}</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-white/80">
                        <User className="w-3 h-3" />
                        <span className="truncate">{project.assignee}</span>
                      </div>
                    </div>
                  </div>
                ))}
                {dayProjects.length === 0 && (
                  <div className="h-full min-h-[100px] flex items-center justify-center">
                    <button className="w-8 h-8 rounded-full border-2 border-dashed border-slate-200 flex items-center justify-center text-slate-300 hover:border-primary hover:text-primary transition-colors">
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Card>

      {/* Upcoming List */}
      <Card className="overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-transparent">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <Calendar className="w-4 h-4 text-primary" />
            </div>
            <div>
              <h2 className="font-semibold text-slate-900">Alle Projekte dieser Woche</h2>
              <p className="text-sm text-slate-500">{projects.length} Einträge</p>
            </div>
          </div>
        </div>
        <div className="divide-y divide-slate-100">
          {projects.map((project) => (
            <div
              key={project.id}
              className="px-5 py-4 flex items-center gap-4 hover:bg-slate-50/50 transition-colors"
            >
              <div className={`w-1.5 h-14 rounded-full ${project.color}`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="font-semibold text-slate-900">{project.title}</p>
                  {getStatusBadge(project.status)}
                </div>
                <p className="text-sm text-slate-600 mt-0.5">{project.client}</p>
                <div className="flex items-center gap-4 mt-1.5 text-sm text-slate-500">
                  <span className="flex items-center gap-1.5">
                    <Calendar className="w-3.5 h-3.5" />
                    {fullWeekDays[project.day]}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5" />
                    {project.startTime} - {project.endTime}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <MapPin className="w-3.5 h-3.5" />
                    {project.address}
                  </span>
                </div>
              </div>
              <div className="text-right">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center">
                    <span className="text-xs font-semibold text-slate-600">
                      {project.assignee.split(" ").map((n) => n[0]).join("")}
                    </span>
                  </div>
                  <span className="text-sm text-slate-600">{project.assignee}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

