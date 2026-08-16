#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lotr_scw_tool.py
================

Reverse-engineered toolkit for the `.scw` archive format used by
*The Lord of the Rings: The Return of the King* (EA Redwood Shores, 2003, PC).

`.scw` files are the game's asset containers. `GlobScen.scw` (in `Data/Game/`)
holds the shared UI text table (`subT`), fonts (`.font`), and other global
assets. Per-level archives (e.g. `bla01.scw`) hold that level's audio/video.

This module gives you two independent layers:

1. **Container layer** (`list_resources`, `read_resource`, `write_resource`) —
   generic: walk any `.scw`, list every embedded resource, read one out,
   or write a same-footprint replacement back in. Works for ANY resource
   type (`font`, `subT`, `Cact`, `atbl`, `HUDs`, ...) as long as it is
   stored **uncompressed** (see "Known limitation" below).

2. **subT layer** (`parse_subt`, `build_subt`, `extract_subt_to_text`,
   `inject_text_into_subt`) — specific to the `subT` resource, which holds
   the game's localizable UI strings as `key = value` pairs. This is the
   piece you actually want if your goal is "translate the game's text".

--------------------------------------------------------------------------
HOW THE `.scw` CONTAINER IS LAID OUT
--------------------------------------------------------------------------

All 4-byte chunk tags are stored **byte-reversed** on disk, e.g. the tag
that means "SHDR" when read forward is literally the bytes `R D H S` on
disk. This was confirmed both by manual reverse-engineering and by
decompiling `org.watto.ge.plugin.archive.Plugin_SCW` from the open-source
tool **Game Extractor** (watto.org) — that plugin is the ground truth this
module is built from; if something here disagrees with the game's actual
behaviour, trust a fresh decompile of that plugin over this file.

