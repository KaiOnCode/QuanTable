"use client";

import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { TrendingUp, Menu, X } from "lucide-react";
import { useState } from "react";

export function LandingNavbar() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-14 max-w-7xl mx-auto items-center px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <div className="h-7 w-7 rounded-lg bg-primary flex items-center justify-center">
            <TrendingUp className="h-4 w-4 text-primary-foreground" />
          </div>
          <span>Agentic-Quant</span>
        </Link>

        <nav className="hidden md:flex items-center gap-6 ml-10 text-sm">
          <Link href="#features" className="text-muted-foreground hover:text-foreground transition-colors">
            Features
          </Link>
          <Link href="#architecture" className="text-muted-foreground hover:text-foreground transition-colors">
            Architecture
          </Link>
          <Link href="#reference" className="text-muted-foreground hover:text-foreground transition-colors">
            Research
          </Link>
          <Link href="/docs" className="text-muted-foreground hover:text-foreground transition-colors">
            Docs
          </Link>
        </nav>

        <div className="flex-1" />

        <div className="hidden md:flex items-center gap-3">
          <Link href="/dashboard" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            Dashboard
          </Link>
          <Link href="/quick-ask" className={buttonVariants({ size: "sm" })}>
            Quick Ask
          </Link>
        </div>

        <Button
          variant="ghost"
          size="icon"
          className="md:hidden"
          onClick={() => setOpen(!open)}
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </Button>
      </div>

      {open && (
        <div className="md:hidden border-t border-border px-6 py-4 space-y-3">
          <Link href="#features" className="block text-sm text-muted-foreground" onClick={() => setOpen(false)}>Features</Link>
          <Link href="#architecture" className="block text-sm text-muted-foreground" onClick={() => setOpen(false)}>Architecture</Link>
          <Link href="#reference" className="block text-sm text-muted-foreground" onClick={() => setOpen(false)}>Research</Link>
          <div className="pt-2 flex gap-3">
            <Link href="/dashboard" className={buttonVariants({ variant: "outline", size: "sm" })}>Dashboard</Link>
            <Link href="/quick-ask" className={buttonVariants({ size: "sm" })}>Quick Ask</Link>
          </div>
        </div>
      )}
    </header>
  );
}
