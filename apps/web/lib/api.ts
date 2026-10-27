/** API base URL, set at build time. Empty means "no API": the plan flow replays the Goa sample (lib/mockPlan.ts). */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
