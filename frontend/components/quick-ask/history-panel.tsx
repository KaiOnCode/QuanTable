"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ActionBadge, DirectionBadge } from "@/components/shared/badges";
import { formatDateTime } from "@/lib/utils";
import { History, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { analyzeApi } from "@/lib/api/analyze";
import type { AnalysisHistoryItem } from "@/lib/types/models";

export function HistoryPanel() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<AnalysisHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (open) {
      setLoading(true);
      analyzeApi
        .listHistory(30)
        .then((data) => setItems(data.items || []))
        .catch(() => {})
        .finally(() => setLoading(false));
    }
  }, [open]);

  const handleSelect = (item: AnalysisHistoryItem) => {
    setOpen(false);
    router.push(`/quick-ask/${item.session_id}`);
  };

  const deleteItem = async (item: AnalysisHistoryItem) => {
    if (deletingIds.has(item.session_id)) return;

    setDeletingIds((prev) => new Set(prev).add(item.session_id));
    try {
      await analyzeApi.deleteHistory(item.session_id);
      setItems((prev) => prev.filter((i) => i.session_id !== item.session_id));
    } catch (error: unknown) {
      toast.error("Failed to delete analysis history", {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(item.session_id);
        return next;
      });
    }
  };

  const handleDelete = (e: React.MouseEvent, item: AnalysisHistoryItem) => {
    e.stopPropagation();
    void deleteItem(item);
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <Button variant="outline" size="sm" className="gap-1.5" onClick={() => setOpen(true)}>
        <History className="h-4 w-4" />
        History
      </Button>
      <SheetContent side="right">
        <SheetHeader>
          <SheetTitle>Ask History</SheetTitle>
        </SheetHeader>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground py-8 text-center">
            No analysis history yet
          </p>
        ) : (
          <ScrollArea className="flex-1 -mx-4 px-4">
            <div className="space-y-1">
              {items.map((item) => (
                <button
                  key={item.session_id}
                  onClick={() => handleSelect(item)}
                  className="w-full text-left p-3 rounded-lg hover:bg-muted/50 transition-colors group flex items-start"
                >
                  <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono font-bold text-sm">
                      {item.ticker}
                    </span>
                    {item.action && <ActionBadge action={item.action} />}
                    {item.direction && <DirectionBadge direction={item.direction} />}
                    {item.status !== "completed" && (
                      <Badge
                        variant={item.status === "failed" ? "destructive" : "secondary"}
                        className="text-[10px] px-1.5 py-0"
                      >
                        {item.status}
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span>{formatDateTime(item.created_at)}</span>
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                      {item.mode}
                    </Badge>
                    {item.confidence != null && (
                      <span className="font-mono">
                        {(item.confidence * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                  {item.oneliner && (
                    <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                      {item.oneliner}
                    </p>
                  )}
                  </div>
                  <span
                    onClick={(e) => handleDelete(e, item)}
                    className={`shrink-0 p-1 rounded transition-colors cursor-pointer ${
                      deletingIds.has(item.session_id)
                        ? "opacity-50 pointer-events-none"
                        : "hover:bg-destructive/10"
                    }`}
                    title="Delete"
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        e.stopPropagation();
                        void deleteItem(item);
                      }
                    }}
                  >
                    <X className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
                  </span>
                </button>
              ))}
            </div>
          </ScrollArea>
        )}
      </SheetContent>
    </Sheet>
  );
}
