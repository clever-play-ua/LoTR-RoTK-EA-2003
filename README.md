# LoTR-RoTK-EA-2003

Reverse-engineering and Ukrainian localization work for *The Lord of the
Rings: The Return of the King* (EA Redwood Shores, 2003, PC).

## Quick start: editing the game's UI text

You need a copy of `GlobScen.scw` from a **single-language regional
install** (e.g. the Russian retail release) — see "Which install to use"
below if you're not sure which one you have.

```bash
# 1. See what's inside a .scw
python lotr_scw_tool.py list "C:\...\Data\Game\GlobScen.scw"

# 2. Pull the UI text table out to a plain text file
python lotr_scw_tool.py extract-subt "C:\...\Data\Game\GlobScen.scw" strings.txt

# 3. Edit strings.txt (it's just "key = value" lines, one per string) --
#    change the values, don't touch the keys or their order.

# 4. Write the translated strings back into a NEW copy of the archive
#    (the original is never modified):
python lotr_scw_tool.py inject-subt "C:\...\Data\Game\GlobScen.scw" strings.txt GlobScen_new.scw

# 5. Copy GlobScen_new.scw over the game's Data/Game/GlobScen.scw to test in-game
#    (back up the original first).
```

No dependencies beyond Python 3 (stdlib only). Full API and format
documentation is in `lotr_scw_tool.py`'s module docstring — read it before
extending the tool, it explains the container format field-by-field.

If a translation ends up **significantly longer** than the source text on
average, `inject-subt` can fail with a "won't fit" error — that's expected
(see the tool's docstring for why) and not a bug to route around silently.

## Which install to use

This project only works with `.scw` files whose `subT` (UI text) resource
is stored **uncompressed**. In practice that means:

- ✅ A regional single-language retail/pirate release (e.g. Russian) —
  these were repacked by the localization team without compression.
- ✅ Any `.scw` you already rebuilt with `lotr_scw_tool.py` (it always
  writes uncompressed).
- ❌ The pristine international/master build (ships all 9 languages in one
  **compressed** table) -- `lotr_scw_tool.py` will refuse this with
  `UnsupportedCompressionError` rather than produce garbage. This is a
  known, currently-unsolved limitation -- see
  `TODO_MASTER_SUBT_DECOMPRESSION.md` if you want to pick that up.

Run `python lotr_scw_tool.py list <file.scw>` first if you're not sure --
it always works (it only reads headers), and will tell you what's inside
either way.

## Repo layout

| File | What it is |
|---|---|
| `lotr_scw_tool.py` | The actual, tested tool. Lists/extracts/injects `.scw` resources; dedicated `subT` (UI text) read/write pipeline. Start here. |
| `FONT_LOCALIZATION_EN.md` / `FONT_LOCALIZATION_UK.md` | Full writeup of the `.font` (FNTS) glyph format, the Cyrillic/Ukrainian glyph-patching techniques that worked, and the rebuild pipeline used to ship the Ukrainian font patch. English and Ukrainian versions of the same document. |
| `AUDIO_INVESTIGATION_EN.md` | Status report on trying to extract/decode in-game dialogue audio. Container format solved, codec identified (EA MicroTalk), but the compression layer between stored bytes and the decoder is **unsolved**. Read this before re-attempting audio work -- several dead ends are already documented in detail. |
| `TODO_MASTER_SUBT_DECOMPRESSION.md` | Same kind of "unsolved, here's what's been tried" status report, but for decompressing the pristine master install's multi-language `subT` table (see "Which install to use" above). Shares a root cause with the audio problem -- both are blocked on the same unidentified EA compression scheme. |
| `GameExtractor.jar` | Vendored copy of the open-source **Game Extractor** tool. Its decompiled Java source (`org.watto.ge.plugin.*`) is the ground truth this whole project's `.scw`/`.font`/audio format understanding is built from -- always trust a fresh decompile of it over notes in any of the `.md` files here if they disagree. See "Re-deriving the format from source" below. |

## Re-deriving the format from source

Whenever something in the `.md` docs doesn't match reality, don't guess --
decompile the real tool and read what it actually does:

```bash
curl -sL -o cfr.jar https://github.com/leibnitz27/cfr/releases/download/0.152/cfr-0.152.jar
unzip -o GameExtractor.jar "org/watto/ge/plugin/archive/Plugin_SCW.class" -d extracted/
java -jar cfr.jar extracted/org/watto/ge/plugin/archive/Plugin_SCW.class --outputdir decompiled/
```

Swap the class name for whatever plugin is relevant (`Plugin_SWVR_RVWS` for
the audio container, etc -- see `AUDIO_INVESTIGATION_EN.md` §1 for that
one). This is how the current, correct byte offsets in `lotr_scw_tool.py`
were found and validated -- earlier notes in this repo had a real,
undetected offset bug for a long time precisely because it was never
cross-checked this way.

## What's solved vs. still open

- ✅ `.scw` container format (chunk structure, uncompressed `SDAT` resources)
- ✅ `.font` glyph format, Cyrillic/Ukrainian glyph patching
- ✅ `subT` UI text table, read and write, for uncompressed installs
- ❌ EA's proprietary compression (`Rdat` chunks / the audio codec's byte
  stream) -- blocks both the pristine multi-language `subT` table and
  in-game dialogue audio extraction. This is the one open problem shared
  by `TODO_MASTER_SUBT_DECOMPRESSION.md` and `AUDIO_INVESTIGATION_EN.md`.
