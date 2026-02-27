/**
 * Core theme definitions — dark arcane palette matching the Timmy Time dashboard.
 *
 * All color tokens are defined here; constants/theme.ts re-exports them.
 */

export type ColorScheme = "light" | "dark";

export interface ThemeColorPalette {
  primary: string;
  background: string;
  surface: string;
  foreground: string;
  muted: string;
  border: string;
  success: string;
  warning: string;
  error: string;
}

/** Per-scheme flat color maps (used by NativeWind vars & ThemeProvider). */
export const SchemeColors: Record<ColorScheme, ThemeColorPalette> = {
  light: {
    primary: "#a855f7",
    background: "#080412",
    surface: "#110820",
    foreground: "#ede0ff",
    muted: "#6b4a8a",
    border: "#3b1a5c",
    success: "#00e87a",
    warning: "#ffb800",
    error: "#ff4455",
  },
  dark: {
    primary: "#a855f7",
    background: "#080412",
    surface: "#110820",
    foreground: "#ede0ff",
    muted: "#6b4a8a",
    border: "#3b1a5c",
    success: "#00e87a",
    warning: "#ffb800",
    error: "#ff4455",
  },
};

/** Alias used by useColors() hook — keyed by scheme. */
export const Colors = SchemeColors;

export const ThemeColors = SchemeColors;

export const Fonts = {
  regular: { fontFamily: "System", fontWeight: "400" as const },
  medium: { fontFamily: "System", fontWeight: "500" as const },
  bold: { fontFamily: "System", fontWeight: "700" as const },
};
