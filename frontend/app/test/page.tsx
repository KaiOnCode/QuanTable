"use client";

import { useState } from "react";
import { Shell } from "@/components/layout/shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

export default function TestPage() {
  const [status, setStatus] = useState<string>("not tried");
  const [result, setResult] = useState<string>("");

  // Test 1: Pure React state
  const testState = () => {
    setStatus("button clicked!");
    setResult("React state works. Button handler is firing.");
  };

  // Test 2: Simple fetch to backend
  const testFetch = async () => {
    setStatus("fetching...");
    try {
      const res = await fetch("http://localhost:8000/api/health");
      const data = await res.json();
      setStatus("fetch success");
      setResult(JSON.stringify(data, null, 2));
    } catch (error: unknown) {
      setStatus("fetch failed");
      setResult(getErrorMessage(error));
    }
  };

  // Test 3: SSE streaming
  const testSSE = () => {
    setStatus("sse connecting...");
    setResult("");

    fetch("http://localhost:8000/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticker: "AAPL",
        mode: "fast",
        active_agents: ["market_analyst", "news_analyst", "pm"],
      }),
    })
      .then(async (response) => {
        setStatus(`response: ${response.status}`);
        if (!response.ok) {
          setResult(`HTTP ${response.status}: ${await response.text()}`);
          return;
        }

        const reader = response.body?.getReader();
        if (!reader) {
          setResult("No response body");
          return;
        }

        const decoder = new TextDecoder();
        let events = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const text = decoder.decode(value, { stream: true });
          events += text;
          setResult(events.slice(-500));
        }
        setStatus("stream complete");
      })
      .catch((error: unknown) => {
        setStatus("sse error");
        setResult(getErrorMessage(error));
      });
  };

  return (
    <Shell>
      <div className="p-6 space-y-6">
        <h1 className="text-xl font-bold">Connectivity Test</h1>

        <Card>
          <CardHeader>
            <CardTitle>Status: {status}</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-xs bg-muted p-4 rounded whitespace-pre-wrap max-h-96 overflow-auto">
              {result || "no result yet"}
            </pre>
          </CardContent>
        </Card>

        <div className="flex gap-3 flex-wrap">
          <Button onClick={testState}>1. Test React State</Button>
          <Button onClick={testFetch}>2. Test Health Fetch</Button>
          <Button onClick={testSSE}>3. Test SSE Stream</Button>
        </div>
      </div>
    </Shell>
  );
}
