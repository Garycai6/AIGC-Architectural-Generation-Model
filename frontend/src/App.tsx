import ParamForm from "./components/ParamForm/ParamForm";
import { LangProvider, useLang } from "./contexts";

function ToggleLang() {
  const { lang, setLang } = useLang();
  return (
    <button
      onClick={() => setLang(lang === "zh" ? "en" : "zh")}
      style={{ marginLeft: "auto", cursor: "pointer" }}
    >
      {lang === "zh" ? "EN" : "中文"}
    </button>
  );
}

function AppInner() {
  const { messages } = useLang();
  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "2rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
        <h1>{messages.app_title}</h1>
        <ToggleLang />
      </div>
      <ParamForm />
    </div>
  );
}

export default function App() {
  return (
    <LangProvider>
      <AppInner />
    </LangProvider>
  );
}
