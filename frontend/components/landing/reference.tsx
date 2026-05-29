import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const projects = [
  { name: "TradingAgents-MCPmode", ideas: ["15-agent pipeline", "Dual debate", "Agent toggle"] },
  { name: "Vibe-Trading", ideas: ["SKILL.md format", "Alpha Zoo 452 factors", "BaseTool + MCP"] },
  { name: "TradeMemory Protocol", ideas: ["OWM 5-factor scoring", "Safety gates", "Reflections"] },
  { name: "ContestTrade", ideas: ["Belief contest", "NL trading philosophies"] },
  { name: "QuantGPT", ideas: ["Knowledge base", "Dual-LLM cross-review"] },
  { name: "LLM-Trading-Lab", ideas: ["Behavioral diagnostics", "Disposition effect"] },
];

export function ReferenceSection() {
  return (
    <section id="reference" className="py-20 md:py-28 border-t border-border bg-muted/20">
      <div className="container max-w-7xl mx-auto px-6">
        <div className="text-center mb-16">
          <h2 className="text-3xl font-bold tracking-tight mb-4">
            Informed by 10+ Open-Source Projects
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Our design decisions are grounded in systematic analysis of the best reference
            implementations in the LLM + quantitative finance space.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((p) => (
            <Card key={p.name} className="border-border/50">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-mono">{p.name}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-1.5">
                  {p.ideas.map((idea) => (
                    <Badge key={idea} variant="secondary" className="text-xs font-normal">
                      {idea}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}
