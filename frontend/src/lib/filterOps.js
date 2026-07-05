// Client-side mirror of backend services/query_builder.OPS_BY_TYPE.
// Keep both in sync — backend still validates, this only shapes the UI.

export const OPS_BY_TYPE = {
  text: ["eq", "ne", "contains", "in", "not_in", "is_empty", "is_not_empty"],
  longtext: ["eq", "ne", "contains", "is_empty", "is_not_empty"],
  richtext: ["contains", "is_empty", "is_not_empty"],
  number: ["eq", "ne", "gt", "lt", "gte", "lte", "between", "in", "not_in", "is_empty", "is_not_empty"],
  currency: ["eq", "ne", "gt", "lt", "gte", "lte", "between", "is_empty", "is_not_empty"],
  date: ["eq", "ne", "gt", "lt", "gte", "lte", "between", "is_empty", "is_not_empty"],
  datetime: ["eq", "ne", "gt", "lt", "gte", "lte", "between", "is_empty", "is_not_empty"],
  boolean: ["eq", "ne"],
  dropdown: ["eq", "ne", "in", "not_in", "is_empty", "is_not_empty"],
  multi_select: ["in", "not_in", "is_empty", "is_not_empty"],
  email: ["eq", "ne", "contains", "is_empty", "is_not_empty"],
  phone: ["eq", "ne", "contains", "is_empty", "is_not_empty"],
  url: ["eq", "ne", "contains", "is_empty", "is_not_empty"],
};

export const OP_LABELS = {
  eq: "equals",
  ne: "not equals",
  contains: "contains",
  gt: "greater than",
  lt: "less than",
  gte: "≥",
  lte: "≤",
  between: "between",
  in: "in",
  not_in: "not in",
  is_empty: "is empty",
  is_not_empty: "is not empty",
};

export function opsForField(fieldType) {
  return OPS_BY_TYPE[fieldType] || OPS_BY_TYPE.text;
}

export function needsValue(op) {
  return op !== "is_empty" && op !== "is_not_empty";
}

export function isRangeOp(op) {
  return op === "between";
}

export function isListOp(op) {
  return op === "in" || op === "not_in";
}

export const BULK_ALLOWED_FIELD_TYPES = new Set([
  "text", "longtext", "number", "currency", "boolean",
  "dropdown", "date", "datetime", "email", "phone", "url",
]);
