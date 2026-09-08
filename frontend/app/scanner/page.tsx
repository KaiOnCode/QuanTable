"use client";

import { Suspense, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Shell } from "@/components/layout/shell";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { scannerApi } from "@/lib/api/scanner";
import { strategiesApi } from "@/lib/api/strategies";
import type {
  ScanCondition,
  ScanResult,
  ScanRun,
  ScannerAgentRequest,
  ScannerBeliefRequest,
  ScannerField,
  ScannerMode,
  ScannerOperator,
  ScannerRuleRequest,
  ScannerSnapshotValue,
} from "@/lib/types/models";
import {
  BarChart3,
  Bot,
  Brain,
  Loader2,
  Plus,
  Search,
  Trash2,
} from "lucide-react";

type RuleDraft = {
  readonly id: string;
  readonly field: ScannerField;
  readonly operator: ScannerOperator;
  readonly value: string;
  readonly value2: string;
};

type ScannerRequest =
  | { readonly kind: "rule"; readonly request: ScannerRuleRequest }
  | { readonly kind: "agent"; readonly request: ScannerAgentRequest }
  | { readonly kind: "belief"; readonly request: ScannerBeliefRequest };

const fieldLabels: Readonly<Record<ScannerField, string>> = {
  price: "Price",
  change_pct: "Change %",
  volume: "Volume",
  rsi14: "RSI (14)",
  sma20: "SMA (20)",
  sma50: "SMA (50)",
  pe_ratio: "P/E ratio",
  pb_ratio: "P/B ratio",
  market_cap: "Market cap",
  sector: "Sector",
};

const operatorLabels: Readonly<Record<ScannerOperator, string>> = {
  "<": "<",
  ">": ">",
  "<=": "≤",
  ">=": "≥",
  "==": "equals",
  between: "between",
};

const numericFields = new Set<ScannerField>([
  "price",
  "change_pct",
  "volume",
  "rsi14",
  "sma20",
  "sma50",
  "pe_ratio",
  "pb_ratio",
  "market_cap",
]);

const allOperators: readonly ScannerOperator[] = [
  "<",
  ">",
  "<=",
  ">=",
  "==",
  "between",
];

let ruleSequence = 0;

function isScannerField(value: string): value is ScannerField {
  return Object.hasOwn(fieldLabels, value);
}

function isScannerOperator(value: string): value is ScannerOperator {
  return Object.hasOwn(operatorLabels, value);
}

function defaultRule(): RuleDraft {
  ruleSequence += 1;
  return { id: `scanner-rule-${ruleSequence}`, field: "rsi14", operator: "<", value: "30", value2: "" };
}

function operatorsForField(field: ScannerField): readonly ScannerOperator[] {
  return field === "sector" ? ["=="] : allOperators;
}

function messageFor(error: unknown): string {
  return error instanceof Error ? error.message : "The scanner request could not be completed.";
}

function displayCondition(condition: ScanCondition): string {
  const field = fieldLabels[condition.field];
  if (condition.operator === "between") {
    return `${field} between ${condition.value} and ${condition.value2}`;
  }
  return `${field} ${operatorLabels[condition.operator]} ${condition.value}`;
}

function conditionKey(condition: ScanCondition): string {
  return `${condition.field}-${condition.operator}-${condition.value}-${condition.value2 ?? "none"}`;
}

function displaySnapshot(value: ScannerSnapshotValue): string {
  if (value.value === null) return "Unknown";
  if (typeof value.value === "string") return value.value;

  switch (value.unit) {
    case "percentage_points":
      return `${value.value >= 0 ? "+" : ""}${value.value.toFixed(2)}%`;
    case "shares":
      return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value.value);
    case "multiple":
      return value.value.toFixed(2);
    case "0_to_100":
      return value.value.toFixed(1);
    case "ticker_currency":
    case "absolute_currency":
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: value.currency ?? "USD",
        maximumFractionDigits: Math.abs(value.value) >= 1000 ? 0 : 2,
      }).format(value.value);
    default:
      return value.value.toLocaleString("en-US", { maximumFractionDigits: 2 });
  }
}

function displaySources(result: ScanResult): string {
  return result.provenance.join(", ");
}

