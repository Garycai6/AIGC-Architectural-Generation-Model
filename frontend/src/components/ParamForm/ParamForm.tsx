import { useState } from "react";
import { generateScheme } from "../../api/client";
import { useLang } from "../../contexts";

const STYLES = ["modern", "neoclassic", "european", "nordic"];
const MATERIALS = ["glass", "stone", "brick", "wood"];

interface ResultImages {
  facade?: string;
  floorplan?: string;
}

export default function ParamForm() {
  const { lang, messages } = useLang();
  const [style, setStyle] = useState("modern");
  const [floors, setFloors] = useState(3);
  const [widthM, setWidthM] = useState(10);
  const [depthM, setDepthM] = useState(8);
  const [material, setMaterial] = useState("glass");
  const [roof, setRoof] = useState("flat");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [images, setImages] = useState<ResultImages>({});

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await generateScheme(
        {
          style,
          floors,
          width_m: widthM,
          depth_m: depthM,
          materials: [material],
          roof,
          environment: "suburb",
        },
        lang
      );
      const facade = res.images.find((u) => u.includes("facade"));
      const floorplan = res.images.find((u) => u.includes("floorplan"));
      setImages({ facade, floorplan });
    } catch (err) {
      setError(messages.error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
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
        <label>{messages.roof}
          <select value={roof} onChange={(e) => setRoof(e.target.value)}>
            <option value="flat">{messages.roof_flat}</option>
            <option value="pitched">{messages.roof_pitched}</option>
            <option value="hipped">{messages.roof_hipped}</option>
          </select>
        </label>
        <button type="submit" disabled={loading}>
          {loading ? messages.generating : messages.generate}
        </button>
      </form>
      {error && <p style={{ color: "red" }}>{error}</p>}
      {(images.facade || images.floorplan) && (
        <div style={{ display: "flex", gap: "1rem", marginTop: "1rem" }}>
          {images.facade && (
            <figure>
              <figcaption>{messages.facade_label}</figcaption>
              <img src={images.facade} alt={messages.facade_label} style={{ width: 320 }} />
            </figure>
          )}
          {images.floorplan && (
            <figure>
              <figcaption>{messages.floorplan_label}</figcaption>
              <img src={images.floorplan} alt={messages.floorplan_label} style={{ width: 240 }} />
            </figure>
          )}
        </div>
      )}
    </>
  );
}
