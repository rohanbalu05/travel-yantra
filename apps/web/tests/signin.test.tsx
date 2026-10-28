import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import SignInPage from "@/app/signin/page";
import { LangProvider } from "@/lib/i18n";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
const store = new Map<string, string>();
vi.stubGlobal("localStorage", { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k) });

afterEach(() => {
  cleanup();
  store.clear();
  push.mockClear();
});

describe("sign in", () => {
  it("blocks continuing until the terms box is ticked", async () => {
    render(<LangProvider><SignInPage /></LangProvider>);
    expect(screen.queryByRole("link", { name: "Continue with Google" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Continue with Google" }));
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("signs in after consent (demo account without Firebase) and goes home", async () => {
    render(<LangProvider><SignInPage /></LangProvider>);
    await userEvent.click(screen.getByRole("button", { name: "Continue with Google" }));
    await userEvent.click(screen.getAllByRole("checkbox")[0]);
    await userEvent.click(screen.getByRole("button", { name: "Continue with Google" }));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(push).toHaveBeenCalledWith("/home/");
    expect(JSON.parse(store.get("ty.account")!).user).toMatchObject({ demo: true, name: "Arjun Rao (sample)" });
  });

  it("switches the page language", async () => {
    render(<LangProvider><SignInPage /></LangProvider>);
    await userEvent.click(screen.getByRole("button", { name: "हिन्दी" }));
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("साइन इन");
    expect(screen.getByRole("button", { name: "हिन्दी" }).className).toContain("on");
  });
});
