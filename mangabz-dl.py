#!/usr/bin/env python3
# MIT License
#
# Copyright (c) 2025 zhengxyz123
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import argparse
import os
import re
import shutil
import sys
import textwrap
from pathlib import Path
from random import choice
from subprocess import PIPE, Popen
from typing import NamedTuple

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

# Unpacker for Dean Edward's p.a.c.k.e.r, a part of javascript beautifier
# by Einar Lielmanis <einar@beautifier.io>
# written by Stefano Sanfilippo <a.little.coder@gmail.com>


class UnpackingError(Exception):
    """Badly packed source or general error. Argument is a meaningful description."""

    pass


def unpack(source: str) -> str:
    """Unpack P.A.C.K.E.R packed js code."""
    mystr = re.search(
        r"eval[ ]*\([ ]*function[ ]*\([ ]*p[ ]*,[ ]*a[ ]*,[ ]*c["
        " ]*,[ ]*k[ ]*,[ ]*e[ ]*,[ ]*",
        source,
    )
    if mystr is None:
        raise UnpackingError("not a P.A.C.K.E.R code")

    begin_offset = mystr.start()
    beginstr = source[:begin_offset]
    source_end = source[begin_offset:]
    if source_end.split("')))", 1)[0] == source_end:
        try:
            endstr = source_end.split("}))", 1)[1]
        except IndexError:
            endstr = ""
    else:
        endstr = source_end.split("')))", 1)[1]
    payload, symtab, radix, count = _filterargs(source)

    if count != len(symtab):
        raise UnpackingError("malformed P.A.C.K.E.R symtab")

    try:
        unbase = Unbaser(radix)
    except TypeError:
        raise UnpackingError("unknown P.A.C.K.E.R encoding")

    def lookup(match):
        """Look up symbols in the synthetic symtab."""
        word = match.group(0)
        return symtab[unbase(word)] or word

    payload = payload.replace("\\\\", "\\").replace("\\'", "'")
    source = re.sub(r"\b\w+\b", lookup, payload, flags=re.ASCII)
    return _replacestrings(source, beginstr, endstr)


def _filterargs(source: str) -> tuple[str, list[str], int, int]:
    """Juice from a source file the four args needed by decoder."""
    juicers = [
        (r"}\('(.*)', *(\d+|\[\]), *(\d+), *'(.*)'\.split\('\|'\), *(\d+), *(.*)\)\)"),
        (r"}\('(.*)', *(\d+|\[\]), *(\d+), *'(.*)'\.split\('\|'\)"),
    ]
    for juicer in juicers:
        args = re.search(juicer, source, re.DOTALL)
        if args:
            a = args.groups()
            if a[1] == "[]":
                a = list(a)
                a[1] = 62
                a = tuple(a)
            try:
                return a[0], a[3].split("|"), int(a[1]), int(a[2])
            except ValueError:
                raise UnpackingError("corrupted P.A.C.K.E.R data")

    # Could not find a satisfying regex
    raise UnpackingError(
        "could not make sense of P.A.C.K.E.R data (unexpected code structure)"
    )


def _replacestrings(source: str, beginstr: str, endstr: str) -> str:
    """Strip string lookup table (list) and replace values in source."""
    match = re.search(r'var *(_\w+)\=\["(.*?)"\];', source, re.DOTALL)

    if match:
        varname, strings = match.groups()
        startpoint = len(match.group(0))
        lookup = strings.split('","')
        variable = "%s[%%d]" % varname
        for index, value in enumerate(lookup):
            source = source.replace(variable % index, '"%s"' % value)
        return source[startpoint:]
    return beginstr + source + endstr


class Unbaser(object):
    """Functor for a given base. Will efficiently convert strings to natural numbers."""

    ALPHABET = {
        62: "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
        95: (
            " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
        ),
    }

    def __init__(self, base: int) -> None:
        self.base = base

        # Fill elements 37...61, if necessary
        if 36 < base < 62:
            if not hasattr(self.ALPHABET, self.ALPHABET[62][:base]):
                self.ALPHABET[base] = self.ALPHABET[62][:base]
        # If base can be handled by int() builtin, let it do it for us
        if 2 <= base <= 36:
            self.unbase = lambda string: int(string, base)
        else:
            # Build conversion dictionary cache
            try:
                self.dictionary = dict(
                    (cipher, index) for index, cipher in enumerate(self.ALPHABET[base])
                )
            except KeyError:
                raise TypeError("unsupported base encoding")

            self.unbase = self._dictunbaser

    def __call__(self, string: str) -> int:
        return self.unbase(string)

    def _dictunbaser(self, string: str) -> int:
        """Decode a value to an integer."""
        ret = 0
        for index, cipher in enumerate(string[::-1]):
            ret += (self.base**index) * self.dictionary[cipher]
        return ret


