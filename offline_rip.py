import sys
from typing import Optional

import codecs

from bot import GameConfig

deaths = {}
game: Optional[GameConfig] = None


def update():
    global deaths
    deaths = {"today": 0, "total": game.rip_total}
    # enabled = bot.game.rip_enabled
    # asyncio.ensure_future(obscog.enable_rip(enabled))
    display_rip()


def display_rip():
    with codecs.open("rip_display.txt", "w", "utf8") as f:
        if game.inexact:
            f.write("☠: {today}+ (всего: ≈{total})".format(**deaths))
            return
        if game.infinite:
            f.write("☠: ∞".format(**deaths))
            return

        f.write("☠: {today} (всего: {total})".format(**deaths))


def write_rip():
    display_rip()
    game.rip_total = deaths["total"]
    game.save()


def do_rip(n=1):
    deaths["today"] += n
    deaths["total"] += n

    write_rip()

    return (
        "iarspiRip {today}".format(**deaths)
        if n > 0
        else "MercyWing1 PinkMercy MercyWing2"
    )


def main():
    global game

    game = GameConfig.get_or_none(game="Horizon Zero Dawn")
    assert game is not None
    update()
    if len(sys.argv) == 2:
        nrip = int(sys.argv[1])
    else:
        nrip = 1

    do_rip(nrip)


if __name__ == "__main__":
    main()
