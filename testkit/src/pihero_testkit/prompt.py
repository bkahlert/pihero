"""Questions on the terminal for what make was not given."""

from collections.abc import Callable

Reader = Callable[[str], str]


def choose(title: str, options: list[str], read: Reader = input) -> int:
    """Prints the numbered options and returns the index of the one chosen; Enter picks the first."""
    print(title)
    for number, option in enumerate(options, 1):
        print(f"  {number}) {option}")
    while True:
        answer = read(f"[1-{len(options)}] (1): ").strip()
        if answer == "":
            return 0
        if answer.isdecimal() and 1 <= int(answer) <= len(options):
            return int(answer) - 1


def confirm(question: str, read: Reader = input) -> bool:
    return read(f"{question} [y/N]: ").strip().lower() in ("y", "yes")


def ask(question: str, read: Reader = input) -> str:
    while not (answer := read(f"{question}: ").strip()):
        pass
    return answer
