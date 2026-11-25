import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        console: {
          bg: "#0B0E13",
          surface: "#11161F",
          elevated: "#161C27",
          border: "#222B3A",
          borderStrong: "#2E3A4E",
        },
        ink: {
          primary: "#E8E6DF",
          secondary: "#9AA4B2",
          muted: "#647082",
        },
        signal: {
          amber: "#F2A33A",
          amberDim: "rgba(242, 163, 58, 0.16)",
        },
        status: {
          verified: "#2EBD85",
          unverified: "#F2A33A",
          conflict: "#E5534B",
          insufficient: "#8C96A6",
        },
        doc: {
          paper: "#F7F5F0",
          sheet: "#FFFFFF",
          ink: "#1B2028",
          rule: "#DDD8CE",
        },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
        serif: ['"Source Serif 4"', "Georgia", "serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;
