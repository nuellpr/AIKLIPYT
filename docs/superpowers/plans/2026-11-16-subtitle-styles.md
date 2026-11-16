# Subtitle Styles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five new subtitle styles (Hormozi, Karaoke, Gadzhi, MrBeast, Bilingual) to the existing ASS renderer, selectable from the same caption-style dropdown, with Bilingual translated via the existing AI chat endpoint.

**Architecture:** No new dependencies. The renderer already builds all captions as ASS override-tag recipes in `build_ass()`; extend that recipe set and dispatch. Bilingual needs translation text aligned to caption groups — produce it in `core/highlights.py` with one `chat()` call, thread it through `core/pipeline.py` into `build_ass(translations=...)`, and fail soft (single-layer) on AI error. Replace the duplicated style whitelist in `server.py` with the single shared tuple.

**Tech Stack:** Python 3.14 stdlib, ASS (Advanced SubStation Alpha) subtitle tags, existing OpenAI-compatible `chat()`, ffmpeg, unittest.

**Spec:** `docs/superpowers/specs/2026-11-16-subtitle-styles-design.md`

## Global Constraints

- No new dependencies. All styles are ASS override-tag recipes rendered by the existing ffmpeg path.
- Python **unittest** only (no pytest). Run: `.venv\Scripts\python.exe -m unittest discover -s tests`.
- All 53 existing tests must still pass after every task.
- Keep every existing style and its exact output byte-for-byte where not targeted (byte-identical for non-new styles).
- Bilingual translation target = `outputLanguage`, fallback `'en'` when the value is `'auto'`.
- Bilingual on AI failure: log via `on_log`, render single-layer (original only), never fail the whole render.
- `build_ass()` stays backward compatible: new `translations` param is optional and defaults to `None`.

## Review Focus

- `translations` shorter than the group list, or containing empty strings → extra groups must still render the original line; no IndexError, no blank translation event. Test: `test_bilingual_partial_translations` (Task 1).
- Karaoke timing with a single word / zero-duration word → `{\kf}` must be at least 1 centisecond; no divide-by-zero, no negative duration. Test: `test_karaoke_single_word_min_duration` (Task 1).
- Non-ASCII / brace characters in translated text → must be escaped via `ass_escape()` like all captions. Test: `test_bilingual_escapes_translation` (Task 1).
- `translate_groups` JSON shape wrong (object instead of array, count mismatch) → raise `AIError`, never return misaligned list. Tests: `test_translate_groups_rejects_wrong_count` and `test_translate_groups_rejects_non_array` (Task 2).
- Bilingual selected but AI unconfigured / offline → render must still finish single-layer. Test: `test_bilingual_translation_failure_is_soft` (Task 3).

---

### Task 1: Renderer styles + shared whitelist

**Files:**
- Modify: `core/render.py:33-43` (whitelist), `:23-26` (ASS header), `:112-131` (signature + fallback), `:150-198` (dispatch)
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: existing `Word`, `_groups()`, `_ass_color`, `_color_tag`, `ass_escape`, `ass_time`.
- Produces: `CAPTION_STYLES` tuple (14 names, public). `build_ass(..., translations: list[str] | None = None)`.

- [ ] **Step 1: Write the failing tests**

Add to `AssTests` in `tests/test_render.py`:

