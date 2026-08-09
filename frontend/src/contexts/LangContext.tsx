// frontend/src/contexts/LangContext.tsx
import { createContext, useContext, useState, type ReactNode } from "react";
import en from "../i18n/en.json";
import zh from "../i18n/zh.json";

export type Lang = "zh" | "en";
export type LangMessages = typeof zh;

const STORAGE_KEY = "archgen_lang";

interface LangContextValue {
  lang: Lang;
  setLang: (l: Lang) => void;
  messages: LangMessages;
}

const LangContext = createContext<LangContextValue | null>(null);

function initialLang(): Lang {
  const stored = typeof window !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null;
  return stored === "en" ? "en" : "zh";
}

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  const setLang = (l: Lang) => {
    setLangState(l);
    localStorage.setItem(STORAGE_KEY, l);
  };

  return (
    <LangContext.Provider value={{ lang, setLang, messages: lang === "zh" ? zh : en }}>
      {children}
    </LangContext.Provider>
  );
}

export function useLang(): LangContextValue {
  const ctx = useContext(LangContext);
  if (!ctx) throw new Error("useLang must be used within LangProvider");
  return ctx;
}
