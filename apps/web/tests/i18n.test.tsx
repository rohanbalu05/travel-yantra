import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LangPicker } from "@/components/AppShell";
import { LANGS, LangProvider, saveLang, translate, useI18n } from "@/lib/i18n";
import phrasebook from "@/lib/i18n/phrasebook.json";

vi.mock("next/navigation", () => ({ usePathname: () => "/home/" }));

// Node's own global localStorage hides jsdom's here; give the tests a plain one.
const store = new Map<string, string>();
vi.stubGlobal("localStorage", {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, v),
  removeItem: (k: string) => void store.delete(k),
  clear: () => store.clear(),
});

afterEach(() => {
  cleanup();
  store.clear();
  saveLang("en");
});

describe("translate", () => {
  it("uses TY5's phrasebook and falls back to English", () => {
    expect(translate("Try again", "hi")).toBe((phrasebook as Record<string, Record<string, string>>)["Try again"].hi);
    expect(translate("Not in any dictionary", "ta")).toBe("Not in any dictionary");
    expect(translate("Try again", "en")).toBe("Try again");
  });

  it("has every phrase in all five Indian languages", () => {
    const missing = Object.entries(phrasebook as Record<string, Record<string, string>>).flatMap(([en, e]) =>
      LANGS.filter((l) => l.code !== "en" && !e[l.code]).map((l) => `${en}:${l.code}`),
    );
    expect(missing).toEqual([]);
  });
});

function Probe() {
  const { lang, t } = useI18n();
  return <p data-testid="probe">{lang}:{t("Plan my trip")}</p>;
}

describe("language switch", () => {
  it("switches the app, remembers the choice and sets <html lang>", () => {
    render(
      <LangProvider>
        <LangPicker />
        <Probe />
      </LangProvider>,
    );
    expect(screen.getByTestId("probe").textContent).toBe("en:Plan my trip");
    act(() => {
      fireEvent.change(screen.getByRole("combobox"), { target: { value: "kn" } });
    });
    expect(screen.getByTestId("probe").textContent).toBe(`kn:${translate("Plan my trip", "kn")}`);
    expect(localStorage.getItem("ty.lang")).toBe("kn");
    expect(document.documentElement.lang).toBe("kn");
    expect(document.documentElement.dataset.lang).toBe("kn");
  });

  it("names each language in its own script", () => {
    render(<LangProvider><LangPicker /></LangProvider>);
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["English", "हिन्दी", "ಕನ್ನಡ", "தமிழ்", "తెలుగు", "বাংলা"]);
  });
});
