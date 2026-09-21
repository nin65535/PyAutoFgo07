import type { ScenarioSummary } from "./scenario";

export type ScenarioDetail = ScenarioSummary & { content: unknown };

export type ScenarioApi = {
  list(): Promise<ScenarioSummary[]>;
  get(id: string): Promise<ScenarioDetail>;
};

type Fetch = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

export function createScenarioApi(fetcher: Fetch = fetch): ScenarioApi {
  return {
    async list() {
      const response = await fetcher("/api/scenarios");
      const body = await readResponse(response);
      return (body as { data: { scenarios: ScenarioSummary[] } }).data
        .scenarios;
    },
    async get(id) {
      const response = await fetcher(
        `/api/scenarios/${encodeURIComponent(id)}`,
      );
      const body = await readResponse(response);
      return (body as { data: ScenarioDetail }).data;
    },
  };
}

async function readResponse(response: Response): Promise<unknown> {
  const body = (await response.json()) as {
    error?: { message?: string };
  };
  if (!response.ok)
    throw new Error(body.error?.message ?? "操作手順を読み込めませんでした");
  return body;
}
