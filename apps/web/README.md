# Truvix web

Four static pages. No build step, no dependencies, no framework: they must keep
working years after anybody last thought about them, and a toolchain is a thing
that rots.

| Page | Why it exists |
| --- | --- |
| `index.html` | Somewhere for the wordmark and the support address to point |
| `verify-email.html` | Completes the email verification link the backend mails |
| `terms.html` | Linked from the paywall; App Store review requires it |
| `privacy.html` | Linked from the paywall and from App Store Connect |

The last two are not optional. Guideline 3.1.2 rejects a subscription screen
that does not link to working Terms of Use and Privacy Policy pages.

## Before publishing

**1. Fill in `assets/config.js`.** Company name, address, tax details and the
API's address all live there. A field left empty renders as
`[legalName — yapılandırılmadı]` in amber rather than as a blank, so a document
published half-finished says so instead of quietly reading as though the field
was never meant to be there.

These are legal statements. A developer inventing a company address is not
filling in a placeholder, they are making a false representation, which is why
the file ships empty.

**2. Have a lawyer read `terms.html` and `privacy.html`.** They are written from
what the code actually does — every row of the data table in the privacy policy
was checked against the database schema, and the section on what reaches OpenAI
against `modules/analysis/vision.py`. That makes them accurate, not sufficient.
KVKK obligations, VERBİS registration and consumer law are not things a
developer should sign off.

**3. Allow the site's origin on the API.** The pages are served from
`truvix.app` and call `api.truvix.app`, which is cross-origin: without this the
verification page fails with a network error and no explanation.

```bash
TRUVIX_CORS_ALLOWED_ORIGINS=["https://truvix.app","https://www.truvix.app"]
```

Production configuration rejects `*`, so the origins must be listed explicitly.

## Deploying

Any static host: Cloudflare Pages, Netlify, S3 with CloudFront, or nginx serving
the directory. The email link points at `verify-email.html`, so keep that
filename or update `TRUVIX_EMAIL_VERIFICATION_BASE_URL` to match.

## Running locally

```bash
python3 -m http.server 4173 --bind 127.0.0.1
```

Point `apiBaseUrl` at `http://127.0.0.1:8000/api/v1` and start the backend with
that origin allowed:

```bash
TRUVIX_CORS_ALLOWED_ORIGINS='["http://127.0.0.1:4173"]' uv run uvicorn truvix.main:app
```

## A note on the token in the URL

The verification link carries a single-use token as a query parameter, because
that is what fits in an email. Two things follow, both already handled here:
`<meta name="referrer" content="no-referrer">` keeps it out of referrer headers,
and the page rewrites the address bar once the request has been made so the
spent token is not left sitting there to be shared or bookmarked.
