# Katha style guide (binding for TY2)

Katha is the story of a place, told to a traveller standing in or near it.
It must hold attention and feel written by a person who loves the place and
respects the reader. It must never read like generic AI travel copy.

## Why it works this way (the research we build on)

- **Interpretation is provocation, not instruction** (Freeman Tilden,
  *Interpreting Our Heritage*, 1957). Information alone is not
  interpretation; the aim is to make the reader think and feel, relate the
  place to their own life, and present a whole rather than a part.
- **One theme, made relevant** (Sam Ham, thematic interpretation). A strong,
  relevant theme is what people remember and think about afterwards.
- **Attention has stages and a price** (Stephen Bitgood, attention-value
  model): capture, then focus, then engagement. People keep paying attention
  only while it feels worth the effort.
- **Curiosity is a gap** (George Loewenstein, information-gap theory, 1994).
  Open a question the reader wants answered; close it later.
- **Peak and end** (Kahneman's peak-end rule). People remember the high point
  and the ending more than the average.
- **Stories carry facts** (narrative transportation): readers absorbed in a
  story remember more of what it carries.

## The twelve rules

1. **One theme.** Write it first as a single line the reader should remember
   ("Hampi was so rich that its markets sold diamonds by the heap"). Every
   paragraph serves it. Cut anything that doesn't.
2. **Hook in the first two sentences.** A person at a moment, a
   contradiction, or a question. Never open with a date, "Located in…",
   "Welcome to…", or a list of superlatives.
3. **A curiosity gap.** Open one question early and close it near the end.
   The 10-minute version opens one per chapter.
4. **People, not lists.** Someone wants something and meets an obstacle: a
   king, a builder, a poet, a merchant, a family that still lives there.
   Facts ride on the story.
5. **Specific and sensory.** At least one checkable specific per paragraph
   (a name, a number, an object) from our sources, and at least one thing to
   see, hear, smell or touch in each version.
6. **Point at what's there.** When the place has such details, direct the
   reader's eyes: "Look at the third pillar on your left…"
7. **One bridge to the reader's life.** A festival they know, a food they
   have eaten, a family trip, a habit that still survives.
8. **A peak and an ending that lands.** The emotional high point sits about
   two-thirds through. End on an image or a line, never a summary, never an
   instruction to visit.
9. **Honest labels.** History (sourced, with a citation), Legend ("people
   here say…"), Disputed (both versions, briefly). Never invent a fact,
   name, date or quote. If the sources are thin, the story is shorter.
10. **Written for the ear.** Mix short sentences with long ones. Use plain
    words. Read-aloud budgets: about 300 words (2 min), 750 words (5 min),
    1,500 words (10 min, in 3–4 chapters, each with its own hook).
11. **No slop.** The checker fails a Katha that contains any of: nestled,
    rich tapestry, tapestry, testament to, steeped in history, hidden gem,
    bustling, vibrant, breathtaking, awe-inspiring, delve, step back in time,
    boasts, a must-visit, must-see, whether you're a … or a …, in
    conclusion, a blend of, timeless charm, rich heritage, nestled amidst,
    plus stacked triples of adjectives and more than one rhetorical question
    in a row. Grow the list when the taste gate finds more.
12. **Each language from the same outline.** Write each language from the
    shared outline (theme, hook, gap, peak, ending, facts), in that
    language's natural voice; not word-for-word translation. Native-speaker
    teammates check samples.

## The pipeline

1. **Facts:** retrieve sourced facts for the place (POIs, chunks, legends,
   Wikimedia), each with its source.
2. **Outline:** theme line, hook, the gap, the people, three to six beats,
   the peak, the ending image, labels for each fact.
3. **Draft** to the word budget for the requested length.
4. **Self-critique** against the rubric below; revise once.
5. **Checks:** banned-phrase checker, citation check (every History claim
   maps to a source), length check. A failing Katha is regenerated, not
   shipped.

## Rubric (used by the self-critique and the taste gate; 1–5 each)

- Hook: would a tired traveller read the third sentence?
- Theme: can a reader say the one line afterwards?
- Specifics: are the details concrete, checkable and vivid?
- Peak: is there a moment that lands emotionally?
- Ending: does it end on an image or line worth remembering?
- Honesty: are history, legend and disputed claims labelled and sourced?

## The taste gate (before TY2 scales Katha)

- Three places (one temple or fort, one city, one food or market story) ×
  three lengths, each paired with a plain-prompt version ("write a 5-minute
  story about X").
- Rohan and the team rate them blind (pairs shuffled), 1–5 on the rubric.
- Pass: Katha averages 4 or more and beats the plain version on most pairs.
  The comparison also goes into the report.
- Saved under `data/katha/taste-gate/`.
