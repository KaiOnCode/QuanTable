"use client";

import { useParams } from "next/navigation";
import { Shell } from "@/components/layout/shell";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { EmptyState } from "@/components/shared/empty-state";
import { ActionBadge, DirectionBadge } from "@/components/shared/badges";
import { formatDateTime } from "@/lib/utils";
import {
  MessageSquare,
  Send,
  User,
  Bot,
  TrendingUp,
  Shield,
} from "lucide-react";

const MOCK_CONVERSATION = {
  id: "conv-1",
  title: "AAPL Analysis — May 28, 2026",
  created_at: "2026-05-28T09:30:00Z",
  tags: ["AAPL", "earnings", "tech"],
  messages: [
    {
      id: "msg-1",
      role: "user" as const,
      content: "Analyze AAPL with deep debate mode",
      timestamp: "2026-05-28T09:30:00Z",
    },
    {
      id: "msg-2",
      role: "assistant" as const,
      content: "Starting deep analysis of AAPL with all 15 agents...",
      timestamp: "2026-05-28T09:30:05Z",
      analysis_result: {
        action: "BUY",
        direction: "Bullish",
        confidence: 0.78,
        timeframe: "1-4w",
        report: "AAPL shows strong bullish signals across multiple dimensions:\n\n" +
          "**Technical**: RSI(14)=32 oversold region, MACD golden cross confirmed.\n" +
          "**Fundamentals**: Q2 earnings beat estimates ($1.52 vs $1.50), revenue +5% YoY.\n" +
          "**News Sentiment**: Positive (+0.65), driven by iPhone 18 cycle upgrade expectations.\n" +
          "**Debate**: Bull case (AI-powered upgrade cycle) won over Bear case (valuation concerns).\n\n" +
          "**Decision**: BUY with 78% confidence. Entry at current levels with 5% trailing stop.",
      },
      debate_records: [
        {
          id: "d1",
          debate_type: "investment" as const,
          round_num: 1,
          speaker: "bull_researcher",
          role: "bull",
          claim: "AI-powered iPhone upgrade cycle will drive 10%+ revenue growth in FY2027",
          evidence: ["iPhone installed base at all-time high", "Apple Intelligence features require newer hardware"],
          rebuttal_to: null,
        },
        {
          id: "d2",
          debate_type: "investment" as const,
          round_num: 1,
          speaker: "bear_researcher",
          role: "bear",
          claim: "Valuation stretched at 30x PE. Competition from Android AI features intensifying.",
          evidence: ["PE ratio above 5-year average", "Samsung and Google launching competing AI features"],
          rebuttal_to: "d1",
        },
      ],
    },
    {
      id: "msg-3",
      role: "user" as const,
      content: "What about the risk of China exposure?",
      timestamp: "2026-05-28T09:35:00Z",
    },
    {
      id: "msg-4",
      role: "assistant" as const,
      content: "China risk analysis shows manageable exposure: Apple's China revenue accounts for 18% of total (down from 20% last year). Diversification into India and Vietnam manufacturing reduces tariff risk. However, a 10% decline in China sales would impact EPS by approximately $0.15.",
      timestamp: "2026-05-28T09:35:30Z",
    },
  ],
};

export default function ConversationDetailPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const conversation = MOCK_CONVERSATION;

  return (
    <Shell>
      <div className="p-6 max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <MessageSquare className="h-5 w-5" />
              {conversation.title}
            </h2>
            <div className="flex items-center gap-2 mt-1">
              {conversation.tags.map((t) => (
                <Badge key={t} variant="outline" className="text-xs">
                  {t}
                </Badge>
              ))}
              <span className="text-xs text-muted-foreground">
                Created {formatDateTime(conversation.created_at)}
              </span>
            </div>
          </div>
          <Button variant="outline">Export PDF</Button>
        </div>

        {/* Messages */}
        <ScrollArea className="h-[calc(100vh-250px)]">
          <div className="space-y-4 pr-4">
            {conversation.messages.map((msg) => (
              <div key={msg.id}>
                {msg.role === "user" ? (
                  <div className="flex items-start gap-3">
                    <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center shrink-0">
                      <User className="h-4 w-4" />
                    </div>
                    <div className="flex-1">
                      <div className="bg-muted/50 rounded-lg p-3 max-w-2xl">
                        <p className="text-sm">{msg.content}</p>
                      </div>
                      <span className="text-xs text-muted-foreground mt-1 block">
                        {formatDateTime(msg.timestamp)}
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="flex items-start gap-3">
                      <div className="h-8 w-8 rounded-full bg-primary flex items-center justify-center shrink-0">
                        <Bot className="h-4 w-4 text-primary-foreground" />
                      </div>
                      <div className="flex-1">
                        <div className="bg-muted/30 rounded-lg p-3 max-w-3xl">
                          <p className="text-sm whitespace-pre-wrap">
                            {msg.content}
                          </p>
                        </div>
                        <span className="text-xs text-muted-foreground mt-1 block">
                          {formatDateTime(msg.timestamp)}
                        </span>
                      </div>
                    </div>

                    {/* Analysis Result Card */}
                    {msg.analysis_result && (
                      <div className="ml-11">
                        <Card className="border-primary/20">
                          <CardHeader className="pb-2">
                            <CardTitle className="text-sm flex items-center gap-2">
                              Analysis Result
                              <ActionBadge action={msg.analysis_result.action} />
                              <DirectionBadge direction={msg.analysis_result.direction} />
                              <Badge variant="outline" className="text-xs font-mono">
                                {(msg.analysis_result.confidence * 100).toFixed(0)}% confidence
                              </Badge>
                            </CardTitle>
                          </CardHeader>
                          <CardContent>
                            <div className="text-sm whitespace-pre-wrap text-muted-foreground">
                              {msg.analysis_result.report}
                            </div>
                          </CardContent>
                        </Card>
                      </div>
                    )}

                    {/* Debate Records */}
                    {msg.debate_records && msg.debate_records.length > 0 && (
                      <div className="ml-11 space-y-2">
                        <p className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                          <TrendingUp className="h-3 w-3" />
                          Debate Records
                        </p>
                        {msg.debate_records.map((d) => (
                          <div
                            key={d.id}
                            className={`p-3 rounded-lg text-xs border ${
                              d.role === "bull"
                                ? "bg-green-500/5 border-green-500/20"
                                : "bg-red-500/5 border-red-500/20"
                            }`}
                          >
                            <div className="flex items-center gap-2 mb-1">
                              <Badge
                                variant="outline"
                                className={
                                  d.role === "bull"
                                    ? "text-green-500 border-green-500/20"
                                    : "text-red-500 border-red-500/20"
                                }
                              >
                                {d.role.toUpperCase()} · Round {d.round_num}
                              </Badge>
                              {d.rebuttal_to && (
                                <span className="text-muted-foreground">
                                  Rebuttal to previous
                                </span>
                              )}
                            </div>
                            <p>{d.claim}</p>
                            {d.evidence.length > 0 && (
                              <div className="mt-1 text-muted-foreground">
                                Evidence: {d.evidence.join("; ")}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </ScrollArea>

        <Separator />

        {/* Follow-up Input */}
        <div className="flex gap-3">
          <Input
            placeholder="Ask a follow-up question..."
            className="h-12 flex-1"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                // Will wire up to API later
              }
            }}
          />
          <Button className="h-12 px-6">
            <Send className="mr-2 h-4 w-4" />
            Send
          </Button>
        </div>
      </div>
    </Shell>
  );
}
