# Cost gate

Stop the card before building, enabling or recommending anything that adds
or raises a charge: a cloud service or setting, a model or tier change, a
new vendor or paid API plan, a paid API call pattern outside the agreed free
caps, a domain, SMS, or a free tier we would outgrow.

When that happens:

1. Do not build the paid part.
2. Add the label `needs-rohan` to the card.
3. Post a BLOCKED STOP that says: what changes; the cost in ₹ with the price
   source and date; any one-time cost; which account pays; the cheaper
   option.
4. Move on to your next card.

Already agreed (no stop needed): Cloud Run, Cloud SQL, Vertex Gemini 3.5
Flash and 3.1 Flash-Lite, Places and Routes within free caps, Firebase
Hosting, GitHub Actions, the WhatsApp test number, Wikimedia, datameet,
AI Studio free tier, Sarvam within the ₹100 free credit, SerpApi free plan.

Code that calls a paid API must cache responses and must not run in tests.
