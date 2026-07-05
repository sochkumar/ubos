/**
 * Lightweight hotkey registry (Phase 6-A).
 *
 * Rules:
 *   - Sequence keys: `useHotkeys("g d", cb)` fires when the user types `g` then
 *     `d` within 1500 ms. Bare single keys ("n", "?") fire immediately.
 *   - Modifiers: use "mod" for Cmd on macOS and Ctrl elsewhere. e.g. "mod+k".
 *   - Ignored when focus is inside an input / textarea / contentEditable.
 *   - `deps` array — like `useEffect`, re-binds when deps change.
 */
import { useEffect, useRef } from "react";

const IS_MAC =
  typeof navigator !== "undefined" &&
  /Mac|iPhone|iPad|iPod/i.test(navigator.platform || "");

function isEditable(el) {
  if (!el) return false;
  if (el.isContentEditable) return true;
  const tag = (el.tagName || "").toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select";
}

function normalizeCombo(combo) {
  return combo
    .toLowerCase()
    .split("+")
    .map((p) => p.trim())
    .map((p) => (p === "mod" ? (IS_MAC ? "meta" : "ctrl") : p))
    .sort()
    .join("+");
}

function eventCombo(e) {
  const parts = [];
  if (e.ctrlKey) parts.push("ctrl");
  if (e.metaKey) parts.push("meta");
  if (e.altKey) parts.push("alt");
  if (e.shiftKey && e.key.length > 1) parts.push("shift"); // avoid duplicating letters
  const key = (e.key || "").toLowerCase();
  if (!["control", "meta", "alt", "shift"].includes(key)) parts.push(key);
  return parts.sort().join("+");
}

export function useHotkeys(binding, callback, deps = []) {
  const cbRef = useRef(callback);
  cbRef.current = callback;

  useEffect(() => {
    const isSequence = /\s/.test(binding.trim());
    const parts = binding.trim().toLowerCase().split(/\s+/);
    let cursor = 0;
    let seqTimer = null;

    const handler = (e) => {
      if (isEditable(document.activeElement) && !/^(mod|ctrl|meta)\+/i.test(binding)) return;
      if (e.defaultPrevented) return;

      if (isSequence) {
        // sequence: match a single lowercase key without modifiers per step
        if (e.ctrlKey || e.metaKey || e.altKey) { cursor = 0; return; }
        const k = (e.key || "").toLowerCase();
        if (k === parts[cursor]) {
          cursor += 1;
          if (cursor === parts.length) {
            cursor = 0;
            clearTimeout(seqTimer);
            e.preventDefault();
            cbRef.current?.(e);
          } else {
            clearTimeout(seqTimer);
            seqTimer = setTimeout(() => { cursor = 0; }, 1500);
          }
        } else {
          cursor = 0;
        }
        return;
      }
      // combo
      const wanted = normalizeCombo(binding);
      if (eventCombo(e) === wanted) {
        e.preventDefault();
        cbRef.current?.(e);
      }
    };

    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
      clearTimeout(seqTimer);
    };
  }, [binding, ...deps]);
}

export const HOTKEY_META = IS_MAC ? "⌘" : "Ctrl";
