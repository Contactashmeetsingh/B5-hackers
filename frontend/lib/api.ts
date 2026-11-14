import type {
  ApiErrorDetail,
  GeneCandidate,
  GeneDetail,
  Health,
  Meta,
  Paper,
  Profile,
  ResearchData,
  TrialMatch,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ?? "";
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: ApiErrorDetail,
  ) {
    super(detail.message);
    this.name = "ApiError";
  }
}
async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) {
    let detail: ApiErrorDetail = {
      message: `Unable to load data (${response.status}).`,
    };
    try {
      const body = await response.json();
      detail =
        typeof body.detail === "string"
          ? { message: body.detail }
          : { ...detail, ...body.detail };
    } catch {
      /* Keep the readable fallback. */
    }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}
export const getProfile = () => get<Profile>("/api/profile");
export const getTrialMatches = () => get<TrialMatch[]>("/api/trial-matches");
export const getGenes = () => get<GeneCandidate[]>("/api/genes");
export const getGene = (gene: string) =>
  get<GeneDetail>(`/api/genes/${encodeURIComponent(gene)}`);
export const getPapers = () => get<Paper[]>("/api/papers");
export const getMeta = () => get<Meta>("/api/meta");
export const getHealth = () => get<Health>("/api/health");

export async function loadResearch(): Promise<{
  data: ResearchData;
  source: string;
  notices: string[];
}> {
  if (!API_BASE) {
    const response = await fetch("/research-data.json", {
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok)
      throw new Error(
        "The saved research data could not be loaded. Please retry.",
      );
    return {
      data: await response.json(),
      source: "Repository snapshot",
      notices: [],
    };
  }
  // Independent stage requests: one unfinished stage must not hide the other results.
  const profile = await getProfile();
  const results = await Promise.allSettled([
    getTrialMatches(),
    getPapers(),
    getGenes(),
    getMeta(),
    getHealth(),
  ] as const);
  const [trials, papers, genes, meta, health] = results;
  const names = [
    "Trial matches",
    "Papers",
    "Candidate genes",
    "Data provenance",
    "Stage status",
  ];
  const notices = results.flatMap((result, i) =>
    result.status === "rejected"
      ? [
          `${names[i]} unavailable. ${result.reason instanceof Error ? result.reason.message : "Please retry."}`,
        ]
      : [],
  );
  const candidateRows = genes.status === "fulfilled" ? genes.value : [];
  const details = await Promise.allSettled(
    candidateRows.map((gene) => getGene(gene.gene)),
  );
  if (details.some((result) => result.status === "rejected"))
    notices.push("Some genomic model details are unavailable.");
  return {
    source: "Connected research API",
    notices,
    data: {
      profile,
      trials: trials.status === "fulfilled" ? trials.value : [],
      papers: papers.status === "fulfilled" ? papers.value : [],
      genes: candidateRows,
      meta:
        meta.status === "fulfilled"
          ? meta.value
          : {
              has_mock_data: false,
              mock_inputs: [],
              disclaimer: "Research prototype. Not medical advice.",
            },
      health:
        health.status === "fulfilled"
          ? health.value
          : { status: "unavailable", files: {} },
      contexts: details.flatMap((result) =>
        result.status === "fulfilled" && result.value.genomic_context
          ? [result.value.genomic_context]
          : [],
      ),
    },
  };
}