function parseRule(draft: RuleDraft, index: number): ScanCondition | string {
  const label = `Condition ${index + 1}`;
  if (draft.field === "sector") {
    if (draft.operator !== "==") return `${label}: Sector only supports equals.`;
    const sector = draft.value.trim();
    return sector
      ? { field: "sector", operator: "==", value: sector, value2: null }
      : `${label}: Enter a sector.`;
  }

  if (!numericFields.has(draft.field)) return `${label}: Unsupported field.`;
  const first = Number(draft.value);
  if (!Number.isFinite(first)) return `${label}: Enter a finite numeric value.`;
  const second = Number(draft.value2);
  if (draft.operator === "between") {
    if (!Number.isFinite(second)) return `${label}: Between requires two finite values.`;
    if (first > second) return `${label}: The lower value cannot exceed the upper value.`;
    if (draft.field === "rsi14" && (first < 0 || second > 100)) {
      return `${label}: RSI values must be between 0 and 100.`;
    }
    return { field: draft.field, operator: "between", value: first, value2: second };
  }
  if (draft.field === "rsi14" && (first < 0 || first > 100)) {
    return `${label}: RSI values must be between 0 and 100.`;
  }
  return { field: draft.field, operator: draft.operator, value: first, value2: null };
}

function ScannerContent() {
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<ScannerMode>("rule");
  const [rules, setRules] = useState<readonly RuleDraft[]>([defaultRule()]);
  const [agentQuery, setAgentQuery] = useState("");
  const [requestedStrategyId, setRequestedStrategyId] = useState("");
  const [requestedBelief, setRequestedBelief] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(() => searchParams.get("scan_run_id"));
  const [run, setRun] = useState<ScanRun | null>(null);

  const strategiesQuery = useQuery({
    queryKey: ["strategies"],
    queryFn: () => strategiesApi.list(),
    retry: false,
  });
  const strategies = strategiesQuery.data?.items ?? [];
  const selectedStrategy =
    strategies.find((strategy) => strategy.id === requestedStrategyId) ?? strategies[0];
  const selectedStrategyId = selectedStrategy?.id ?? "";
  const beliefs = selectedStrategy?.beliefs ?? [];
  const selectedBelief = beliefs.includes(requestedBelief) ? requestedBelief : beliefs[0] ?? "";

  const runQuery = useQuery({
    queryKey: ["scanner-run", runId],
    queryFn: () => scannerApi.getRun(runId ?? ""),
    enabled: runId !== null,
    retry: false,
  });

  const scanMutation = useMutation({
    mutationFn: (payload: ScannerRequest) => {
      switch (payload.kind) {
        case "rule":
          return scannerApi.scanRule(payload.request);
        case "agent":
          return scannerApi.scanAgent(payload.request);
        case "belief":
          return scannerApi.scanBelief(payload.request);
      }
    },
    onSuccess: (created) => {
      setValidationError(null);
      setRun(created);
      setRunId(created.id);
      const url = new URL(window.location.href);
      url.searchParams.set("scan_run_id", created.id);
      window.history.replaceState(null, "", url);
    },
  });

  const latestRun = run ?? runQuery.data ?? null;
  const visibleMode = latestRun?.mode ?? mode;
  const activeRun = latestRun?.mode === visibleMode ? latestRun : null;
  const result = activeRun?.result ?? null;
  const requestError = scanMutation.isError ? messageFor(scanMutation.error) : null;

  const updateRule = (index: number, change: Partial<RuleDraft>) => {
    setRules((current) => current.map((rule, ruleIndex) =>
      ruleIndex === index ? { ...rule, ...change } : rule,
    ));
  };

  const selectMode = (nextMode: ScannerMode) => {
    setMode(nextMode);
    setRun(null);
    setRunId(null);
    setValidationError(null);
    const url = new URL(window.location.href);
    url.searchParams.delete("scan_run_id");
    window.history.replaceState(null, "", url);
  };

  const submitRule = () => {
    const conditions: ScanCondition[] = [];
    const errors: string[] = [];
    rules.forEach((rule, index) => {
      const parsed = parseRule(rule, index);
      if (typeof parsed === "string") errors.push(parsed);
      else conditions.push(parsed);
    });
    if (errors.length > 0) {
      setValidationError(errors.join(" "));
      return;
    }
    setValidationError(null);
    scanMutation.mutate({ kind: "rule", request: { conditions, universe: "tracked" } });
  };

  const submitAgent = () => {
    const query = agentQuery.trim();
    if (!query) {
      setValidationError("Describe the tracked-market scan you want to run.");
      return;
    }
    setValidationError(null);
    scanMutation.mutate({ kind: "agent", request: { mode: "agent", query } });
  };

  const submitBelief = () => {
    if (!selectedStrategyId) {
      setValidationError("Choose a persisted strategy with a belief.");
      return;
    }
    if (!selectedBelief) {
      setValidationError("This strategy has no selectable belief text.");
      return;
    }
    setValidationError(null);
    scanMutation.mutate({
      kind: "belief",
      request: {
        mode: "belief",
        strategy_id: selectedStrategyId,
        belief_text: selectedBelief,
      },
    });
  };

  const pending = scanMutation.isPending || runQuery.isLoading;
  const visibleError = validationError ?? requestError ?? activeRun?.error?.message ?? null;

  return (
    <Shell>
      <div className="space-y-6 p-4 sm:p-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Search className="h-5 w-5" /> Market Scanner
          </h2>
          <p className="text-sm text-muted-foreground">
            Evaluate only the tracked universe using deterministic rules or a restricted scanner agent.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Scanner request</CardTitle>
            <CardDescription>
              Tracked universe merges tickers from strategies, watchlists, and the cached market store.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant={visibleMode === "rule" ? "default" : "outline"} size="sm" onClick={() => selectMode("rule")}>
                <BarChart3 className="mr-2 h-4 w-4" /> Rule-Based
              </Button>
              <Button type="button" variant={visibleMode === "agent" ? "default" : "outline"} size="sm" onClick={() => selectMode("agent")}>
                <Bot className="mr-2 h-4 w-4" /> Agent-Driven
              </Button>
              <Button type="button" variant={visibleMode === "belief" ? "default" : "outline"} size="sm" onClick={() => selectMode("belief")}>
                <Brain className="mr-2 h-4 w-4" /> Belief-Driven
              </Button>
            </div>

            {visibleMode === "rule" ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Badge variant="secondary">Tracked universe</Badge>
                  <span>Conditions are combined with AND.</span>
                </div>
                {rules.map((rule, index) => {
                  const supportsBetween = rule.operator === "between";
                  return (
                    <div key={rule.id} className="grid grid-cols-1 gap-3 rounded-lg border p-3 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]">
                      <div className="space-y-1">
                        <Label htmlFor={`scanner-rule-field-${index}`} className="text-xs">Field</Label>
                        <Select value={rule.field} onValueChange={(value) => {
                          if (!value || !isScannerField(value)) return;
                          updateRule(index, {
                            field: value,
                            operator: value === "sector" ? "==" : rule.operator === "==" && numericFields.has(value) ? ">" : rule.operator,
                            value: value === "sector" ? "Technology" : rule.value,
                            value2: "",
                          });
                        }}>
                          <SelectTrigger id={`scanner-rule-field-${index}`} className="w-full"><SelectValue /></SelectTrigger>
                          <SelectContent>{Object.entries(fieldLabels).map(([field, label]) => <SelectItem key={field} value={field}>{label}</SelectItem>)}</SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor={`scanner-rule-operator-${index}`} className="text-xs">Operator</Label>
                        <Select value={rule.operator} onValueChange={(value) => {
                          if (value && isScannerOperator(value)) updateRule(index, { operator: value, value2: "" });
                        }}>
                          <SelectTrigger id={`scanner-rule-operator-${index}`} className="w-full"><SelectValue /></SelectTrigger>
                          <SelectContent>{operatorsForField(rule.field).map((operator) => <SelectItem key={operator} value={operator}>{operatorLabels[operator]}</SelectItem>)}</SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor={`scanner-rule-value-${index}`} className="text-xs">{supportsBetween ? "Lower value" : "Value"}</Label>
                        <Input id={`scanner-rule-value-${index}`} value={rule.value} onChange={(event) => updateRule(index, { value: event.target.value })} inputMode={rule.field === "sector" ? "text" : "decimal"} placeholder={rule.field === "sector" ? "Technology" : "30"} />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor={`scanner-rule-value2-${index}`} className="text-xs">Upper value</Label>
                        <Input id={`scanner-rule-value2-${index}`} value={rule.value2} onChange={(event) => updateRule(index, { value2: event.target.value })} inputMode="decimal" placeholder={supportsBetween ? "70" : "Not used"} disabled={!supportsBetween} />
                      </div>
                      <div className="flex items-end">
                        <Button type="button" variant="ghost" size="icon" aria-label={`Remove condition ${index + 1}`} disabled={rules.length === 1} onClick={() => setRules((current) => current.filter((_rule, ruleIndex) => ruleIndex !== index))}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  );
                })}
                <div className="flex flex-wrap gap-3">
                  <Button type="button" variant="outline" onClick={() => setRules((current) => [...current, defaultRule()])}>
                    <Plus className="mr-2 h-4 w-4" /> Add Condition
                  </Button>
                  <Button type="button" onClick={submitRule} disabled={scanMutation.isPending}>
                    {scanMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Search className="mr-2 h-4 w-4" />} Scan tracked universe
                  </Button>
                </div>
              </div>
            ) : null}

            {visibleMode === "agent" ? (
              <div className="space-y-3">
                <Label htmlFor="scanner-agent-query">What should the restricted scanner find?</Label>
                <Textarea id="scanner-agent-query" value={agentQuery} onChange={(event) => setAgentQuery(event.target.value)} placeholder="Find tracked stocks with price above 140" className="min-h-20 resize-y" />
                <p className="text-xs text-muted-foreground">The agent can only compile typed conditions and call the tracked-universe scanner once.</p>
                <Button type="button" onClick={submitAgent} disabled={scanMutation.isPending}>
                  {scanMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Bot className="mr-2 h-4 w-4" />} Scan with Agent
                </Button>
              </div>
            ) : null}

            {visibleMode === "belief" ? (
              <div className="space-y-4">
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="scanner-belief-strategy">Strategy</Label>
                    <Select value={selectedStrategyId} onValueChange={(value) => {
                      if (!value) return;
                      setRequestedStrategyId(value);
                      setRequestedBelief("");
                    }} disabled={strategiesQuery.isLoading || strategiesQuery.isError || strategies.length === 0}>
                      <SelectTrigger id="scanner-belief-strategy" className="w-full"><SelectValue placeholder="Select strategy" /></SelectTrigger>
                      <SelectContent>{strategies.map((strategy) => <SelectItem key={strategy.id} value={strategy.id}>{strategy.name}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="scanner-belief-text">Belief text</Label>
                    <Select value={selectedBelief} onValueChange={(value) => { if (value) setRequestedBelief(value); }} disabled={!selectedStrategyId || beliefs.length === 0}>
                      <SelectTrigger id="scanner-belief-text" className="w-full"><SelectValue placeholder={beliefs.length === 0 ? "No beliefs on this strategy" : "Select belief"} /></SelectTrigger>
                      <SelectContent>{beliefs.map((belief) => <SelectItem key={belief} value={belief}>{belief}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                </div>
                {strategiesQuery.isLoading ? <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading persisted strategies</p> : null}
                {strategiesQuery.isError ? <p className="text-sm text-destructive" role="alert">Failed to load strategies: {messageFor(strategiesQuery.error)}</p> : null}
                {!strategiesQuery.isLoading && !strategiesQuery.isError && strategies.length === 0 ? <p className="text-sm text-muted-foreground">Create a strategy with at least one belief before running a belief scan.</p> : null}
                {selectedStrategyId && beliefs.length === 0 ? <p className="text-sm text-muted-foreground">This strategy has no belief text available for a scanner request.</p> : null}
                <Button type="button" onClick={submitBelief} disabled={scanMutation.isPending || !selectedStrategyId || !selectedBelief}>
                  {scanMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Brain className="mr-2 h-4 w-4" />} Scan with Belief
                </Button>
              </div>
            ) : null}

            {visibleError ? <p className="text-sm text-destructive" role="alert">{visibleError}</p> : null}
          </CardContent>
        </Card>

        {pending && runId ? <Card><CardContent className="flex items-center gap-2 pt-6 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading persisted scanner run {runId}</CardContent></Card> : null}
        {runQuery.isError ? <Card className="border-destructive"><CardContent className="pt-6 text-sm" role="alert">Unable to load this scanner run: {messageFor(runQuery.error)}</CardContent></Card> : null}

        {!activeRun && !pending && !visibleError ? <Card><CardContent className="pt-2"><EmptyState icon={<Search className="h-12 w-12" />} title="No scanner run selected" description="Choose a mode, then run the tracked universe. Results appear only after the API returns a persisted run." /></CardContent></Card> : null}

        {activeRun?.compiled_conditions ? <Card>
          <CardHeader><CardTitle className="text-base">Compiled conditions</CardTitle><CardDescription>Conditions persisted with this {activeRun.mode} scanner run.</CardDescription></CardHeader>
          <CardContent className="flex flex-wrap gap-2">{activeRun.compiled_conditions.map((condition) => <Badge key={conditionKey(condition)} variant="secondary">{displayCondition(condition)}</Badge>)}</CardContent>
        </Card> : null}

        {result ? <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Tracked-universe result</CardTitle>
              <CardDescription>{result.scanned_count} scanned · {result.matched_count} matched · {result.missing_data_count} with missing required data</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {result.warnings.length > 0 ? <div className="rounded-lg border border-yellow-500/40 bg-yellow-500/10 p-3 text-sm" role="status"><p className="font-medium">Partial data warnings</p><ul className="mt-2 list-disc space-y-1 pl-5">{result.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div> : null}
              <p className="text-xs text-muted-foreground">Run {activeRun?.id} · scanned at {result.scanned_at}</p>
              <div className="overflow-x-auto rounded-lg border">
                <Table>
                  <TableHeader><TableRow><TableHead>Ticker</TableHead><TableHead className="text-right">Price</TableHead><TableHead className="text-right">Change</TableHead><TableHead className="text-right">RSI (14)</TableHead><TableHead className="text-right">P/E</TableHead><TableHead>Sector</TableHead><TableHead>Provenance</TableHead><TableHead>Matched conditions</TableHead></TableRow></TableHeader>
                  <TableBody>{result.results.length === 0 ? <TableRow><TableCell colSpan={8} className="py-10 text-center text-muted-foreground">{result.scanned_count === 0 ? "No tracked ticker is currently available in the scanner universe." : "No tracked ticker matched all persisted conditions."}</TableCell></TableRow> : result.results.map((item) => <TableRow key={item.ticker}>
                    <TableCell className="font-mono font-semibold">{item.ticker}</TableCell>
                    <TableCell className="text-right font-mono">{displaySnapshot(item.snapshot.price)}</TableCell>
                    <TableCell className={`text-right font-mono ${typeof item.snapshot.change_pct.value === "number" && item.snapshot.change_pct.value < 0 ? "text-destructive" : "text-emerald-500"}`}>{displaySnapshot(item.snapshot.change_pct)}</TableCell>
                    <TableCell className="text-right font-mono">{displaySnapshot(item.snapshot.rsi14)}</TableCell>
                    <TableCell className="text-right font-mono">{displaySnapshot(item.snapshot.pe_ratio)}</TableCell>
                    <TableCell>{displaySnapshot(item.snapshot.sector)}</TableCell>
                    <TableCell><Badge variant="outline">{displaySources(item)}</Badge></TableCell>
                    <TableCell><div className="flex min-w-48 flex-wrap gap-1">{item.matched_conditions.map((condition) => <Badge key={conditionKey(condition)} variant="secondary">{displayCondition(condition)}</Badge>)}</div></TableCell>
                  </TableRow>)}</TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </div> : null}
      </div>
    </Shell>
  );
}

export default function ScannerPage() {
  return (
    <Suspense fallback={<Shell><div className="p-6 text-sm text-muted-foreground">Loading scanner…</div></Shell>}>
      <ScannerContent />
    </Suspense>
  );
}
