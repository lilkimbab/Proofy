"use client";

import { useEffect } from "react";

const STORAGE_KEY = "proofy-theme";

export function ThemeController() {
  useEffect(() => {
    const savedTheme = window.localStorage.getItem(STORAGE_KEY) ?? "chalk-amber";
    document.documentElement.dataset.theme = savedTheme;
  }, []);

  return null;
}

export function persistTheme(themeId: string) {
  document.documentElement.dataset.theme = themeId;
  window.localStorage.setItem(STORAGE_KEY, themeId);
}
