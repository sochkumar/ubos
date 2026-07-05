/**
 * Slugify a human label into a safe key.
 * Policy:
 *  - Lowercase
 *  - Any run of non-[a-z0-9] → single "_"
 *  - Collapse consecutive "_"
 *  - Strip leading and trailing "_"
 *  - Ensure result starts with a letter — if it starts with a digit, prefix "f"
 *  - Truncate to 64 chars
 *
 * Backend contract: `^[a-z][a-z0-9_]*$` (max 64).
 */
export function slugifyKey(input) {
  let v = (input ?? "").toString().toLowerCase();
  v = v.replace(/[^a-z0-9]+/g, "_");
  v = v.replace(/_+/g, "_");
  v = v.replace(/^_+|_+$/g, "");
  if (/^\d/.test(v)) v = "f" + v;
  return v.slice(0, 64);
}
