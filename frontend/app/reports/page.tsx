"use client";

import { Shell } from "@/components/layout/shell";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { EmptyState } from "@/components/shared/empty-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDate, formatCurrency } from "@/lib/utils";
import { FileText, Download, TrendingUp, PieChart, Clock, CheckCircle2 } from "lucide-react";

const MOCK_REPORTS = [
  {
    id: "r1",
    type: "stock_deep_dive" as const,
    title: "AAPL Deep Dive Analysis",
    tickers: ["AAPL"],
    generated_at: "2026-05-25T14:00:00Z",
    parameters: { sections: ["technical", "fundamental", "news", "risk"] },
  },
  {
    id: "r2",
    type: "sector_analysis" as const,
    title: "Semiconductor Sector Analysis",
    tickers: ["NVDA", "AMD", "INTC", "TSM", "ASML"],
    generated_at: "2026-05-20T10:30:00Z",
    parameters: { theme: "semiconductors" },
  },
  {
    id: "r3",
    type: "stock_deep_dive" as const,
    title: "MSFT Deep Dive Analysis",
    tickers: ["MSFT"],
    generated_at: "2026-05-18T16:00:00Z",
    parameters: { sections: ["technical", "fundamental", "sentiment"] },
  },
];

export default function ReportsPage() {
  const reports = MOCK_REPORTS;

  return (
    <Shell>
      <div className="p-6 space-y-6">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Reports
          </h2>
          <p className="text-sm text-muted-foreground">
            Generate professional PDF research reports with agent-powered analysis.
          </p>
        </div>

        {/* Generate New */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <TrendingUp className="h-4 w-4" />
                Stock Deep Dive
              </CardTitle>
              <CardDescription>
                10-15 page report with full multi-agent analysis.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>Ticker</Label>
                <Input placeholder="AAPL" className="font-mono max-w-[200px]" />
              </div>
              <div>
                <Label className="text-sm mb-2 block">Sections</Label>
                <div className="flex gap-2 flex-wrap">
                  {["Technical", "News", "Fundamentals", "Sentiment", "Risk", "Debate"].map(
                    (s) => (
                      <Badge key={s} variant="outline" className="cursor-pointer hover:bg-primary/10">
                        {s}
                      </Badge>
                    )
                  )}
                </div>
              </div>
              <Button className="w-full">
                <FileText className="mr-2 h-4 w-4" />
                Generate Report
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <PieChart className="h-4 w-4" />
                Sector Analysis
              </CardTitle>
              <CardDescription>
                Auto-discover tickers in a sector and generate aggregated analysis.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>Sector / Theme</Label>
                <Input placeholder="e.g. AI, Semiconductors, Clean Energy" />
              </div>
              <Button className="w-full" variant="outline">
                <FileText className="mr-2 h-4 w-4" />
                Generate Sector Report
              </Button>
            </CardContent>
          </Card>
        </div>

        <Separator />

        {/* Report History */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Clock className="h-4 w-4" />
              Report History
            </CardTitle>
          </CardHeader>
          <CardContent>
            {reports.length === 0 ? (
              <EmptyState
                title="No reports yet"
                description="Generated reports will appear here for download."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Title</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Tickers</TableHead>
                    <TableHead>Tickers Count</TableHead>
                    <TableHead>Generated</TableHead>
                    <TableHead className="w-12" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {reports.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell className="font-medium">{r.title}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className="capitalize">
                          {r.type.replace(/_/g, " ")}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1 flex-wrap">
                          {r.tickers.map((t) => (
                            <span key={t} className="text-xs font-mono text-muted-foreground">
                              ${t}
                            </span>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell className="text-sm">{r.tickers.length}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {formatDate(r.generated_at)}
                      </TableCell>
                      <TableCell>
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <Download className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </Shell>
  );
}
