import { useState } from "react";
import { messages } from "../../i18n";

const STYLES = ["modern", "neoclassic", "european", "nordic"];
const MATERIALS = ["glass", "stone", "brick", "wood"];

export default function ParamForm() {
  const [style, setStyle] = useState("modern");
  const [floors, setFloors] = useState(3);
  const [widthM, setWidthM] = useState(10);
  const [depthM, setDepthM] = useState(8);
  const [material, setMaterial] = useState("glass");

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    console.log({ style, floors, widthM, depthM, material });
  };

  return (
    <form onSubmit={onSubmit} style={{ display: "grid", gap: "1rem" }}>
      <label>{messages.style}
        <select value={style} onChange={(e) => setStyle(e.target.value)}>
          {STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
      <label>{messages.floors}
        <input type="number" min={1} max={6} value={floors} onChange={(e) => setFloors(+e.target.value)} />
      </label>
      <label>{messages.width}
        <input type="number" min={6} max={20} value={widthM} onChange={(e) => setWidthM(+e.target.value)} />
      </label>
      <label>{messages.depth}
        <input type="number" min={5} max={18} value={depthM} onChange={(e) => setDepthM(+e.target.value)} />
      </label>
      <label>{messages.material}
        <select value={material} onChange={(e) => setMaterial(e.target.value)}>
          {MATERIALS.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </label>
      <button type="submit">{messages.generate}</button>
    </form>
  );
}
