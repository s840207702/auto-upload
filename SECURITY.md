# Security Policy

## Sensitive Data

Do not commit or share:

- `cookiesFile/`
- `db/`
- `videoFile/`
- `avatars/`
- `logs/`
- `.venv/`
- `python/`
- `third_party/`
- Any Cookie, Token, session, account screenshot, real video, cover image, or local database.

## Before Publishing The Repository

Run at least these checks:

```powershell
git status --short
git ls-files cookiesFile db videoFile avatars logs
git grep -n "cookie\\|token\\|session\\|password\\|Authorization"
```

If any real credential, Cookie, local account data, or private media file has ever been committed, do not simply delete it in a later commit. Rotate the affected credentials and publish from a clean repository or rewrite the Git history before making the repository public.

## Reporting

Please report security issues privately to the repository owner. Do not open public issues containing credentials, Cookies, account screenshots, private media, or reproduction data with sensitive values.

