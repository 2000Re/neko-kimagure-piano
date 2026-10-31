"""同梱フォントをサブセット化する(リポジトリを軽く保つため)。

収録: ASCII・ラテン補助・一般記号・JIS X 0208の非漢字(かな・記号)・第1水準漢字。
フォントを差し替えるときだけローカルで実行する。要 fonttools。
使い方: python3 tools/subset_fonts.py <入力.otf/.ttc> <出力.otf> [--ttc-family "Noto Serif CJK JP"]
"""
import argparse

from fontTools import subset
from fontTools.ttLib import TTCollection, TTFont


def jis_level1_and_symbols():
    chars = set()
    for row in list(range(1, 9)) + list(range(16, 48)):  # 1〜8区: 記号・かな、16〜47区: 第1水準漢字
        for col in range(1, 95):
            try:
                chars.add(bytes([0xA0 + row, 0xA0 + col]).decode("euc_jp"))
            except UnicodeDecodeError:
                pass
    chars.update(chr(c) for c in range(0x20, 0x7F))
    chars.update(chr(c) for c in range(0xA0, 0x180))   # É など
    chars.update(chr(c) for c in range(0x2000, 0x2070))  # — ・ ‧ など
    chars.update("〇々〆〜♪♯♭")
    return chars


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--ttc-family")
    args = ap.parse_args()
    if args.src.endswith(".ttc"):
        font = next(f for f in TTCollection(args.src).fonts if args.ttc_family in f["name"].getDebugName(1))
    else:
        font = TTFont(args.src)
    opts = subset.Options()
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=[ord(c) for c in jis_level1_and_symbols()])
    sub.subset(font)
    font.save(args.dst)


if __name__ == "__main__":
    main()
