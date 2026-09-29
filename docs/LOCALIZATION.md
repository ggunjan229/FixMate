# FixMate localization

The app currently offers English and Hindi. The language picker lists only locales with an included translation dictionary. UI labels are translated in the browser; service IDs, API payloads, database statuses, and worker/customer-entered data remain unchanged so localization cannot change matching or booking behavior.

## Adding another language

1. Add a locale entry to `app/i18n.js` with its display label and BCP-47 locale for date/number formatting.
2. Translate all visible text, dialog copy, form labels, placeholders, accessibility labels, statuses, errors, and dynamic message templates.
3. Add the language option to `app/index.html` only after the translation is complete.
4. Verify customer, worker, and administrator flows, including modals, filters, booking state changes, forecast results, and empty/error states.
5. Update the service-worker cache version if the locale bundle's cache contract changes.

FixMate does not send customer text or personal data to a third-party translation service. A locale must be reviewed before it is exposed in the picker; silently falling back to English would recreate the mixed-language problem.
