export interface BuildingParams {
  style: string;
  floors: number;
  width_m: number;
  depth_m: number;
  materials: string[];
  roof: string;
  environment: string;
  view_angle?: string;
  color_scheme?: string;
}

export interface GenerateResponse {
  scheme_id: string;
  description: string;
  images: string[];
}

export async function generateScheme(params: BuildingParams, lang = "zh"): Promise<GenerateResponse> {
  const resp = await fetch("/api/v1/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ params, lang }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}
