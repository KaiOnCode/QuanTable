import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Bot,
  MessageSquare,
  Brain,
  Shield,
  Database,
  Globe,
  BarChart3,
  Zap,
  Server,
  TrendingUp,
  Bell,
  Search,
} from "lucide-react";

const features = [
  {
    title: "15-Agent Pipeline",
    description: "Market, News, Fundamentals, Sentiment, Technical, Macro analysts run in parallel. Bull vs Bear debate. 3-way risk analysis.",
    icon: Bot,
  },
  {
    title: "Structured Debate",
    description: "Investment debate: Bull vs Bear (configurable rounds). Risk debate: Aggressive vs Safe vs Neutral. Research Manager synthesizes.",
    icon: MessageSquare,
  },
  {
    title: "OWM Strategy Memory",
    description: "Outcome-Weighted Memory — 5-factor scoring learns from every past trade. Pre-trade safety gates prevent repeat mistakes.",
    icon: Brain,
  },
  {
    title: "HITL Approval",
    description: "Human-in-the-loop gatekeeping with dual-LLM cross-review. Risky decisions require human sign-off via multi-channel notifications.",
    icon: Shield,
  },
  {
    title: "Multi-Source Data",
    description: "Yahoo Finance, Google News, AkShare, Finnhub with automatic fallback. Sentiment aggregation. All data persisted for backtesting.",
    icon: Database,
  },
  {
    title: "MCP Interoperability",
    description: "Expose analysis tools to external AI agents via MCP. Load external MCP servers. Stdio, SSE, and streamable HTTP transports.",
    icon: Server,
  },
  {
    title: "React Dashboard",
    description: "14 interactive pages — Quick Ask with SSE streaming, Strategy management, Backtest, Memory Lab, Risk Analytics, and more.",
    icon: BarChart3,
  },
  {
    title: "Knowledge Base",
    description: "Rules, findings, and failures accumulate per strategy. Hypotheses tracked through draft → validating → confirmed/rejected lifecycle.",
    icon: Search,
  },
];

export function FeaturesSection() {
  return (
    <section id="features" className="py-20 md:py-28 border-t border-border">
      <div className="container max-w-7xl mx-auto px-6">
        <div className="text-center mb-16">
          <h2 className="text-3xl font-bold tracking-tight mb-4">
            Everything an AI Trading System Needs
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Built from analysis of 10+ open-source trading agent projects.
            Each component is modular, testable, and designed for extensibility.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((f) => (
            <Card key={f.title} className="border-border/50 hover:border-primary/30 transition-colors">
              <CardHeader>
                <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center mb-3">
                  <f.icon className="h-5 w-5 text-primary" />
                </div>
                <CardTitle className="text-base">{f.title}</CardTitle>
                <CardDescription className="text-sm leading-relaxed">{f.description}</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}
