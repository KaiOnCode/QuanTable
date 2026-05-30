import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { TrendingUp, ChevronRight } from "lucide-react";

export function HeroSection() {
  return (
    <section className="relative py-20 md:py-32 overflow-hidden">
      {/* Background gradient */}
      <div className="absolute inset-0 bg-gradient-to-b from-primary/5 via-transparent to-transparent" />
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[600px] bg-primary/5 rounded-full blur-3xl" />

      <div className="container max-w-5xl mx-auto px-6 relative">
        <div className="text-center space-y-6">
          <Badge variant="outline" className="text-sm px-4 py-1.5 border-primary/20">
            University of Hong Kong — COMP7705 Final Year Project
          </Badge>

          <h1 className="text-4xl md:text-6xl font-bold tracking-tight leading-tight">
            Multi-Agent Framework for{" "}
            <span className="text-primary">Reasoning-Based</span>{" "}
            Quantitative Analysis
          </h1>

          <p className="text-lg md:text-xl text-muted-foreground max-w-3xl mx-auto leading-relaxed">
            Up to 15 specialized LLM agents collaborate with structured debate — bull vs bear,
            3-way risk analysis — to produce verifiable investment decisions. Built with
            LangGraph, backed by strategy memory and knowledge accumulation.
          </p>

          <div className="flex items-center justify-center gap-4 pt-4 flex-wrap">
            <Link href="/quick-ask" className={buttonVariants({ size: "lg" })}>
              Try Quick Ask
              <ChevronRight className="ml-1 h-4 w-4" />
            </Link>
            <Link href="/dashboard" className={buttonVariants({ variant: "outline", size: "lg" })}>
              Open Dashboard
            </Link>
          </div>

          <div className="pt-8 flex items-center justify-center gap-8 text-sm text-muted-foreground">
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-green-500" />
              <span>15 Specialized Agents</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-green-500" />
              <span>452 Alpha Factors</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-green-500" />
              <span>OWM Strategy Memory</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
