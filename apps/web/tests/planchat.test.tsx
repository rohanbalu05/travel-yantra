import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PlanChanged } from "@/components/chat/ChatPanel";
import { GOA_ITINERARY } from "@/lib/mockPlan";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
// TY5's panel faked: one button that reports a finished chat edit.
vi.mock("@/components/chat/ChatPanel", () => ({
  default: ({ onPlanChanged }: { onPlanChanged: (e: PlanChanged) => void }) => (
    <button type="button" onClick={() => onPlanChanged({ plan_id: "p2", itinerary: { ...GOA_ITINERARY, warnings: ["edited in chat"] } })}>edit</button>
  ),
}));

const session = new Map<string, string>();
vi.stubGlobal("sessionStorage", { getItem: (k: string) => session.get(k) ?? null, setItem: (k: string, v: string) => void session.set(k, v), removeItem: (k: string) => void session.delete(k) });

afterEach(() => {
  cleanup();
  session.clear();
  push.mockClear();
});

describe("chat on the plan pages", () => {
  it("replaces the stored plan in place after a chat edit", async () => {
    const { PlanChat } = await import("@/components/PlanChat");
    render(<PlanChat planId="p2" shareToken="s2" />);
    await userEvent.click(screen.getByRole("button", { name: "edit" }));
    const saved = JSON.parse(session.get("ty.plan.result")!);
    expect(saved).toMatchObject({ plan_id: "p2", share_token: "s2" });
    expect(saved.itinerary.warnings).toEqual(["edited in chat"]);
    expect(push).not.toHaveBeenCalled();
  });

  it("opens the Itinerary when the chat makes a new plan from Plan start", async () => {
    const { PlanChat } = await import("@/components/PlanChat");
    render(<PlanChat planId={null} openOnNew />);
    await userEvent.click(screen.getByRole("button", { name: "edit" }));
    expect(push).toHaveBeenCalledWith("/plan/itinerary/");
  });
});