The file is a flat sequence of chunks, read start to end:

  FILL  (on disk: "LLIF")
      Padding chunk. Its own 8-byte header (tag + length) says how many
      bytes to skip; these chunks appear whenever the writer needed to
      pad up to a 65536-byte boundary. Just skip `length` bytes and move on.

  SHOC / SONO  (on disk: "COHS" / "ONOS")
      A single "physical" chunk. Byte layout, all offsets relative to
      where this chunk's own 4-byte tag begins:

        [0:4)   tag ("COHS" or "ONOS")
        [4:8)   chunk length, little-endian uint32 -- INCLUDES this
                8-byte header, i.e. "next chunk starts at this_offset + length"
        [8:16)  8 reserved bytes, always skipped
        [16:20) file-header tag: "RDHS" (SHDR) / "TADS" (SDAT) / "tadR" (Rdat)

      What follows depends on that file-header tag:

        SHDR (on disk "RDHS") -- marks the START of a new resource.
              [20:24) reserved, skipped
              [24:28) ext, reversed (e.g. "subT", "font")
              [28:32) reserved, skipped
              [32:36) decompLen, little-endian uint32 -- total decompressed
                      size of this resource, summed across every chunk that
                      belongs to it
              (rest of this SHOC chunk is padding/reserved, ignore it)
            The chunk chain for the resource itself starts wherever THIS
            SHOC chunk ends (this_offset + length from field [4:8) above),
            and continues until `decompLen` bytes have been collected.

        SDAT (on disk "TADS") -- one **uncompressed** slice of resource
            data. Payload starts at byte offset 64 (relative to this
            chunk's own start) and runs to the end of the chunk -- i.e.
            `chunk_length - 64` bytes, stored exactly as decompressed,
            no decompression needed.

        Rdat (on disk "tadR") -- one **compressed** slice of resource
            data. Same as SDAT, except there is one more 4-byte
            little-endian uint32 at offset 64 -- the TRUE decompressed
            length of just this slice (larger than what's actually
            stored) -- pushing the real payload start to offset 68. The
            compression scheme used here has **not** been cracked (see
            "Known limitation" below) -- this tool refuses to read Rdat
            chunks rather than silently return garbage.

  Anything else at top level (STOC, CTRL, PADD, SWVR, ...) belongs to
  other resource kinds this module doesn't care about (audio, mostly) --
  they are skipped, not parsed.

--------------------------------------------------------------------------
KNOWN LIMITATION: Rdat (compressed) chunks are NOT supported
--------------------------------------------------------------------------

EA's regional single-language re-releases (e.g. the Russian retail build)
were repacked by the localization team using plain SDAT chunks -- no
compression, one language only. That is the case this module handles.

The pristine international/master build ships every language's text in
ONE `subT` resource, using Rdat (compressed) chunks. Decompressing those
requires cracking EA's proprietary compression, whose sample bytes start
with a byte pattern (`0x88`) that also blocks the *audio* format used by
this same game (documented at length, unsolved, in
`AUDIO_INVESTIGATION_EN.md` in this repo). If `read_resource()` hits an
Rdat chunk it raises `UnsupportedCompressionError` instead of guessing.

Practical upshot: point this tool at an SDAT-based `.scw` (a regional
single-language repack, or a `.scw` you already rebuilt with this same
tool) -- not at a pristine multi-language master build.

--------------------------------------------------------------------------
THE `subT` RESOURCE ITSELF (once you have its raw decompressed bytes)
--------------------------------------------------------------------------

`subT` is a tiny hand-rolled key/value string table, cp1251-encoded
(regardless of which language actually occupies it -- Cyrillic text in
this codepage covers both Russian and Ukrainian without a substitution
table). Layout:

  bytes [0:36)      36-byte header. Only two fields matter for rebuilding:
                      offset 4, uint32 LE -- pair_count (usually 768)
                    The remaining header bytes (version stamp, a 4-byte
                    ASCII language-code tag like b"ENG\\0", and some
                    constant-looking padding) are NOT recomputed by this
                    tool -- they're copied verbatim from the source file,
                    which is both simpler and safer than guessing what a
                    field none of us has decoded actually means.

  bytes [36 : 36 + pair_count*8)
                    Offset table: `pair_count` pairs of
                    (key_offset, value_offset), each a uint32 LE, each
                    relative to `base` (see next field). So this table is
                    `pair_count * 2` uint32s = `pair_count * 8` bytes.

  base = 36 + pair_count*8
                    Where the actual string blob starts.

  bytes [base : EOF)
                    The blob: every key and value is a cp1251-encoded,
                    NUL-terminated string, referenced by the offsets
                    above (relative to `base`). Order of appearance in
                    the blob does not need to match table order, and in
                    practice it doesn't -- always resolve through the
                    offset table, never assume sequential layout.

--------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------

As a library:

    from lotr_scw_tool import (
        list_resources, extract_subt_to_text, inject_text_into_subt,
    )

    # see what's inside a .scw
    for res in list_resources(r"C:\...\GlobScen.scw"):
        print(res)

    # pull the UI text table out to a plain-text file you can translate
    extract_subt_to_text(r"C:\...\GlobScen.scw", "strings.txt")

    # ... edit strings.txt by hand (or script it), keeping the same
    # "key = value" format and the same set of keys, then:

    inject_text_into_subt(
        r"C:\...\GlobScen.scw",       # original archive (read-only)
        "strings_translated.txt",     # your edited key = value file
        r"C:\...\GlobScen_new.scw",   # output copy with the new text
    )

From the command line:

    python lotr_scw_tool.py list GlobScen.scw
    python lotr_scw_tool.py extract-subt GlobScen.scw strings.txt
    python lotr_scw_tool.py inject-subt GlobScen.scw strings_ua.txt GlobScen_ua.scw

--------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

# --------------------------------------------------------------------------
# Container-level constants
# --------------------------------------------------------------------------

# On-disk (byte-reversed) chunk tags. Comments show the "true" name.
TAG_FILL = b"LLIF"  # = "FILL", padding chunk (pads to the next 65536-byte boundary)
TAG_SHOC = b"COHS"  # = "SHOC", the only physical-chunk wrapper we handle
TAG_SONO = b"ONOS"  # on-disk (reversed) form of "SONO", an audio variant of the same wrapper as SHOC

FH_SHDR = b"RDHS"  # = "SHDR", starts a new resource
FH_SDAT = b"TADS"  # = "SDAT", uncompressed payload slice
FH_RDAT = b"tadR"  # = "Rdat", COMPRESSED payload slice (unsupported, see module docstring)

# Byte offsets, relative to the start of a SHOC/SONO chunk (i.e. relative to
# where its 4-byte tag begins), confirmed against a decompile of
# org.watto.ge.plugin.archive.Plugin_SCW:
#   [0:4)   tag ("COHS"/"ONOS")
#   [4:8)   chunk length, little-endian uint32, INCLUDES this 8-byte header
#   [8:16)  8 reserved bytes (always skipped, never read)
#   [16:20) file-header tag: "RDHS" (SHDR) / "TADS" (SDAT) / "tadR" (Rdat)
# From there, only the SHDR case reads more fixed fields:
#   [20:24) reserved (skipped)
#   [24:28) ext, reversed (e.g. "font", "subT")
#   [28:32) reserved (skipped)
#   [32:36) decompLen, little-endian uint32 -- total decompressed size of
#           this resource across every chunk in its chain
_FILE_HEADER_OFFSET = 16
_SHDR_EXT_OFFSET = 24
_SHDR_DECOMPLEN_OFFSET = 32

# SDAT/Rdat payload prefix, relative to chunk start: the 16 bytes above,
# plus 4 more reserved bytes, plus 44 reserved bytes = 64 total before an
# SDAT chunk's raw payload begins. An Rdat chunk has one extra 4-byte field
# (its true decompressed length) before ITS payload, hence 68.
_SDAT_PAYLOAD_PREFIX = 64
_RDAT_PAYLOAD_PREFIX = 68

# Every top-level chunk we don't otherwise care about -- CTRL, STOC, SWVR
# (audio filename markers), PADD, and anything unrecognised -- has the
# same shape as far as *skipping past it* goes: a 4-byte tag, then a
# 4-byte little-endian length that counts the WHOLE chunk including that
# 8-byte header. So "next chunk starts at pos + length" uniformly, no
# per-type special-casing needed (confirmed against a decompile of
# org.watto.ge.plugin.archive.Plugin_SCW -- its SWVR/CTRL/STOC branches
# all resolve to exactly this same offset arithmetic once you trace
# through their internal skip()/relativeSeek() calls, even the SWVR
# "read the filename" case, since readNullString() consumes precisely
# the remaining bytes of that chunk).
_SKIPPABLE_TOP_LEVEL_TAGS = {b"LRTC", b"COTS", b"RVWS", b"DDAP"}  # CTRL, STOC, SWVR, PADD


class UnsupportedCompressionError(RuntimeError):
    """Raised when a resource's chunk chain contains an Rdat (compressed)
    slice. This tool intentionally does not attempt to decompress it --
    see the "Known limitation" section of the module docstring."""


class ScwFormatError(RuntimeError):
    """Raised when the container doesn't parse the way this module expects
    (unknown chunk tag where SHOC/SONO/FILL was required, truncated file,
    etc). Means either the file isn't a `.scw` this tool understands, or
    the reverse-engineered layout above is incomplete for this file."""


@dataclass
class ResourceInfo:
    """One entry from `list_resources()` / what `read_resource()` needs.

    `shdr_pos` is the absolute byte offset of the resource's SHDR chunk
    (the "COHS...RDHS..." chunk) inside the .scw file -- pass it straight
    to `read_resource()` / `write_resource()`.
    """

    shdr_pos: int
    ext: str          # e.g. "font", "subT", "atbl" -- already un-reversed
    decomp_len: int    # total decompressed size across all chunks


# --------------------------------------------------------------------------
# Container layer
# --------------------------------------------------------------------------


def list_resources(scw_path_or_bytes) -> List[ResourceInfo]:
    """Scan an entire `.scw` file and return one ResourceInfo per resource
    (i.e. per SHDR chunk found), in file order.

    This only reads the resource *headers* -- it does not walk each
    resource's full chunk chain, so it works even for resources that use
    Rdat (compressed) chunks (those will just show up in the list; you'll
    get UnsupportedCompressionError only if you try to actually read one
    with `read_resource()`).
    """
    data = _as_bytes(scw_path_or_bytes)
    resources: List[ResourceInfo] = []
    pos = 0
    n = len(data)
    while pos + 4 <= n:
        tag = data[pos : pos + 4]
        if tag == TAG_FILL:
            pos += 4 + _padding_to_boundary(pos + 4, 65536)
            continue
        length = struct.unpack_from("<I", data, pos + 4)[0]
        if length == 0:
            # Only seen at true end-of-file padding; nothing left to parse.
            break
        if tag in (TAG_SHOC, TAG_SONO):
            file_header = data[pos + _FILE_HEADER_OFFSET : pos + _FILE_HEADER_OFFSET + 4]
            if file_header == FH_SHDR:
                ext_raw = data[pos + _SHDR_EXT_OFFSET : pos + _SHDR_EXT_OFFSET + 4]
                ext = ext_raw[::-1].decode("ascii", errors="replace").rstrip("\x00")
                decomp_len = struct.unpack_from("<I", data, pos + _SHDR_DECOMPLEN_OFFSET)[0]
                resources.append(ResourceInfo(shdr_pos=pos, ext=ext, decomp_len=decomp_len))
            pos += length
            continue
        # Everything else at top level -- CTRL, STOC, SWVR (audio filename
        # markers), PADD, and any tag we don't otherwise recognise -- is not
        # a resource boundary we care about, but is still just "a chunk with
        # an 8-byte tag+length header, total size = length". Skip straight
        # past it. See _SKIPPABLE_TOP_LEVEL_TAGS above for why this uniform
        # formula is safe even for SWVR's internal filename-reading branch.
        pos += length
    return resources


def _padding_to_boundary(offset: int, boundary: int) -> int:
    """Bytes needed to advance `offset` to the next multiple of `boundary`
    (0 if already aligned). Mirrors Plugin_SCW's calculatePadding()."""
    remainder = offset % boundary
    return 0 if remainder == 0 else boundary - remainder


def read_resource(scw_path_or_bytes, shdr_pos: int) -> bytes:
    """Read one resource's full decompressed payload, given the absolute
    file offset of its SHDR chunk (as returned by `list_resources()`).

    Raises UnsupportedCompressionError if any chunk in this resource's
    chain is Rdat (compressed) -- see module docstring.
    """
    data = _as_bytes(scw_path_or_bytes)
    segments = _read_segments(data, shdr_pos)
    return b"".join(data[start : start + length] for start, length in segments)


def write_resource(scw_bytearray: bytearray, shdr_pos: int, new_payload: bytes) -> None:
    """Overwrite a resource's payload **in place**, within its existing
    physical footprint in the file.

    This is a "capacity-checked" write, not a resize: the resource's
    on-disk chunk layout (how many chunks, how big each one is) is left
    completely untouched, because every other resource in the file is
    positioned relative to this one and there is no simple way to shift
    them. Concretely:

      - `new_payload` must be <= the resource's original total capacity
        (sum of its chunk payload sizes). Raises ValueError otherwise.
      - If `new_payload` is shorter, the leftover bytes at the end of the
        last chunk are zero-filled (harmless: the resource's own
        decompLen field, which we DO update, tells the game exactly how
        many bytes are real).
      - The SHDR chunk's decompLen field is updated to len(new_payload).

    `scw_bytearray` must be a mutable bytearray (not `bytes`) -- load the
    file with `bytearray(path.read_bytes())` and write it back out with
    `path.write_bytes(...)` once you're done.
    """
    segments = _read_segments(bytes(scw_bytearray), shdr_pos)
    capacity = sum(length for _, length in segments)
    if len(new_payload) > capacity:
        raise ValueError(
            f"new payload is {len(new_payload)} bytes but this resource's slot "
            f"only has room for {capacity} bytes (its on-disk chunk layout is "
            f"fixed-size -- see write_resource() docstring). Shorten the content "
            f"or extend this tool to grow the chunk chain."
        )
    padded = new_payload + b"\x00" * (capacity - len(new_payload))
    cursor = 0
    for start, length in segments:
        scw_bytearray[start : start + length] = padded[cursor : cursor + length]
        cursor += length
    struct.pack_into("<I", scw_bytearray, shdr_pos + _SHDR_DECOMPLEN_OFFSET, len(new_payload))


def _read_segments(data: bytes, shdr_pos: int) -> List[Tuple[int, int]]:
    """Walk a resource's chunk chain starting at its SHDR chunk and return
    the list of (payload_start, payload_len) byte ranges that make up its
    decompressed content, in order. Internal helper for read/write_resource.
    """
    if data[shdr_pos : shdr_pos + 4] not in (TAG_SHOC, TAG_SONO):
        raise ScwFormatError(f"no SHOC/SONO chunk at offset {shdr_pos}")
    if data[shdr_pos + _FILE_HEADER_OFFSET : shdr_pos + _FILE_HEADER_OFFSET + 4] != FH_SHDR:
        raise ScwFormatError(f"chunk at offset {shdr_pos} is not a SHDR (resource start)")
    decomp_len = struct.unpack_from("<I", data, shdr_pos + _SHDR_DECOMPLEN_OFFSET)[0]

    segments: List[Tuple[int, int]] = []
    collected = 0
    # The SHDR chunk itself only carries metadata -- the first payload
    # chunk starts wherever this SHOC chunk ends.
    shdr_chunk_len = struct.unpack_from("<I", data, shdr_pos + 4)[0]
    pos = shdr_pos + shdr_chunk_len

    while collected < decomp_len:
        tag = data[pos : pos + 4]
        if tag == TAG_FILL:
            pos += 4 + _padding_to_boundary(pos + 4, 65536)
            continue
        if tag not in (TAG_SHOC, TAG_SONO):
            raise ScwFormatError(
                f"expected SHOC/SONO/FILL continuing resource at offset {shdr_pos}, "
                f"found {tag!r} at {pos} ({collected}/{decomp_len} bytes collected)"
            )
        chunk_len = struct.unpack_from("<I", data, pos + 4)[0]
        file_header = data[pos + _FILE_HEADER_OFFSET : pos + _FILE_HEADER_OFFSET + 4]
        if file_header == FH_SDAT:
            payload_start = pos + _SDAT_PAYLOAD_PREFIX
            payload_len = chunk_len - _SDAT_PAYLOAD_PREFIX
        elif file_header == FH_RDAT:
            raise UnsupportedCompressionError(
                f"resource at offset {shdr_pos} contains a compressed (Rdat) chunk "
                f"at offset {pos} -- decompression is not implemented (see module "
                f"docstring, 'Known limitation'). This .scw is likely a pristine "
                f"multi-language master build; point this tool at a single-language "
                f"regional repack instead."
            )
        else:
            raise ScwFormatError(f"unexpected file-header tag {file_header!r} at offset {pos}")
        take = min(payload_len, decomp_len - collected)
        segments.append((payload_start, take))
        collected += take
        pos += chunk_len

    return segments


def _as_bytes(path_or_bytes) -> bytes:
    if isinstance(path_or_bytes, (bytes, bytearray)):
        return bytes(path_or_bytes)
    return Path(path_or_bytes).read_bytes()


def find_resource(scw_path_or_bytes, ext: str) -> ResourceInfo:
    """Convenience wrapper: find the first resource with the given
    extension (e.g. "subT", "font"). Raises LookupError if none found."""
    for res in list_resources(scw_path_or_bytes):
        if res.ext == ext:
            return res
    raise LookupError(f"no resource with ext={ext!r} found in this .scw")


# --------------------------------------------------------------------------
# subT layer
# --------------------------------------------------------------------------

_SUBT_HEADER_LEN = 36
_SUBT_PAIR_COUNT_OFFSET = 4  # uint32 LE, inside the 36-byte header
_SUBT_ENCODING = "cp1251"


def parse_subt(raw: bytes) -> Tuple[bytes, List[Tuple[str, str]]]:
    """Decode a subT resource's raw decompressed bytes into
    (header_bytes, [(key, value), ...]) in the same order as the file's
    own offset table.

    `header_bytes` is the 36-byte header verbatim -- pass it straight back
    into `build_subt()` when you rebuild the file; see the module
    docstring for why this tool doesn't try to recompute it.
    """
    header = raw[:_SUBT_HEADER_LEN]
    pair_count = struct.unpack_from("<I", header, _SUBT_PAIR_COUNT_OFFSET)[0]
    n_offsets = pair_count * 2
    offsets = struct.unpack_from(f"<{n_offsets}I", raw, _SUBT_HEADER_LEN)
    base = _SUBT_HEADER_LEN + n_offsets * 4

    pairs: List[Tuple[str, str]] = []
    for i in range(pair_count):
        key_off, val_off = offsets[2 * i], offsets[2 * i + 1]
        key = _read_cstr(raw, base + key_off)
        val = _read_cstr(raw, base + val_off)
        pairs.append((key, val))
    return header, pairs


def build_subt(header: bytes, pairs: List[Tuple[str, str]]) -> bytes:
    """Inverse of parse_subt(): rebuild a subT resource's raw bytes from
    a header (copied verbatim from the source file -- see parse_subt) and
    an ordered list of (key, value) pairs.

    Every distinct string (key or value) is written into the blob exactly
    once and reused via the offset table if it repeats -- this mirrors
    what the original files do (many keys share a value, e.g. several
    "cancel"-style buttons all pointing at the same translated word) and
    keeps the output close in spirit to the source format, though it is
    NOT required for correctness: writing every string separately would
    also produce a valid file, just a slightly larger one.
    """
    pair_count = len(pairs)
    header = bytearray(header)
    struct.pack_into("<I", header, _SUBT_PAIR_COUNT_OFFSET, pair_count)

    blob = bytearray()
    string_offsets: dict[str, int] = {}

    def blob_offset_for(s: str) -> int:
        if s not in string_offsets:
            string_offsets[s] = len(blob)
            blob.extend(s.encode(_SUBT_ENCODING))
            blob.append(0)
        return string_offsets[s]

    offset_table = []
    for key, val in pairs:
        offset_table.append(blob_offset_for(key))
        offset_table.append(blob_offset_for(val))

    out = bytearray()
    out.extend(header)
    out.extend(struct.pack(f"<{len(offset_table)}I", *offset_table))
    out.extend(blob)
    return bytes(out)


def _read_cstr(data: bytes, start: int) -> str:
    end = data.index(b"\x00", start)
    return data[start:end].decode(_SUBT_ENCODING)


def extract_subt_to_text(scw_path, out_txt_path) -> int:
    """Full pipeline: find the subT resource in `scw_path`, decode it, and
    write it out as a plain-text `key = value` file (UTF-8), one pair per
    line, in the file's own key order. Returns the number of pairs written.

    This is the format you hand-translate (or script-translate) before
    calling `inject_text_into_subt()`.
    """
    res = find_resource(scw_path, "subT")
    raw = read_resource(scw_path, res.shdr_pos)
    _, pairs = parse_subt(raw)
    lines = [f"{key} = {val}" for key, val in pairs]
    Path(out_txt_path).write_text("\n".join(lines), encoding="utf-8")
    return len(pairs)


def parse_text_pairs(txt_path) -> List[Tuple[str, str]]:
    """Read a `key = value` text file (the format extract_subt_to_text()
    produces) back into an ordered list of (key, value) tuples.

    Splits on the FIRST " =" only, so values are free to contain their own
    " = " substrings without breaking the parse. The value's single leading
    space (from the " = " separator) is stripped if present, but no more --
    this also accepts an empty value written as "key =" with nothing after
    it (some entries genuinely translate to nothing, e.g. `device =`).
    """
    pairs = []
    for line in Path(txt_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        key, sep, rest = line.partition(" =")
        if not sep:
            raise ValueError(f"line does not match 'key = value': {line!r}")
        val = rest[1:] if rest.startswith(" ") else rest
        pairs.append((key, val))
    return pairs


def inject_text_into_subt(scw_path, translated_txt_path, out_scw_path) -> None:
    """Full pipeline: take a `.scw`, replace its subT resource's content
    with the translated `key = value` text file, and write the result to
    `out_scw_path` (the original file is never modified).

    Safety checks performed before anything is written:
      - the translated file's key set and order must exactly match the
        original subT's key set and order (a translation should only
        ever change values, never add/remove/reorder keys -- if it does,
        that's almost certainly a bug in how the translated file was
        produced, not something to silently paper over).
      - the rebuilt subT must fit within the original resource's on-disk
        capacity (see write_resource() docstring) -- if your translation
        is longer than the source language on average, this can fail;
        there is currently no support for growing a resource's footprint.
    """
    scw_path = Path(scw_path)
    data = bytearray(scw_path.read_bytes())

    res = find_resource(bytes(data), "subT")
    original_header, original_pairs = parse_subt(read_resource(bytes(data), res.shdr_pos))
    original_keys = [k for k, _ in original_pairs]

    translated_pairs = parse_text_pairs(translated_txt_path)
    translated_keys = [k for k, _ in translated_pairs]

    if translated_keys != original_keys:
        missing = set(original_keys) - set(translated_keys)
        extra = set(translated_keys) - set(original_keys)
        reordered = missing == set() and extra == set()
        detail = "keys are reordered" if reordered else f"missing={sorted(missing)[:10]} extra={sorted(extra)[:10]}"
        raise ValueError(
            f"translated file's keys don't exactly match the original subT's "
            f"keys/order ({detail}). Refusing to inject -- fix the translated "
            f"file rather than have this silently corrupt the key table."
        )

    new_subt = build_subt(original_header, translated_pairs)
    write_resource(data, res.shdr_pos, new_subt)

    Path(out_scw_path).write_bytes(bytes(data))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_list(args: argparse.Namespace) -> None:
    for res in list_resources(args.scw):
        print(f"{res.shdr_pos:>10}  ext={res.ext:<8}  decompLen={res.decomp_len}")


def _cmd_extract_subt(args: argparse.Namespace) -> None:
    n = extract_subt_to_text(args.scw, args.out_txt)
    print(f"wrote {n} pairs to {args.out_txt}")


def _cmd_inject_subt(args: argparse.Namespace) -> None:
    inject_text_into_subt(args.scw, args.translated_txt, args.out_scw)
    print(f"wrote {args.out_scw}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1] if __doc__ else "")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list every resource in a .scw file")
    p_list.add_argument("scw")
    p_list.set_defaults(func=_cmd_list)

    p_extract = sub.add_parser("extract-subt", help="dump the subT string table to a text file")
    p_extract.add_argument("scw")
    p_extract.add_argument("out_txt")
    p_extract.set_defaults(func=_cmd_extract_subt)

    p_inject = sub.add_parser("inject-subt", help="write a translated text file back into a copy of the .scw")
    p_inject.add_argument("scw", help="original .scw (not modified)")
    p_inject.add_argument("translated_txt", help="key = value file with translated values")
    p_inject.add_argument("out_scw", help="path to write the new .scw to")
    p_inject.set_defaults(func=_cmd_inject_subt)

    args = parser.parse_args()
    try:
        args.func(args)
    except (UnsupportedCompressionError, ScwFormatError, ValueError, LookupError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
