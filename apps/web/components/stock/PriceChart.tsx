"use client";

import { useEffect, useRef } from "react";
import { createChart, AreaSeries, CandlestickSeries } from "lightweight-charts";
import type { PriceBar } from "@/lib/api";

interface Props {
  bars: PriceBar[];
  symbol: string;
  chartType?: "area" | "candlestick";
}

export function PriceChart({ bars, symbol, chartType = "area" }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);

  useEffect(() => {
    if (!containerRef.current || bars.length === 0) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "transparent" },
        textColor: "#9ca3af",
        fontFamily: "ui-monospace, monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#1f2937" },
        horzLines: { color: "#1f2937" },
      },
      crosshair: {
        vertLine: { color: "#4b5563", width: 1 },
        horzLine: { color: "#4b5563", width: 1 },
      },
      rightPriceScale: {
        borderColor: "#1f2937",
      },
      timeScale: {
        borderColor: "#1f2937",
        timeVisible: false,
      },
      handleScroll: true,
      handleScale: true,
    });

    chartRef.current = chart;

    if (chartType === "candlestick") {
      const series = chart.addSeries(CandlestickSeries, {
        upColor: "#10b981",
        downColor: "#ef4444",
        borderUpColor: "#10b981",
        borderDownColor: "#ef4444",
        wickUpColor: "#10b981",
        wickDownColor: "#ef4444",
      });
      const data = bars
        .filter((b) => b.open != null && b.high != null && b.low != null)
        .map((b) => ({
          time: b.session_date as `${number}-${number}-${number}`,
          open: b.open!,
          high: b.high!,
          low: b.low!,
          close: b.close,
        }));
      series.setData(data);
    } else {
      const series = chart.addSeries(AreaSeries, {
        lineColor: "#3b82f6",
        topColor: "rgba(59,130,246,0.25)",
        bottomColor: "rgba(59,130,246,0.02)",
        lineWidth: 2,
        priceLineVisible: true,
        lastValueVisible: true,
        crosshairMarkerVisible: true,
        crosshairMarkerRadius: 4,
      });
      const data = bars.map((b) => ({
        time: b.session_date as `${number}-${number}-${number}`,
        value: b.adj_close ?? b.close,
      }));
      series.setData(data);
    }

    chart.timeScale().fitContent();

    function handleResize() {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    }
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [bars, chartType, symbol]);

  if (bars.length === 0) {
    return (
      <div className="h-[260px] flex items-center justify-center text-xs text-gray-600 border border-gray-800 rounded-lg">
        Tidak ada data harga tersimpan — klik Refresh Data untuk mengambil dari provider.
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="w-full h-[260px] rounded-lg overflow-hidden border border-gray-800/60"
    />
  );
}
