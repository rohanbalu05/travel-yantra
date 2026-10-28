// Screenshots of the deployed web app (not a test; never run in CI).
// Usage: node e2e/live-shots.mjs <base-url> <out-dir>
// Makes one plan on the live site (a few model calls on the agreed Gemini models).
import { chromium, devices } from "@playwright/test";
import { mkdirSync } from "node:fs";

const [base, out] = process.argv.slice(2);
if (!base || !out) throw new Error("usage: node e2e/live-shots.mjs <base-url> <out-dir>");
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
const sizes = { phone: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } }, laptop: { viewport: { width: 1366, height: 860 } } };
const notes = [];

async function shot(page, name) {
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  if (wide) notes.push(`${name}: sideways scroll`);
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: true });
}

for (const [size, opts] of Object.entries(sizes)) {
  for (const lang of ["en", "hi"]) {
    const ctx = await browser.newContext(opts);
    await ctx.addInitScript((l) => localStorage.setItem("ty.lang", l), lang);
    const page = await ctx.newPage();
    const go = async (path, name) => {
      await page.goto(base + path, { waitUntil: "networkidle" });
      await shot(page, `${size}-${lang}-${name}`);
    };
    await go("/home/", "home");
    await go("/signin/", "signin");
    await go("/plan/start/?mode=form", "plan-form");
    await go("/plan/start/", "plan-words");
    await go("/katha/", "katha-library");
    await go("/settings/", "settings");
    await go("/trips/", "trips-empty");
    await ctx.close();
  }
}

// One live plan (phone, English), then the pages that need it, and My trips after.
{
  const ctx = await browser.newContext(sizes.phone);
  const page = await ctx.newPage();
  // Anonymous: turn on Keep my trips so My trips lists the plan (signed-in accounts have it on).
  await page.goto(`${base}/settings/`, { waitUntil: "networkidle" });
  const keep = page.getByRole("switch").first();
  if ((await keep.getAttribute("aria-checked")) !== "true") await keep.click();
  await page.waitForTimeout(1500);
  await page.goto(`${base}/plan/start/`, { waitUntil: "networkidle" });
  await page.getByLabel("Your trip, in your words").fill("Bengaluru to Goa, 11 to 14 Dec 2026, with my parents and sister. Churches and a little beach.");
  await page.getByRole("button", { name: "Plan my trip" }).first().click();
  await page.getByText(/Your plan is ready|We need a little more|could not/i).first().waitFor({ timeout: 180_000 });
  await shot(page, "phone-en-plan-done");
  for (const [path, name] of [["/plan/options/", "options"], ["/plan/itinerary/", "itinerary"], ["/book/", "book"], ["/katha/", "katha-with-plan"], ["/ask/", "ask"], ["/trips/", "trips"], ["/home/", "home-with-trip"]]) {
    await page.goto(base + path, { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);
    await shot(page, `phone-en-${name}`);
  }
  // My trips → View details opens the editable Itinerary, not the share page.
  await page.goto(`${base}/trips/`, { waitUntil: "networkidle" });
  const view = page.getByRole("button", { name: "View details" }).first();
  if (await view.count()) {
    await view.click();
    await page.waitForURL(/\/plan\/itinerary\/$/, { timeout: 30_000 });
    await shot(page, "phone-en-trips-reopened");
    notes.push(`View details opened ${new URL(page.url()).pathname}`);
  } else notes.push("My trips: no saved trip to reopen");
  await ctx.close();
}

await browser.close();
console.log(notes.length ? notes.join("\n") : "no sideways scroll on any page");
