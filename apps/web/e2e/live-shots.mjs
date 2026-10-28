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

/** Waits until a revise outcome line is shown (any text that is not the in-progress one). */
async function outcome(page) {
  await page.waitForFunction(() => [...document.querySelectorAll("p.rev-msg")].some((p) => !p.hidden && p.textContent && !/…$/.test(p.textContent.trim())), null, { timeout: 150_000 });
  return [...(await page.locator("p.rev-msg:not([hidden])").allTextContents())].map((x) => x.trim()).filter(Boolean).join(" | ");
}

async function shot(page, name) {
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  if (wide) notes.push(`${name}: sideways scroll`);
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: true });
}

for (const [size, opts] of Object.entries(sizes)) {
  for (const lang of ["en", "hi", "ta"]) {
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

// The longest scripts at phone width: the Plan page with the chat box (TY5) and buttons.
for (const lang of ["kn", "bn"]) {
  const ctx = await browser.newContext(sizes.phone);
  await ctx.addInitScript((l) => localStorage.setItem("ty.lang", l), lang);
  const page = await ctx.newPage();
  await page.goto(`${base}/plan/start/`, { waitUntil: "networkidle" });
  await shot(page, `phone-${lang}-plan-words`);
  await ctx.close();
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
  // The form, with a budget style (TY1's budget_style), four travellers, two of them seniors.
  await page.goto(`${base}/plan/start/?mode=form`, { waitUntil: "networkidle" });
  await page.getByLabel("From").fill("Bengaluru");
  await page.getByLabel("To", { exact: true }).fill("Goa");
  await page.getByLabel("First day").fill("2026-12-11");
  await page.getByLabel("Last day").fill("2026-12-14");
  await page.getByRole("button", { name: "One more: Adults" }).click();
  await page.getByRole("button", { name: "One more: Seniors" }).click();
  await page.getByRole("button", { name: "One more: Seniors" }).click();
  await page.getByRole("button", { name: "Shoestring" }).click();
  await shot(page, "phone-en-form-filled");
  await page.getByRole("button", { name: "Plan my trip" }).last().click();
  await page.getByText(/Your plan is ready|We need a little more|could not/i).first().waitFor({ timeout: 180_000 });
  await shot(page, "phone-en-plan-done");
  for (const [path, name] of [["/plan/options/", "options"], ["/plan/itinerary/", "itinerary"], ["/book/", "book"], ["/katha/", "katha-with-plan"], ["/ask/", "ask"], ["/trips/", "trips"], ["/home/", "home-with-trip"]]) {
    await page.goto(base + path, { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);
    await shot(page, `phone-en-${name}`);
  }
  // budget_style: switch the plan to Comfort on the Itinerary.
  await page.goto(`${base}/plan/itinerary/`, { waitUntil: "networkidle" });
  const comfort = page.getByRole("group", { name: "Budget style" }).getByRole("button", { name: "Comfort" });
  if ((await comfort.count()) && (await comfort.isEnabled())) {
    await comfort.click();
    notes.push(`budget_style: ${await outcome(page)}`);
    await shot(page, "phone-en-itinerary-style");
  }

  // change_stay: pick another stay on Book, then booked: the rail option's train with its times.
  await page.goto(`${base}/book/`, { waitUntil: "networkidle" });
  const others = page.locator("details.stay-others").first();
  if (await others.count()) {
    await others.locator("summary").click();
    await others.getByRole("button", { name: "Choose this stay" }).first().click();
    notes.push(`change_stay: ${await outcome(page)}`);
    await shot(page, "phone-en-book-stay-changed");
  } else notes.push("change_stay: no other stays offered");
  const booked = page.getByRole("button", { name: "I've booked this" }).first();
  if (await booked.count()) {
    await booked.click();
    const ref = page.locator("form.booked input").first();
    if (!(await ref.inputValue())) await ref.fill("17309");
    await page.getByRole("button", { name: "Update my plan" }).click();
    notes.push(`booked: ${await outcome(page)}`);
    await shot(page, "phone-en-book-booked");
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
