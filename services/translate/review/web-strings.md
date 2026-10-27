# Web strings: TY5 review for native speakers (28 Oct 2026)

What was checked: TY4's UNREVIEWED strings (`apps/web/lib/i18n/screens-plan.json`,
`screens-guide.json` and the `EXTRA` table in `index.tsx`): 418 strings in hi, kn, ta, te and bn,
against the phrasebook (`services/translate/app/phrasebook.tsv`).

How: `uv run python scripts/review_web_strings.py review/web-strings-flags.md` checks every
string automatically. It looks for:
- missing or untranslated strings
- wrong script, length and foreign punctuation
- lost `{placeholders}` and numbers
- travel terms that don't use the phrasebook's word

Brand names and acronyms kept in Latin (Travel Yantra, IRCTC, PNR, OpenStreetMap) are allowed.
48 of 2,090 string-language pairs are flagged
([web-strings-flags.md](web-strings-flags.md)). I then went through the flags and the EXTRA table
by hand. Nothing is missing, untranslated or has a broken placeholder.

TY5 is not a native speaker of these languages. The items below are doubts for Rohan's native
speakers to settle, not corrections. TY4 owns the files and makes any change.

## Doubtful: please decide

1. **Telugu "trip": యాత్ర or ప్రయాణం** (27 strings, e.g. "My trips" → నా యాత్రలు). The web uses
   యాత్ర throughout, but the phrasebook and the bot use ప్రయాణ. In everyday Telugu, యాత్ర can
   suggest a pilgrimage. Pick one, and TY5 aligns the phrasebook to it.
2. **Bengali "Katha" → কথা** (13 strings, e.g. "City Katha" → শহরের কথা). কথা usually means
   "talk, words", not "story" (গল্প, কাহিনি). Does শহরের কথা read as "the city's story" or as "talk
   about the city"?
3. **Is "Katha" a name or a word?** Hindi keeps it as कथा and Telugu as కథ. Kannada and Tamil
   translate it as the word for story (ಕಥೆ, கதை), so "Play the Katha" becomes "play the story".
   Both are defensible; it should be one rule across all five.
4. **Tamil register** (8 strings use the informal imperative, about 81 the polite -ங்கள் form):
   - Swap → மாற்று
   - Start → தொடங்கு
   - Open → திற
   - Open IRCTC → IRCTC-யைத் திற
   - Open Settings → அமைப்புகளைத் திற
   - Share my location → என் இருப்பிடத்தைப் பகிர்
   - Delete my data → என் தரவை நீக்கு
   - I agree, start → நான் ஒப்புக்கொள்கிறேன், தொடங்கு

   Short informal buttons may be fine. The phrasebook also has a few (பகிர், ரத்து செய்), but the
   mix reads unevenly next to polite sentences.
5. **Bengali numerals**: 14 Bengali strings use Bengali digits (১৫ সেকেন্ড, ১০ সংখ্যার PNR), while
   every other language uses 0–9. For input hints ("10-digit PNR", "Rating, 1 to 5") users will
   type 0–9, so Bengali digits there may confuse them. Choose one convention.
6. **Place names left in English inside Indic sentences**: "Why is the Basilica of Bom Jesus
   famous?" keeps "Basilica of Bom Jesus" in Latin script in all five languages. The guide and
   the bot use native names, e.g. Hindi बॉम जीसस बेसिलिका. Native spellings would match what the
   guide answers.
7. **Tamil "Plan a trip"** (EXTRA) → பயணம் திட்டமிடுங்கள். The object needs the accusative:
   பயணத்தைத் திட்டமிடுங்கள் (the phrasebook's form, as in "Plan my trip").
8. **Bengali "Ask"** → জিজ্ঞাসা করুন is only flagged as long for a one-word button. It is
   correct; শুধান or প্রশ্ন করুন are shorter if the button is tight.

## Looked at and fine

- Hindi: no doubts beyond item 3. यात्रा, योजना, दिन and बजट are used consistently.
- Placeholders such as `{day}`, `{budget}` and `{travellers}` move to where each language's word
  order needs them; the flags on "{day} in {city}" are false positives.
- Acronyms stay in Latin (IRCTC, PNR, AI), and "Type DELETE to confirm" keeps the literal
  DELETE the form checks for.