user_agents = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0",
    "Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 OPR/118.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.3124.85",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.7; rv:136.0) Gecko/20100101 Firefox/136.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 OPR/118.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.3124.85",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 OPR/118.0.0.0",
]


class ChapterInfo(NamedTuple):
    href: str
    title: str


class MangaInfo(NamedTuple):
    title: str
    chapters: list[ChapterInfo]


def parse_range(string: str, info: MangaInfo) -> list[int]:
    """Parse comma separated string to a list.

    `[start]-[end]` presents a range.

    For example:

    ```python
    parse_range("1", ...) == [1]
    parse_range("1,2", ...) == [2]
    parse_range("1-5", ...) == [1, 2, 3, 4, 5]
    parse_range("1-5,7-10", ...) == [1, 2, 3, 4, 5, 7, 8, 9, 10]
    ```
    """
    if len(string) == 0:
        return list(range(len(info.chapters)))
    result = []
    for part in string.split(","):
        if "-" in part:
            hyphen = part.find("-")
            for i in range(int(part[:hyphen]), int(part[hyphen + 1 :]) + 1):
                if i not in result:
                    result.append(i)
        else:
            if (i := int(part)) not in result:
                result.append(i)
    result = [i - 1 for i in result if 1 <= i <= len(info.chapters)]
    return sorted(result)


def find_mangabz_var(name: str, string: str) -> str:
    """Find a variable named `name` in javascript `string`."""
    start = string.find(f"var {name}")
    a = string.find("=", start) + 1
    b = string.find(";", start)
    return string[a:b].strip(" '\"")


def get_manga_info(
    session: requests.Session, manga: str, is_chapter: bool = False
) -> MangaInfo:
    """Get manga metadata."""
    response = session.get(f"https://mangabz.com/{manga}/")
    response.raise_for_status()
    dom = BeautifulSoup(response.text, features="html.parser")
    if is_chapter:
        manga_title = find_mangabz_var("MANGABZ_CTITLE", response.text)
    else:
        manga_title = dom.select("p.detail-info-title")[0].text.strip()
    chap_list: list[ChapterInfo] = []
    if is_chapter:
        chap_list.append(ChapterInfo(manga, manga_title))
    else:
        for node in dom.select("a.detail-list-form-item"):
            title, _ = [s for s in node.stripped_strings]
            info = ChapterInfo(node.attrs["href"][1:-1], title)  # type: ignore
            chap_list.append(info)
    return MangaInfo(manga_title, chap_list[::-1])


def list_chapters(info: MangaInfo) -> None:
    """List all chapters using `less` (or other program defined in `$PAGER`).

    Output format like:

    ```
    index: chapter name (chapter id)
    ```
    """
    pager = shutil.which(os.environ.get("PAGER", "less"))
    has_pager = pager is not None
    if not sys.stdout.isatty():
        has_pager = False
    num_width = len(str(len(info.chapters)))
    if not has_pager:
        for n, chap in enumerate(info.chapters):
            print(
                "{0:{width}}: {1} ({2})".format(
                    n + 1, chap.title, chap.href, width=num_width
                )
            )
    else:
        with Popen(pager, stdin=PIPE, universal_newlines=True) as proc:  # type: ignore
            for n, chap in enumerate(info.chapters):
                proc.stdin.write(
                    "{0:{width}}: {1} ({2})\n".format(
                        n + 1, chap.title, chap.href, width=num_width
                    )
                )