```python
from core.render import CAPTION_STYLES  # add to existing import line

def test_caption_styles_exposes_new_presets(self):
    for name in ("hormozi", "karaoke", "gadzhi", "mrbeast", "bilingual"):
        self.assertIn(name, CAPTION_STYLES)
    self.assertEqual(len(CAPTION_STYLES), 14)

def test_hormozi_style(self):
    ass = build_ass([Word("halo", 0.2, 0.7)], caption_style="hormozi")
    self.assertIn(r"\bord12", ass)
    self.assertIn("HALO", ass)  # uppercase

def test_karaoke_style(self):
    words = [Word("halo", 0.2, 0.7), Word("dunia", 0.8, 1.4)]
    ass = build_ass(words, caption_style="karaoke")
    self.assertIn(r"{\kf", ass)
    self.assertIn(r"\2c&H00FFFFFF&", ass)

def test_karaoke_single_word_min_duration(self):
    ass = build_ass([Word("halo", 0.2, 0.7)], caption_style="karaoke")
    self.assertIn(r"{\kf1}", ass)

def test_gadzhi_style(self):
    ass = build_ass([Word("halo", 0.2, 0.7)], caption_style="gadzhi")
    self.assertIn(r"\fnArial\b0", ass)
    self.assertIn(r"\bord1", ass)

def test_mrbeast_style(self):
    words = [Word("a", 0.1, 0.4), Word("b", 0.5, 0.8), Word("c", 0.9, 1.2)]
    ass = build_ass(words, caption_style="mrbeast")
    self.assertIn(r"\fscx120", ass)
    self.assertIn("A", ass)

def test_bilingual_renders_translation_above(self):
    words = [Word("halo", 0.2, 0.7)]
    ass = build_ass(words, "TONTON INI", "@kredit", 1.5, 2.0,
                    caption_style="bilingual", translations=["Halo!"])
    self.assertIn("halo", ass)
    self.assertIn("Halo!", ass)
    self.assertIn("CaptionAlt", ass)

def test_bilingual_partial_translations(self):
    words = [Word("a", 0.1, 0.4), Word("b", 0.5, 0.8), Word("c", 0.9, 1.2),
             Word("d", 1.3, 1.6), Word("e", 1.7, 2.0)]
    ass = build_ass(words, caption_style="bilingual", translations=["only"])
    self.assertNotIn("IndexError", ass)
    self.assertEqual(ass.count("Dialogue:") - 1, 5)  # 1 hook + 5 originals

def test_bilingual_escapes_translation(self):
    words = [Word("halo", 0.2, 0.7)]
    ass = build_ass(words, caption_style="bilingual", translations=["{evil\\pos(0,0)}"])
    self.assertNotIn("{evil", ass)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m unittest discover -s tests -v`
Expected: FAIL with `ImportError: cannot import name 'CAPTION_STYLES'` and unknown-style fallbacks.

- [ ] **Step 3: Implement in `core/render.py`**

1. Rename `_CAPTION_STYLES` → `CAPTION_STYLES` and append the 5 new names. Export `group_words = _groups` as a public alias right after `_groups` is defined (Task 3 imports it). Existing internal calls to `_groups` stay unchanged.
2. Add a `CaptionAlt` style line to `_ASS_HEADER` using Arial, smaller size and higher margin (add `alt_size`, `alt_margin` to the `.format()` call; derive from `portrait` like existing `caption_size`/`bottom_margin`).
3. Add `translations: list[str] | None = None` as the last `build_ass` parameter.
4. In the group loop, use `for group_index, group in enumerate(_groups(words)):`. Use local `style = "highlight" if caption_style == "bilingual" else caption_style` in the dispatch chain.
5. Add dispatch branches before the existing fallback:
   - `hormozi`: `base = r"{\bord12\3c&H000000&\shad2}"`; inactive `base + token.upper()`; active `_color_tag(accent) + r"{\fscx118\fscy118}" + token.upper() + r"{\rCaption}" + base`.
   - `gadzhi`: `base = r"{\fnArial\b0\bord1\shad0\3c&H000000&}"`; inactive `base + token`; active `_color_tag(accent) + base + token + r"{\rCaption}" + base`.
   - `mrbeast`: module-level `MRBEAST_COLORS` list of bright `&H00BBGGRR&` strings; `base = r"{\bord8\3c&HFFFFFF&\shad2}"`; color = `MRBEAST_COLORS[other_index % len(MRBEAST_COLORS)]`; inactive `base + token.upper()`; active `f"{{\\c{color}\\fscx120\\fscy120}}" + token.upper() + r"{\rCaption}" + base`.
   - `karaoke`: for each group build one Dialogue on `Caption`: prefix `r"{\2c&H00FFFFFF&}" + _color_tag(accent)`, then per word `r"{\kf" + str(max(1, int(round(((group[i+1].start - w.start) if i+1 < len(group) else (w.end - w.start)) * 100)))) + "}" + ass_escape(w.word)`, joined by spaces; end time `ass_time(group[-1].end + 0.12)`; `continue`.
   - After the main `events.append(...)` for a group, if `caption_style == "bilingual"` and `translations` and `group_index < len(translations)` and `translations[group_index].strip()`: append a second Dialogue with style `CaptionAlt`, same start/end, text `ass_escape(translations[group_index].strip())`.

