"use client";

import { Shell } from "@/components/layout/shell";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";
import {
  TrendingUp,
  BarChart3,
  Zap,
  LineChart,
  Plus,
  ArrowUpRight,
} from "lucide-react";
import Link from "next/link";

export default function DashboardPage() {
  return (
    <Shell>
      <div className="p-6 space-y-6">
        {/* Quick Actions */}
        <div className="flex items-center gap-3 flex-wrap">
          <Link href="/quick-ask" className={buttonVariants()}>
            <Zap className="mr-2 h-4 w-4" />
            Quick Ask
          </Link>
          <Link href="/strategies/new" className={buttonVariants({ variant: "outline" })}>
            <Plus className="mr-2 h-4 w-4" />
            New Strategy
          </Link>
          <Link href="/backtest" className={buttonVariants({ variant: "outline" })}>
            <LineChart className="mr-2 h-4 w-4" />
            Run Backtest
          </Link>
          <Link href="/memory-lab" className={buttonVariants({ variant: "outline" })}>
            <BarChart3 className="mr-2 h-4 w-4" />
            Memory Lab
          </Link>
        </div>

        {/* Strategy Leaderboard */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Strategy Leaderboard</h2>
            <Link
              href="/strategies"
              className={buttonVariants({ variant: "ghost", size: "sm" })}
            >
              View All <ArrowUpRight className="h-3 w-3" />
            </Link>
          </div>

          <Card>
            <CardContent className="pt-8">
              <EmptyState
                title="No strategies yet"
                description="Create your first trading strategy to see performance metrics and leaderboard rankings."
                action={
                  <Link
                    href="/strategies/new"
                    className={buttonVariants()}
                  >
                    <Plus className="mr-2 h-4 w-4" />
                    Create Strategy
                  </Link>
                }
              />
            </CardContent>
          </Card>
        </div>

        {/* Equity Chart + Alerts */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <Card className="xl:col-span-2">
            <CardHeader>
              <CardTitle className="text-base">
                Portfolio Performance
              </CardTitle>
              <CardDescription>
                Equity curve overlay vs benchmark
              </CardDescription>
            </CardHeader>
            <CardContent className="h-80 flex items-center justify-center">
              <EmptyState
                icon={<TrendingUp className="h-12 w-12" />}
                title="Performance chart"
                description="Equity curves will appear here once strategies have trade data."
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Alerts & Pending</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex items-center justify-between text-sm p-3 rounded-lg bg-muted/50">
                  <span>Pending Approvals</span>
                  <Badge variant="outline">0</Badge>
                </div>
                <div className="flex items-center justify-between text-sm p-3 rounded-lg bg-muted/50">
                  <span>Triggered Alerts</span>
                  <Badge variant="outline">0</Badge>
                </div>
                <div className="flex items-center justify-between text-sm p-3 rounded-lg bg-muted/50">
                  <span>Reflections Ready</span>
                  <Badge variant="outline">0</Badge>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Market Brief */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Today&apos;s Market Brief
            </CardTitle>
            <CardDescription>
              Morning insight summary — updated at market open
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Market brief not yet available. Start the backend server and
              configure daily insights to see content here.
            </p>
          </CardContent>
        </Card>
      </div>
    </Shell>
  );
}
