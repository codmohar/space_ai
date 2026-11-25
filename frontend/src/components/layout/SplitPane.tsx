import { type ReactNode, useRef } from "react";

interface SplitPaneProps {
  left: ReactNode;
  right: ReactNode;
  ratio: number;
  onRatioChange: (ratio: number) => void;
}

export function SplitPane({ left, right, ratio, onRatioChange }: SplitPaneProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  const startDrag = () => {
    const onMove = (ev: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      if (rect.width <= 0) return;
      const pct = ((ev.clientX - rect.left) / rect.width) * 100;
      onRatioChange(pct);
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  return (
    <div ref={containerRef} className="flex h-full w-full overflow-hidden">
      <div
        style={{ width: `${ratio}%` }}
        className="h-full min-w-[300px] overflow-hidden"
      >
        {left}
      </div>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize answer and PDF citation viewer"
        tabIndex={0}
        onMouseDown={startDrag}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") onRatioChange(ratio - 3);
          if (e.key === "ArrowRight") onRatioChange(ratio + 3);
        }}
        className="w-1.5 shrink-0 cursor-col-resize border-x border-console-border bg-console-surface transition-colors hover:bg-signal-amber/40 focus:bg-signal-amber/60 focus:outline-none"
      />
      <div
        style={{ width: `${100 - ratio}%` }}
        className="h-full min-w-[320px] flex-1 overflow-hidden"
      >
        {right}
      </div>
    </div>
  );
}
