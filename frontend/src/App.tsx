import ParamForm from "./components/ParamForm/ParamForm";
import { messages } from "./i18n";

export default function App() {
  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "2rem" }}>
      <h1>{messages.app_title}</h1>
      <ParamForm />
    </div>
  );
}
