"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { Button, buttonVariants } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  LayoutDashboard,
  LineChart,
  Zap,
  TrendingUp,
  Brain,
  Newspaper,
  CheckSquare,
  Search,
  Star,
  Shield,
  FileText,
  Eye,
  Settings,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { useState } from "react";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/agent", label: "Agent", icon: Zap },
  { href: "/quick-ask", label: "Quick Ask", icon: TrendingUp },
  { href: "/strategies", label: "Strategies", icon: TrendingUp },
  { href: "/backtest", label: "Backtest", icon: LineChart },
  { href: "/memory-lab", label: "Memory Lab", icon: Brain },
  { href: "/insights", label: "Insights", icon: Newspaper },
  { href: "/approvals", label: "Approvals", icon: CheckSquare },
  { href: "/scanner", label: "Scanner", icon: Search },
  { href: "/watchlist", label: "Watchlist", icon: Star },
  { href: "/monitor", label: "Monitor", icon: Eye },
  { href: "/risk", label: "Risk", icon: Shield },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        "flex flex-col border-r border-border bg-sidebar transition-all duration-300 h-screen sticky top-0",
        collapsed ? "w-16" : "w-56"
      )}
    >
      {/* Logo */}
      <div className="flex items-center h-14 px-4 border-b border-border">
        {!collapsed && (
          <Link href="/" className="flex items-center gap-2 font-semibold text-sm">
            <div className="h-7 w-7 rounded bg-primary flex items-center justify-center">
              <TrendingUp className="h-4 w-4 text-primary-foreground" />
            </div>
            <span className="truncate">Agentic-Quant</span>
          </Link>
        )}
        {collapsed && (
          <div className="h-7 w-7 rounded bg-primary flex items-center justify-center mx-auto">
            <TrendingUp className="h-4 w-4 text-primary-foreground" />
          </div>
        )}
      </div>

      {/* Nav */}
      <ScrollArea className="flex-1 py-2">
        <nav className="flex flex-col gap-0.5 px-2">
          {navItems.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  buttonVariants({
                    variant: isActive ? "secondary" : "ghost",
                    size: collapsed ? "icon" : "default",
                  }),
                  "justify-start gap-3 h-9",
                  collapsed && "w-10 mx-auto",
                  !collapsed && "w-full px-3"
                )}
              >
                <item.icon className="h-4 w-4 shrink-0" />
                {!collapsed && (
                  <span className="text-sm truncate">{item.label}</span>
                )}
              </Link>
            );
          })}
        </nav>
      </ScrollArea>

      {/* Collapse toggle */}
      <Separator />
      <div className="p-2">
        <Button
          variant="ghost"
          size="icon"
          className="w-full h-8"
          onClick={() => setCollapsed(!collapsed)}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </Button>
      </div>
    </aside>
  );
}
