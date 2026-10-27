import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import SignInPage from "@/app/signin/page";

afterEach(cleanup);

describe("sign in", () => {
  it("blocks continuing until the terms box is ticked", async () => {
    render(<SignInPage />);
    expect(screen.queryByRole("link", { name: "Continue with Google" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Continue with Google" }));
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("links to home after consent and clears the error", async () => {
    render(<SignInPage />);
    await userEvent.click(screen.getByRole("button", { name: "Continue with Google" }));
    await userEvent.click(screen.getAllByRole("checkbox")[0]);
    expect(screen.getByRole("link", { name: "Continue with Google" }).getAttribute("href")).toMatch(/^\/home\/?$/);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("switches the page language", async () => {
    render(<SignInPage />);
    await userEvent.click(screen.getByRole("button", { name: "हिन्दी" }));
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("साइन इन");
    expect(screen.getByRole("button", { name: "हिन्दी" }).className).toContain("on");
  });
});