Keep all existing branches unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m unittest discover -s tests -v`
Expected: PASS (all 53 existing + 9 new).

- [ ] **Step 5: Commit**

```bash
git add core/render.py tests/test_render.py
git commit -m "feat: add five subtitle style recipes to ASS renderer"
```

---

### Task 2: Translation helper

**Files:**
- Modify: `core/highlights.py` (after `chat`, ~line 328)
- Test: `tests/test_highlights.py`

**Interfaces:**
- Consumes: `chat(base_url, api_key, model, messages, timeout) -> tuple[str, dict]`, `AIError`, `_strip_fences()`.
- Produces: `translate_groups(texts: list[str], target: str, base_url: str, api_key: str, model: str, timeout: int = 60) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_highlights.py` (uses the same local-server pattern as `ChatTests`):

```python
def test_translate_groups_parses_json_array(self):
    # local server returns {"choices":[{"message":{"content":"[\"Halo\",\"Dunia\"]"}}]}
    out = translate_groups(["Hello", "World"], "Indonesian", base, "k", "m")
    self.assertEqual(out, ["Halo", "Dunia"])

def test_translate_groups_rejects_wrong_count(self):
    # server returns ["only one"]
    with self.assertRaises(AIError):
        translate_groups(["a", "b"], "Indonesian", base, "k", "m")

def test_translate_groups_rejects_non_array(self):
    # server returns {"wrong":"shape"}
    with self.assertRaises(AIError):
        translate_groups(["a"], "Indonesian", base, "k", "m")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m unittest discover -s tests -v`
Expected: FAIL with `ImportError: cannot import name 'translate_groups'`.

- [ ] **Step 3: Implement `translate_groups` in `core/highlights.py`**

Build a system message: "You translate short video caption lines. Reply with ONLY a JSON array of strings, same count and order as the input. No explanation." User message: `json.dumps({"target_language": target, "lines": texts}, ensure_ascii=False)`. Call `content, _ = chat(base_url, api_key, model, messages, timeout=timeout)`. Parse `json.loads(_strip_fences(content))`; if not a `list`, if any element is not `str`, or if `len != len(texts)`, raise `AIError`. Return the list (strip each element). Wrap parse failures in `AIError` with a clear message.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m unittest discover -s tests -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/highlights.py tests/test_highlights.py
git commit -m "feat: add translate_groups using existing AI chat"
```

---

### Task 3: Wire bilingual translation into the render pipeline

**Files:**
- Modify: `core/pipeline.py:17` (import), `:212-306` (`_render_worker`)
- Test: `tests/test_pipeline.py` (new file, unittest)

**Interfaces:**
- Consumes: `translate_groups(texts, target, base, key, model)` from Task 2; `group_words(words)` from `core.render` (Task 1, where `_groups` is exported under the public name `group_words` while keeping `_groups` as a backward-compatible alias).
- Produces: no new public API; `render_clip(..., translations=...)` call site.

- [ ] **Step 1: Write the failing test**

Create `tests/test_pipeline.py`:

```python
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.pipeline import _bilingual_translations  # noqa: E402
from core.subtitles import Word  # noqa: E402

class BilingualTranslationTests(unittest.TestCase):
    def test_builds_one_line_per_group_in_order(self):
        words = [Word("a", 0.1, 0.4), Word("b", 0.5, 0.8), Word("c", 3.0, 3.4)]
        seen = {}
        def fake(texts, target, base, key, model):
            seen["texts"] = texts
            return [f"T{i}" for i in range(len(texts))]
        out = _bilingual_translations(words, "Indonesian", "base", "key", "model", translate=fake)
        self.assertEqual(seen["texts"], ["a b", "c"])
        self.assertEqual(out, ["T0", "T1"])

    def test_ai_failure_returns_none(self):
        def boom(*a, **k):
            raise RuntimeError("offline")
        self.assertIsNone(_bilingual_translations([Word("a", 0.1, 0.4)], "id", "b", "k", "m", translate=boom))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m unittest discover -s tests -v`
