import { afterEach, describe, expect, it, vi } from "vitest";
import { getQuizzes } from "@/services/modules/quizzes";
import { getInfoCards } from "@/services/modules/info_cards";
import { getKnowledgeDocuments } from "@/services/modules/knowledge";

// The list endpoints read `tag` as a repeated query parameter (any-of). The view specs mock
// these modules, so this pins the step they skip: how the shared client puts an array on
// the wire. A comma-joined "family,medication" would reach the backend as one tag that
// matches nothing.
function stubFetch() {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ items: [], total: 0 }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function requestedUrl(fetchMock: ReturnType<typeof vi.fn>): URL {
  const request = fetchMock.mock.calls[0][0] as Request;
  return new URL(request.url, "http://localhost");
}

describe("tag filters on the wire", () => {
  afterEach(() => vi.unstubAllGlobals());

  it.each([
    ["quizzes", () => getQuizzes({ tag: ["family", "medication"] })],
    ["info cards", () => getInfoCards({ tag: ["family", "medication"] })],
    ["documents", () => getKnowledgeDocuments({ tag: ["family", "medication"] })],
  ])("%s send one tag parameter per selected tag", async (_name, call) => {
    const fetchMock = stubFetch();

    await call();

    expect(requestedUrl(fetchMock).searchParams.getAll("tag")).toEqual(["family", "medication"]);
  });
});
