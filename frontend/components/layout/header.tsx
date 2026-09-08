"use client";

import { usePathname } from "next/navigation";
import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";

const pageTitles: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/quick-ask": "Quick Ask",
  "/strategies": "Strategies",
  "/backtest": "Backtest",
  "/memory-lab": "Memory Lab",
  "/insights": "Insights",
  "/approvals": "Approvals",
  "/scanner": "Scanner",
  "/watchlist": "Watchlist",
  "/risk": "Risk Analytics",
  "/reports": "Reports",
  "/settings": "Settings",
};

export function Header({ onOpenNavigation }: { readonly onOpenNavigation: () => void }) {
  const pathname = usePathname();

  // Find longest matching prefix for nested routes like /strategies/:id
  const title =
    Object.entries(pageTitles).find(([key]) => pathname.startsWith(key))?.[1] ||
    "Agentic-Quant";

  return (
    <header className="flex items-center h-14 px-3 sm:px-6 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-10">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="mr-2 md:hidden"
        onClick={onOpenNavigation}
        aria-label="Open navigation"
      >
        <Menu className="h-5 w-5" />
      </Button>
      <div className="flex items-center gap-4 flex-1">
        <h1 className="text-lg font-semibold">{title}</h1>
        <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded">
          v1.0
        </span>
      </div>
      <div className="flex items-center gap-2">
        {/* Placeholder for market status, notifications, user menu */}
        <div className="hidden sm:flex items-center gap-2 text-sm text-muted-foreground">
          <span className="h-2 w-2 rounded-full bg-green-500" />
          <span>Market Open</span>
        </div>
      </div>
    </header>
  );
}