def download_manga(
    session: requests.Session, info: MangaInfo, index: int, is_chapter: bool = False
) -> None:
    """Download manga and save it in a specific directory."""
    response = session.get(f"https://mangabz.com/{info.chapters[index].href}/")
    response.raise_for_status()
    mid = find_mangabz_var("COMIC_MID", response.text)
    cid = find_mangabz_var("MANGABZ_CID", response.text)
    viewsign = find_mangabz_var("MANGABZ_VIEWSIGN", response.text)
    viewsign_dt = find_mangabz_var("MANGABZ_VIEWSIGN_DT", response.text)
    total_pages = int(find_mangabz_var("MANGABZ_IMAGE_COUNT", response.text))

    print(f"Downloading {info.chapters[index].title!r}...")
    if is_chapter:
        save_dir = Path(info.title)
    else:
        save_dir = Path(info.title) / info.chapters[index].title
    save_dir.mkdir(parents=True, exist_ok=True)
    num_width = len(str(total_pages))
    now_page = 0
    bar = tqdm(total=total_pages)
    while now_page < total_pages:
        code = session.get(
            f"https://mangabz.com/{info.chapters[index].href}/chapterimage.ashx",
            params={
                "cid": cid,
                "page": now_page + 1,
                "key": "",
                "_cid": cid,
                "_mid": mid,
                "_dt": viewsign_dt,
                "_sign": viewsign,
            },
            headers={"Referer": f"https://mangabz.com/{info.chapters[index].href}/"},
        )
        code.raise_for_status()
        unpack_code = unpack(code.text)
        pix = re.search(r'pix="(.*?)"', unpack_code).group(1)
        suffix = re.search(r"pix\+pvalue\[i\]\+'(.*?)'", unpack_code).group(1)
        pvalue = re.findall(r'"(/.*?\.jpg)"', unpack_code)
        for url in [(pix + p + suffix) for p in pvalue]:
            now_page += 1
            save_file = save_dir / "{0:0{width}}.jpg".format(now_page, width=num_width)
            with open(save_file, "wb+") as f:
                pic = session.get(url, headers={"Referer": "https://mangabz.com/"})
                pic.raise_for_status()
                f.write(pic.content)
            bar.update(1)
    bar.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="A Python tool for downloading manga from Mangabz."
    )
    parser.add_argument(
        "-l",
        "--language",
        choices=["zh_sim", "zh_tra"],
        default="zh_sim",
        help=textwrap.dedent(
            """\
                website language
                ('zh_sim' for Simplified Chinese, 'zh_tra' for Traditional Chinese)
            """
        ),
    )
    parser.add_argument(
        "-r",
        "--range",
        default="",
        help=textwrap.dedent(
            """\
                comma separated index of chapters to download;
                using '[start]-[end]' to specify a range;
                e.g. '1', '1,2', '1-10', '1,3-10' and '1-5,7-10';
                using -c/--chapters option to see chapter index
            """
        ),
    )
    parser.add_argument(
        "-c",
        "--chapters",
        action="store_true",
        help=textwrap.dedent(
            """\
                list chapters and exit,
                output format is 'index: chapter name (chapter id)'
            """
        ),
    )
    parser.add_argument(
        "manga_or_chapter",
        help="manga (whose prefix is 'bz') or chapter (whose suffix is 'm') id",
    )
    args = parser.parse_args()

    session = requests.Session()
    session.headers["User-Agent"] = choice(user_agents)
    if args.language == "zh_tra":
        session.cookies["mangabz_lang"] = "1"
    else:
        session.cookies["mangabz_lang"] = "2"

    if args.manga_or_chapter.endswith("bz"):
        is_chapter = False
        manga_info = get_manga_info(session, args.manga_or_chapter)
    elif args.manga_or_chapter.startswith("m"):
        is_chapter = True
        manga_info = get_manga_info(
            session, args.manga_or_chapter, is_chapter=is_chapter
        )
    else:
        print(f"invalid manga or chapter id: {args.manga_or_chapter!r}")
        return 1

    if args.chapters:
        list_chapters(manga_info)
        return 0

    if is_chapter:
        chap_range = [0]
    else:
        chap_range = parse_range(args.range, manga_info)
    for n in chap_range:
        download_manga(session, manga_info, n, is_chapter=is_chapter)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as err:
        print(err.args[0])
        sys.exit(1)
    except KeyboardInterrupt:
        print("interrupted by user")
        sys.exit(1)
