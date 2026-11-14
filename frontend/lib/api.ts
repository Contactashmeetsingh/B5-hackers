// Tiny typed fetch helpers for the FastAPI backend (backend/app/main.py).
// Base URL comes from NEXT_PUBLIC_API_BASE (set it in frontend/.env.local).

import {
  MOCK,
  type ApiErrorDetail,
  type Biomarker,
  type GeneDetail,
  type GeneScore,
  type Health,
  type Meta,
  type Paper,
  type Ranking,
} from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

/** Thrown on any non-2xx. status 503 means a pipeline stage has not run yet; detail.run says which. */
export class ApiError extends Error {
  status: number;
  detail: ApiErrorDetail;

  constructor(status: number, detail: ApiErrorDetail) {
    super(detail.message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function get<T>(path: string): Promise<T> {
  // no-store: the backend re-reads its JSON files per request, so never serve a stale copy.
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    let detail: ApiErrorDetail = { message: `${res.status} ${res.statusText} on ${path}` };
    try {
      const body = await res.json();
      detail = typeof body?.detail === "string" ? { message: body.detail } : { ...detail, ...body?.detail };
    } catch {
      // body was not JSON; keep the status line
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const getHealth = () => get<Health>("/api/health");
export const getMeta = () => get<Meta>("/api/meta");
export const getBiomarker = () => get<Biomarker>("/api/biomarker");
export const getRankings = () => get<Ranking[]>("/api/rankings");
export const getGenes = () => get<GeneScore[]>("/api/genes");
export const getGene = (gene: string) => get<GeneDetail>(`/api/genes/${encodeURIComponent(gene)}`);
export const getPapers = () => get<Paper[]>("/api/papers");

/** True when a ranked row should carry the visible "mock data" tag. */
export const isMockRanking = (r: Ranking) => r.source === MOCK || r.mock_inputs.length > 0;

/** Link target for a ranked row, or null for mock trials (url ""), which must render as plain text. */
export const trialHref = (r: Ranking): string | null => (r.url.trim() ? r.url : null);

/** True when anything in the evidence drawer for this gene is mocked. */
export const isMockGene = (g: GeneDetail) => g.mock_inputs.length > 0;
