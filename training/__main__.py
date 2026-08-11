"""python -m training 分派到 train / verify。"""

import sys


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    if sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    if sys.argv[1] not in ("train", "verify", "package"):
        print(__doc__)
        return 1
    sub, rest = sys.argv[1], sys.argv[2:]
    if sub == "train":
        from training.train import main as train_main

        return train_main(rest)
    if sub == "package":
        from training.pack import main as pack_main

        return pack_main(rest)
    from training.verify import main as verify_main

    return verify_main(rest)


if __name__ == "__main__":
    raise SystemExit(main())