Expected: FAIL with `ImportError: cannot import name '_bilingual_translations'`.

- [ ] **Step 3: Implement in `core/pipeline.py`**

1. Import `translate_groups` from `.highlights` and `CAPTION_STYLES` not needed.
2. In `core/render.py`, export `group_words = _groups` (one line, after `_groups` is defined) so pipeline can reuse the exact same grouping rule. Add `_bilingual_translations(words, target, base, key, model, translate=None) -> list[str] | None` that groups `words` via `group_words(words)`, joins each group's words with a space, calls `(translate or translate_groups)(lines, target, base, key, model)`, and returns the result; catches any `Exception` and returns `None`.
3. In `_render_worker`, after `clip_words = slice_words(...)` and before `render_clip(...)`, if `render_opts.get("captionStyle") == "bilingual"` and `clip_words`: compute `target = str(render_opts.get("outputLanguage") or config.get("outputLanguage") or "auto")`; if `target == "auto"` set `target = "en"`; resolve via `LANGUAGES.get(target, target)` (import `LANGUAGES`); call `_bilingual_translations(clip_words, target_name, base_url, key, model, translate=...)` using the credentials available in `_render_worker` (obtain with `from .secret import api_key` and `api_key(config)`, base/model from `config["ai"]`). Log the outcome via `on_log(job, ...)`. Pass `translations=translations` to `render_clip(...)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m unittest discover -s tests -v`
Expected: PASS (all existing + new).

- [ ] **Step 5: Commit**

```bash
git add core/render.py core/pipeline.py tests/test_pipeline.py
git commit -m "feat: translate bilingual captions before rendering"
```

---

### Task 4: Remove duplicated whitelist and expose styles in the UI

**Files:**
- Modify: `server.py:19-24,159-170`
- Modify: `web/index.html:347` (captionStyle select), `:362` (hint text)

**Interfaces:**
- Consumes: `CAPTION_STYLES` from `core.render` (Task 1).
- Produces: none.

- [ ] **Step 1: Write a failing test**

Add to `tests/test_server.py`:

```python
def test_all_caption_styles_are_accepted(self):
    from core.render import CAPTION_STYLES
    config = {"render": {"captionStyle": "bilingual"}}
    _normalize_caption_style(config)  # new shared helper in server.py
    self.assertEqual(config["render"]["captionStyle"], "bilingual")

def test_unknown_style_falls_back(self):
    config = {"render": {"captionStyle": "nonsense"}}
    _normalize_caption_style(config)
    self.assertEqual(config["render"]["captionStyle"], "highlight")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m unittest discover -s tests -v`
Expected: FAIL with `ImportError: cannot import name '_normalize_caption_style'`.

- [ ] **Step 3: Implement**

1. In `server.py`, add `from core.render import CAPTION_STYLES` and define `_normalize_caption_style(config) -> None` that sets `config["render"]["captionStyle"]` to `"highlight"` when its current value is not in `CAPTION_STYLES` (matching the in-place mutation pattern of the surrounding code). Replace the inline whitelist block (lines 159-170) with `_normalize_caption_style(config)`.
2. In `web/index.html`, add 5 `<option>` entries to `#captionStyle`: `hormozi`, `karaoke`, `gadzhi`, `mrbeast`, `bilingual`, with short Indonesian labels. Update the hint text to mention that Bilingual uses the AI endpoint and the output language setting.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m unittest discover -s tests -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server.py web/index.html tests/test_server.py
git commit -m "feat: expose subtitle styles in UI and dedupe style whitelist"
```

---

### Task 5: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full suite**

Run: `.venv\Scripts\python.exe -W error::ResourceWarning -m unittest discover -s tests -v`
Expected: PASS, no warnings.

- [ ] **Step 2: Smoke-test the UI**

Start `run.bat`, open `http://127.0.0.1:8765`, confirm the 5 new options appear in the caption-style dropdown and that selecting Bilingual does not error before a render job starts.

- [ ] **Step 3: Final commit if any fixups were needed**

Only if Step 1 or 2 found a problem: commit the fixup with an appropriate message.
