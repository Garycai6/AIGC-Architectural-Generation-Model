import ParamForm from "./components/ParamForm/ParamForm";

export default function App() {
  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "2rem" }}>
      <h1>ArchGen 建筑方案生成</h1>
      <ParamForm />
    </div>
  );
}
