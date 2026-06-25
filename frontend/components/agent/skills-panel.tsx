"use client";

import { useState, useEffect, useCallback } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Search, BookOpen, X, Loader2, Trash2 } from "lucide-react";
import ReactMarkdown from "react-markdown";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

type SkillSummary = {
  name: string;
  category: string;
  description: string;
  version: string;
  is_builtin: boolean;
  tools?: string[];
};

type SkillDetail = SkillSummary & {
  content: string;
  file_path: string;
};

export function SkillsPanel({ onClose }: { onClose: () => void }) {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [selectedCat, setSelectedCat] = useState("");
  const [search, setSearch] = useState("");
  const [selectedSkill, setSelectedSkill] = useState<SkillDetail | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchSkills = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (selectedCat) params.set("category", selectedCat);
    if (search) params.set("search", search);
    fetch(`${API_BASE}/agent/skills?${params}`)
      .then((r) => r.json())
      .then((d) => {
        setSkills(d.skills || []);
        if (!selectedCat && !search) {
          setCategories(Object.keys(d.categories || {}).sort());
        }
      })
      .finally(() => setLoading(false));
  }, [selectedCat, search]);

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  const loadSkillDetail = (name: string) => {
    fetch(`${API_BASE}/agent/skills/${name}`)
      .then((r) => r.json())
      .then(setSelectedSkill);
  };

  const deleteSkill = async (name: string) => {
    await fetch(`${API_BASE}/agent/skills/${name}`, { method: "DELETE" });
    setSelectedSkill(null);
    fetchSkills();
  };

  return (
    <div className="flex flex-col h-full border-l bg-background">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <BookOpen className="h-4 w-4 shrink-0" />
          <span className="font-semibold text-sm truncate">Skills ({skills.length})</span>
        </div>
        <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={onClose}>
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Search + Category filter */}
      <div className="px-3 py-2 space-y-1.5 border-b shrink-0">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            className="h-7 pl-7 text-xs"
            placeholder="Search skills..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="flex gap-1 flex-wrap">
          <Badge
            variant={selectedCat === "" ? "default" : "outline"}
            className="cursor-pointer text-[10px]"
            onClick={() => setSelectedCat("")}
          >
            All
          </Badge>
          {categories.map((cat) => (
            <Badge
              key={cat}
              variant={selectedCat === cat ? "default" : "outline"}
              className="cursor-pointer text-[10px]"
              onClick={() => setSelectedCat(cat)}
            >
              {cat}
            </Badge>
          ))}
        </div>
      </div>

      {/* Skill list */}
      <ScrollArea className="flex-1">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-4 w-4 animate-spin" />
          </div>
        ) : (
          <div className="p-1.5 space-y-0.5">
            {skills.map((s) => (
              <div
                key={s.name}
                role="button"
                tabIndex={0}
                className={`w-full text-left px-2 py-1.5 rounded text-xs transition-colors cursor-pointer ${
                  selectedSkill?.name === s.name
                    ? "bg-primary/10 border border-primary/20"
                    : "hover:bg-muted/50"
                }`}
                onClick={() => loadSkillDetail(s.name)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") loadSkillDetail(s.name);
                }}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium truncate">{s.name}</span>
                  <div className="flex items-center gap-1 shrink-0 ml-1">
                    {!s.is_builtin && (
                      <Badge variant="secondary" className="text-[9px] h-4 px-1">
                        user
                      </Badge>
                    )}
                  </div>
                </div>
                <p className="text-[10px] text-muted-foreground truncate mt-0.5">
                  {s.description}
                </p>
              </div>
            ))}
            {skills.length === 0 && !loading && (
              <p className="text-xs text-muted-foreground text-center py-4">
                No skills found
              </p>
            )}
          </div>
        )}
      </ScrollArea>

      {/* Skill detail */}
      {selectedSkill && (
        <div className="border-t shrink-0 flex flex-col" style={{ maxHeight: "40%" }}>
          <div className="flex items-center justify-between px-3 py-1.5 border-b bg-muted/20">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="text-xs font-medium truncate">{selectedSkill.name}</span>
              {!selectedSkill.is_builtin && (
                <Badge variant="secondary" className="text-[9px] h-4 px-1">
                  user
                </Badge>
              )}
              <span className="text-[9px] text-muted-foreground">
                {selectedSkill.category}
              </span>
            </div>
            <div className="flex items-center gap-0.5 shrink-0">
              {!selectedSkill.is_builtin && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-5 w-5 p-0 text-destructive hover:text-destructive"
                  onClick={() => deleteSkill(selectedSkill.name)}
                  title="Delete"
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                className="h-5 w-5 p-0"
                onClick={() => setSelectedSkill(null)}
              >
                <X className="h-3 w-3" />
              </Button>
            </div>
          </div>
          <ScrollArea className="flex-1 p-2">
            <div className="text-xs prose prose-sm dark:prose-invert max-w-none">
              <ReactMarkdown>{selectedSkill.content.slice(0, 5000)}</ReactMarkdown>
            </div>
          </ScrollArea>
        </div>
      )}
    </div>
  );
}
