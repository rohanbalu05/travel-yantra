import { expect, test, type Page } from "@playwright/test";

// The demo path (card #44): Home, plan Goa, revise, book, Katha, ask the guide, rate,
// language and settings, on the mock API that replays the Goa family sample.

async function noSidewaysScroll(page: Page) {
  const [scroll, width] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(scroll).toBeLessThanOrEqual(width);
}

test("plan Goa from Home to the itinerary, revise a day and rate it", async ({ page }) => {
  await page.goto("/home/");
  await page.getByLabel("Where do you want to go?").fill("Bengaluru to Goa, 11 to 14 Dec, with my parents and sister.");
  await page.getByRole("button", { name: "Plan my trip" }).click();

  await expect(page).toHaveURL(/\/plan\/thinking\/$/);
  await expect(page.getByText("Your plan is ready")).toBeVisible({ timeout: 20_000 });
  await noSidewaysScroll(page);
  // Refresh on the Plan step shows the same plan at once; it never plans again.
  await page.reload();
  await expect(page.getByText("Your plan is ready")).toBeVisible({ timeout: 2_000 });
  await expect(page.getByText("Still planning")).toHaveCount(0);
  await page.getByRole("link", { name: /See the 2 ways to go/ }).click();

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("2 ways to Goa");
  await expect(page.getByText("Our pick: rail")).toBeVisible();
  await page.getByRole("button", { name: "See the day-by-day plan" }).click();

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Goa with family");
  await expect(page.locator(".smap-pin")).toHaveCount(2);
  await expect(page.locator("#day-panel .mk-stop")).toHaveCount(2);
  await noSidewaysScroll(page);

  await page.getByRole("button", { name: "Make Fri lighter" }).click();
  await expect(page.getByText(/^Done: Dropped /)).toBeVisible(); // TY1's own line for what changed
  await expect(page.locator("#day-panel .mk-stop")).toHaveCount(1);

  await page.getByRole("radio", { name: "4: Good" }).click();
  await page.getByRole("complementary").getByRole("button", { name: "Send" }).click(); // the chat panel has its own Send
  await expect(page.getByText("Thank you")).toBeVisible();
});

test("book: train card, PNR timeline and stays", async ({ page }) => {
  await page.goto("/plan/start/?mode=form");
  await page.getByLabel("From").fill("Bengaluru");
  await page.getByLabel("To", { exact: true }).fill("Goa");
  await page.getByLabel("First day").fill("2026-12-11");
  await page.getByLabel("Last day").fill("2026-12-14");
  await page.getByRole("button", { name: "Plan my trip" }).last().click();
  await expect(page.getByText("Your plan is ready")).toBeVisible({ timeout: 20_000 });

  await page.goto("/book/");
  await expect(page.getByText(/Ready for IRCTC: 90001/)).toBeVisible();
  await expect(page.getByRole("cell", { name: "Arjun Rao" })).toBeVisible();
  await page.getByRole("button", { name: "4521690144" }).click();
  await expect(page.locator(".timeline li").first()).toContainText("WL 7");
  await expect(page.getByText("Sample Heritage Inn")).toBeVisible();
  await noSidewaysScroll(page);
});

test("Katha with labelled legends and sources, and the guide with an emergency answer", async ({ page }) => {
  await page.goto("/katha/place/?subject=Basilica%20of%20Bom%20Jesus");
  await page.getByRole("button", { name: /^5 / }).click(); // nothing loads until a length is picked (10 is hidden until TY2 passes it)
  await expect(page.getByRole("button", { name: /^10 / })).toHaveCount(0);
  await expect(page.locator(".seg.legend").first()).toContainText("As the story goes");
  await expect(page.locator(".srcs li")).toHaveCount(2);
  await page.locator("a.cite").first().click();
  await expect(page).toHaveURL(/#k-src-1$/);

  await page.goto("/ask/");
  await page.getByRole("button", { name: /Where is the nearest hospital/ }).click();
  await expect(page.getByText("In an emergency, call 112")).toBeVisible();
  await expect(page.getByRole("link", { name: "Map" }).first()).toHaveAttribute("href", /openstreetmap\.org/);
  await noSidewaysScroll(page);
});

test("language, consents and delete my data", async ({ page }) => {
  await page.goto("/settings/");
  await page.getByRole("combobox").first().selectOption("hi");
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
  await expect(page.getByRole("link", { name: "होम" })).toBeVisible();
  await noSidewaysScroll(page);
  await page.getByRole("combobox").first().selectOption("en");

  const keep = page.getByRole("switch", { name: "Keep my trips" });
  await expect(keep).toHaveAttribute("aria-checked", "false");
  await keep.click();
  await expect(keep).toHaveAttribute("aria-checked", "true");

  await page.getByLabel("Type DELETE to confirm").fill("DELETE");
  await page.getByRole("button", { name: "Delete my data" }).click();
  await expect(page.getByText("Deleted from this browser.")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("switch", { name: "Keep my trips" })).toHaveAttribute("aria-checked", "false");
});

test("study: ty arm plans in the app, baseline arm uses the timer with no app navigation", async ({ page }) => {
  await page.goto("/study/?task=plan_goa_family&arm=ty");
  await expect(page.getByText("Goa with the family")).toBeVisible();
  await page.getByRole("button", { name: "I agree, start" }).click();
  await expect(page).toHaveURL(/\/plan\/start\/$/);

  await page.goto("/study/?task=plan_mysuru_weekend&arm=baseline");
  await expect(page.getByRole("navigation", { name: "Main" })).toHaveCount(0);
  await page.getByRole("button", { name: "I agree, start" }).click();
  await expect(page).toHaveURL(/\/study\/baseline\//);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("A weekend in Mysuru");
  await expect(page.getByRole("button", { name: "I have my plan" })).toBeDisabled();
  await page.getByRole("button", { name: "Start" }).click();
  await page.getByRole("button", { name: "I have my plan" }).click();
  await page.getByRole("button", { name: "I chose where to book" }).click();
  await expect(page.getByText("Thank you. You can close this tab.")).toBeVisible();
});

test("privacy is linked from the footer; data deletion from Settings only", async ({ page }) => {
  await page.goto("/home/");
  await page.getByRole("contentinfo").getByRole("link", { name: "Privacy policy" }).click();
  await expect(page).toHaveURL(/\/privacy\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Privacy policy");
  await expect(page.getByRole("link", { name: "rohan@aizyantra.com" }).first()).toHaveAttribute("href", "mailto:rohan@aizyantra.com");
  await expect(page.getByRole("contentinfo").getByRole("link", { name: "Delete your data" })).toHaveCount(0);
  await page.goto("/settings/");
  await page.getByRole("link", { name: "Delete your data" }).click();
  await expect(page).toHaveURL(/\/data-deletion\/$/);
  await expect(page.getByText(/delete my data/i).first()).toBeVisible();
  await noSidewaysScroll(page);
});

test("a shared plan opens read only", async ({ page }) => {
  await page.goto("/t/sample-goa-family/");
  await expect(page.getByText("Shared plan, read only")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Bengaluru to Goa");
  await page.goto("/t/not-a-token/");
  await expect(page.getByText(/was not found/)).toBeVisible();
});
