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

export class QuotaExhaustedError extends Error {}

const VISITOR_ID_KEY = "archgen_visitor_id";

export function getVisitorId(): string {
  let id = localStorage.getItem(VISITOR_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(VISITOR_ID_KEY, id);
  }
  return id;
}

export interface GenerateResponse {
  scheme_id: string;
  description: string;
  images: string[];
  remaining_quota: number;
}

export async function generateScheme(params: BuildingParams, lang = "zh"): Promise<GenerateResponse> {
  const resp = await fetch("/api/v1/generate", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Visitor-Id": getVisitorId(),
    },
    body: JSON.stringify({ params, lang }),
  });
  if (resp.status === 429) throw new QuotaExhaustedError();
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}
