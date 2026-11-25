/**
 * MISSIONWISE AI — Instrument-Grade Design Tokens
 * Palette: Deep slate mission-control console (#0B0E13) + single amber signal (#F2A33A)
 * Document surface: Light archival paper theme (#F7F5F0) for primary PDF inspection.
 */

export const designTokens = {
  colors: {
    console: {
      base: "#0B0E13",
      surface: "#11161F",
      elevated: "#161C27",
      hover: "#1C2330",
      rule: "#222B3A",
      ruleStrong: "#2E3A4E",
    },
    text: {
      primary: "#E8E6DF",
      secondary: "#9AA4B2",
      muted: "#647082",
    },
    accent: {
      amber: "#F2A33A",
      amberFill: "rgba(242, 163, 58, 0.16)",
      amberHighlight: "rgba(242, 163, 58, 0.28)",
    },
    status: {
      verified: "#2EBD85",
      verifiedBg: "rgba(46, 189, 133, 0.12)",
      unverified: "#F2A33A",
      unverifiedBg: "rgba(242, 163, 58, 0.12)",
      conflict: "#E5534B",
      conflictBg: "rgba(229, 83, 75, 0.14)",
      insufficient: "#8C96A6",
    },
    document: {
      paper: "#F7F5F0",
      sheet: "#FFFFFF",
      ink: "#1B2028",
      mutedInk: "#5A6270",
      rule: "#DDD8CE",
    },
  },
  typography: {
    ui: '"IBM Plex Sans", system-ui, sans-serif',
    mono: '"IBM Plex Mono", ui-monospace, monospace',
    serif: '"Source Serif 4", Georgia, serif',
  },
  confidenceStyles: {
    Strong: {
      color: "#2EBD85",
      bg: "rgba(46, 189, 133, 0.12)",
      border: "rgba(46, 189, 133, 0.4)",
      label: "STRONG",
    },
    Partial: {
      color: "#F2A33A",
      bg: "rgba(242, 163, 58, 0.12)",
      border: "rgba(242, 163, 58, 0.4)",
      label: "PARTIAL",
    },
    Conflicting: {
      color: "#E5534B",
      bg: "rgba(229, 83, 75, 0.14)",
      border: "rgba(229, 83, 75, 0.45)",
      label: "CONFLICTING",
    },
    Insufficient: {
      color: "#8C96A6",
      bg: "rgba(140, 150, 166, 0.12)",
      border: "rgba(140, 150, 166, 0.35)",
      label: "INSUFFICIENT",
    },
    None: {
      color: "#647082",
      bg: "rgba(100, 112, 130, 0.12)",
      border: "rgba(100, 112, 130, 0.3)",
      label: "NONE",
    },
  },
  evidenceClassificationLabels: {
    explicitly_stated: {
      label: "Explicitly Stated",
      tone: "border-status-verified/40 text-status-verified bg-status-verified/10",
    },
    official_root_cause: {
      label: "Official Root Cause",
      tone: "border-signal-amber/50 text-signal-amber bg-signal-amber/10",
    },
    official_contributing_factor: {
      label: "Contributing Factor",
      tone: "border-signal-amber/35 text-ink-primary bg-console-elevated",
    },
    system_inference: {
      label: "System Inference",
      tone: "border-dashed border-ink-secondary/50 text-ink-secondary bg-transparent",
    },
    unknown: {
      label: "Unknown / Undetermined",
      tone: "border-status-insufficient/40 text-status-insufficient bg-console-elevated",
    },
  },
} as const;

export type ConfidenceCategory = keyof typeof designTokens.confidenceStyles;
export type EvidenceClassification =
  keyof typeof designTokens.evidenceClassificationLabels;
