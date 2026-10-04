"""Plain text console with injectable input/output (so the confirm flow is testable)."""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from .strings import t


class Console:
    def __init__(
        self,
        input_fn: Callable[[str], str] = input,
        print_fn: Callable[[str], None] = print,
        assume_yes: bool = False,
        interactive: bool = True,
    ) -> None:
        self._input = input_fn
        self._print = print_fn
        self.assume_yes = assume_yes
        self.interactive = interactive

    def say(self, text: str = "") -> None:
        self._print(text)

    def ask(self, prompt: str) -> Optional[str]:
        try:
            return self._input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return None

    def confirm(self, question: str, default: bool = False) -> bool:
        """Yes/no. --yes answers yes; end of input or Ctrl+C answers no."""
        if self.assume_yes:
            self.say(f"{question} -> yes (--yes)")
            return True
        if not self.interactive:
            return False
        hint = t("yesno.yes_default") if default else t("yesno.no_default")
        answer = self.ask(f"{question} {hint} ")
        if answer is None:
            return False
        if answer == "":
            return default
        return answer.lower() in ("y", "yes", "j", "ja")

    def choose(self, prompt: str, options: Sequence[str]) -> Optional[int]:
        """Pick from a numbered list (already printed); returns a 0-based index or None."""
        if not self.interactive:
            return None
        answer = self.ask(prompt)
        if not answer:
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return int(answer) - 1
        self.say(t("menu.invalid"))
        return None
