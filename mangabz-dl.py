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
import shutil
import subprocess
import sys
import textwrap
from random import choice
from pathlib import Path
from subprocess import PIPE, Popen
from typing import NamedTuple

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

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
    if len(string) == 0:
        return list(range(len(info.chapters)))
    result = []
    for part in string.split(","):
        if "-" in part:
            hyphen = part.find("-")
            for i in range(int(part[:hyphen]), int(part[hyphen + 1 :]) + 1):
                if i not in result:
                    result.append(i)
        elif part.isdigit() and part.isdecimal():
            if int(part) not in result:
                result.append(int(part))
        else:
            raise ValueError(f"unknow range {part!r}")
    result = [i - 1 for i in result if 1 <= i <= len(info.chapters)]
    return sorted(result)


def find_mangabz_var(name: str, string: str) -> str:
    start = string.find(f"var {name}")
    a = string.find("=", start) + 1
    b = string.find(";", start)
    return string[a:b].strip(" '\"")


def get_manga_info(
    session: requests.Session, manga: str, is_chapter: bool = False
) -> MangaInfo:
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
        proc = subprocess.run(
            [
                "node",
                "-e",
                f"let ret={code.text};for(let line of ret){{console.log(line);}}",
            ],
            capture_output=True,
        )
        for url in proc.stdout.decode().splitlines():
            now_page += 1
            save_file = save_dir / "{0:0{width}}.jpg".format(now_page, width=num_width)
            with open(save_file, "wb+") as f:
                pic = session.get(url, headers={"Referer": "https://mangabz.com/"})
                pic.raise_for_status()
                f.write(pic.content)
            bar.update(1)
    bar.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="A Python tool for downloading manga from Mangabz.")
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
                using --chapters option to see chapter index
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
        manga_info = get_manga_info(session, args.manga_or_chapter, is_chapter=is_chapter)
    else:
        print(f"invalid manga or chapter id: {args.manga_or_chapter!r}")
        return 1

    if args.chapters:
        list_chapters(manga_info)
        return 0

    try:
        if is_chapter:
            chap_range = [0]
        else:
            chap_range = parse_range(args.range, manga_info)
    except Exception as err:
        print(f"range error: {err.args[0]}")
        return 1
    if shutil.which("node") is None:
        print(
            "Node.js is not found, you should download it from https://nodejs.org/en/download"
        )
        return 1
    for n in chap_range:
        download_manga(session, manga_info, n, is_chapter=is_chapter)
    return 0


if __name__ == "__main__":
    sys.exit(main())
