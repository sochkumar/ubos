# UBOS — Auth testing brief for automation

## Bearer flow

1. `POST ${API}/auth/login` with `{ "email": "owner@ubos.test", "password": "OwnerPass!123" }`
2. Response body → `{ access_token, refresh_token, org_id, role, permissions, user, organizations }`
3. All subsequent requests: `Authorization: Bearer <access_token>`
4. On 401 → call `POST ${API}/auth/refresh` with `{ refresh_token }`, replace tokens.
5. To log out → `POST ${API}/auth/logout` with `{ refresh_token }` (also revoked server-side).

## In Playwright / browser tests

Frontend stores tokens in `localStorage`:

```js
localStorage.setItem("ubos.access_token", "<access>");
localStorage.setItem("ubos.refresh_token", "<refresh>");
```

Simpler + more reliable: drive `POST /api/auth/login` from Playwright and inject
the returned tokens directly into localStorage before navigating, e.g.:

```python
resp = requests.post(f"{API}/auth/login", json={"email": E, "password": P}).json()
await page.evaluate(f'''
  localStorage.setItem("ubos.access_token", "{resp['access_token']}");
  localStorage.setItem("ubos.refresh_token", "{resp['refresh_token']}");
''')
await page.goto(f"{FRONTEND_URL}/entity-types")
```

## Multi-tenancy

- Every request MUST resolve an `org_id`. Coming from the JWT (`org_id` claim) by
  default; overridable via `X-Org-Id` header only if the user is a member of that org.
- `POST /api/orgs/{id}/switch` re-issues tokens with a new active `org_id`.

## Google OAuth

- Currently DISABLED (env vars are placeholders). `GET /api/auth/google/status` returns `{enabled:false}`.
- Frontend button is disabled with a tooltip.
- To enable manually: set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `/app/backend/.env`
  and restart the backend. The redirect URI is always built by the frontend
  (`window.location.origin + "/auth/google/callback"`) — never hardcoded.

## Seeded baseline

On empty DB, backend seeds three users + one org "Acme Furniture":
- owner@ubos.test / OwnerPass!123   → owner
- editor@ubos.test / EditorPass!123 → editor
- viewer@ubos.test / ViewerPass!123 → viewer

They all share the same org and default to it on first login.

## Curl smoke test

```sh
API="$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)/api"
TOKEN=$(curl -s -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"owner@ubos.test","password":"OwnerPass!123"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s "$API/entity-types" -H "Authorization: Bearer $TOKEN"
```
