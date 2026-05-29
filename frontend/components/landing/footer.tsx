import Link from "next/link";
import { TrendingUp } from "lucide-react";

export function LandingFooter() {
  return (
    <footer className="border-t border-border py-12">
      <div className="container max-w-7xl mx-auto px-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-12">
          <div>
            <h4 className="text-sm font-semibold mb-3">Product</h4>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li><Link href="/quick-ask" className="hover:text-foreground transition-colors">Quick Ask</Link></li>
              <li><Link href="/strategies" className="hover:text-foreground transition-colors">Strategies</Link></li>
              <li><Link href="/backtest" className="hover:text-foreground transition-colors">Backtest</Link></li>
              <li><Link href="/memory-lab" className="hover:text-foreground transition-colors">Memory Lab</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="text-sm font-semibold mb-3">Analytics</h4>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li><Link href="/risk" className="hover:text-foreground transition-colors">Risk Analytics</Link></li>
              <li><Link href="/scanner" className="hover:text-foreground transition-colors">Scanner</Link></li>
              <li><Link href="/insights" className="hover:text-foreground transition-colors">Insights</Link></li>
              <li><Link href="/reports" className="hover:text-foreground transition-colors">Reports</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="text-sm font-semibold mb-3">Resources</h4>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li><a href="https://github.com/KaiOnCode/COMP7705-Agent-Quant" className="hover:text-foreground transition-colors">GitHub</a></li>
              <li><Link href="/docs" className="hover:text-foreground transition-colors">Documentation</Link></li>
              <li><Link href="/settings" className="hover:text-foreground transition-colors">Settings</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="text-sm font-semibold mb-3">About</h4>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li>University of Hong Kong</li>
              <li>COMP7705 — 2026</li>
              <li>School of Computing</li>
            </ul>
          </div>
        </div>

        <div className="border-t border-border pt-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <TrendingUp className="h-4 w-4" />
            <span>Agentic-Quant — Multi-Agent Framework for Quantitative Analysis</span>
          </div>
          <p className="text-xs text-muted-foreground">
            This system provides analysis for research purposes only. It does not constitute investment advice.
          </p>
        </div>
      </div>
    </footer>
  );
}
