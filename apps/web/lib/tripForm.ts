import type { Pace, Traveller, TripDraft, TripRequest } from "@/lib/contracts";
import { GOA_REQUEST } from "@/lib/mockPlan";

export type TripForm = {
  from: string;
  to: string;
  start: string;
  end: string;
  adults: number;
  seniors: number;
  kids: number;
  stepFree: boolean;
  interests: string[];
  pace: Pace;
  food: string;
  budget: string;
  /** The travellers the form started from (sample or intake's draft); kept while the counts match. */
  people?: Traveller[];
};

export const INTERESTS = ["Churches", "Temples", "Beaches", "Forts and palaces", "Food", "Nature and waterfalls", "Museums", "Markets"];
export const PACES: [Pace, string][] = [["relaxed", "Gentle"], ["balanced", "Balanced"], ["packed", "Packed"]];
export const FOODS = ["Vegetarian", "Jain", "Eggs are fine", "Anything"];

const isSenior = (t: Traveller) => t.age >= 60;
const isKid = (t: Traveller) => t.age < 18;

/** The form, prefilled from the Goa family sample. */
export function goaForm(): TripForm {
  const r = GOA_REQUEST;
  const c = r.constraints ?? {};
  const people = c.travellers ?? [];
  return {
    from: r.origin,
    to: r.destinations.join(", "),
    start: r.start_date,
    end: r.end_date,
    ...counts(people),
    stepFree: (c.mobility_needs ?? []).includes("step-free access"),
    interests: ["Churches", "Temples", "Beaches"],
    pace: c.pace ?? "relaxed",
    food: "Vegetarian",
    budget: String(c.budget_inr ?? ""),
  };
}

const counts = (people: Traveller[]) => ({
  adults: people.filter((t) => !isSenior(t) && !isKid(t)).length,
  seniors: people.filter(isSenior).length,
  kids: people.filter(isKid).length,
});

/**
 * The form from what intake understood on needs_input. Missing fields stay
 * empty so the form asks for them; a missing group counts as one adult.
 */
export function formFromDraft(d: TripDraft): TripForm {
  const people = d.travellers ?? [];
  const c = people.length ? counts(people) : { adults: 1, seniors: 0, kids: 0 };
  return {
    from: d.origin ?? "",
    to: (d.destinations ?? []).join(", "),
    start: d.start_date ?? "",
    end: d.end_date ?? "",
    ...c,
    stepFree: false,
    interests: [],
    pace: d.pace ?? "balanced",
    food: "Anything",
    budget: d.budget_inr ? String(d.budget_inr) : "",
    people: people.length ? people : undefined,
  };
}

/** Keeps the starting travellers (sample or draft) when the group is unchanged; otherwise numbered placeholders. */
function travellers(f: TripForm): Traveller[] {
  const base = f.people ?? GOA_REQUEST.constraints?.travellers ?? [];
  const d = counts(base);
  if (f.adults === d.adults && f.seniors === d.seniors && f.kids === d.kids) return base;
  const list: Traveller[] = [];
  for (let i = 1; i <= f.adults; i++) list.push({ name: `Adult ${i}`, age: 35 });
  for (let i = 1; i <= f.seniors; i++) list.push({ name: `Senior ${i}`, age: 65 });
  for (let i = 1; i <= f.kids; i++) list.push({ name: `Child ${i}`, age: 10 });
  return list;
}

/** What is wrong with the form, in plain words; empty when it can be sent. */
export function formProblems(f: TripForm): string[] {
  const p: string[] = [];
  if (!f.from.trim()) p.push("Say where you start from.");
  if (!f.to.trim()) p.push("Say where you are going.");
  if (!f.start || !f.end) p.push("Pick the first and last day.");
  else if (f.end < f.start) p.push("The last day is before the first.");
  if (f.adults + f.seniors + f.kids < 1) p.push("Add at least one traveller.");
  if (f.budget && !/^\d+$/.test(f.budget.replace(/,/g, ""))) p.push("Write the budget as a number of rupees.");
  return p;
}

export function toTripRequest(f: TripForm, lang: TripRequest["lang"] = "en"): TripRequest {
  const budget = f.budget.replace(/,/g, "");
  const food = f.food === "Anything" ? [] : [f.food.toLowerCase()];
  return {
    origin: f.from.trim(),
    destinations: f.to.split(",").map((s) => s.trim()).filter(Boolean),
    start_date: f.start,
    end_date: f.end,
    constraints: {
      budget_inr: budget ? Number(budget) : null,
      pace: f.pace,
      mobility_needs: f.stepFree ? ["step-free access"] : [],
      dietary: food,
      travellers: travellers(f),
    },
    lang,
    notes: f.interests.length ? `Interests: ${f.interests.join(", ")}.` : null,
  };
}
