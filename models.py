from enum import Enum

import peewee
import peewee_enum_field
from deprecation import deprecated

from config import database_file

database = peewee.SqliteDatabase(database_file)


# TODO: remove deprecated aliases after 5.8.0
class GameConfig(peewee.Model):
    game = peewee.CharField(primary_key=True)

    # ─── RIP / Death counter ──────────────────────────────
    rip_enabled = peewee.BooleanField(default=True)
    rip_total = peewee.IntegerField(default=0)
    rip_emoji = peewee.CharField(default="☠")

    # External source of truth (e.g. Minecraft mod)
    rip_watchfile = peewee.CharField(default="")
    rip_is_inexact = peewee.BooleanField(
        default=False, help_text="Deaths count is approximate (no reliable source)"
    )

    # ─── Stream / gameplay state ──────────────────────────
    rip_is_infinite = peewee.BooleanField(
        default=False, help_text="Streamer enabled immortality / cheats"
    )

    music_enabled = peewee.BooleanField(default=False)

    # ─── OBS capture (window mode) ────────────────────────
    obs_window = peewee.TextField(
        default="", help_text="OBS window string: id\\ntitle\\nclass"
    )
    obs_window_title_glob = peewee.BooleanField(
        default=False, help_text="Window title is glob-pattern"
    )

    # LEGACY (Windows OBS distinction)
    # use_game_capture = peewee.BooleanField(
    #     default=True,
    #     help_text="LEGACY: OBS Game Capture vs Window Capture"
    # )

    # ─── External integrations ────────────────────────────
    mt_enabled = peewee.BooleanField(default=False)
    mt_source = peewee.CharField(default="iarspider/moar__/danzio_plagius")

    # ─── Acoustic Echo Cancellation ───────────────────────
    aec = peewee.BooleanField(default=False)

    # ─── Twitch metadata ──────────────────────────────────
    tags = peewee.TextField(
        default="", help_text="Twitch tags (semicolon-separated, raw)"
    )

    class Meta:
        database = database

    # ─── Derived / helper properties ──────────────────────
    @property
    @deprecated("5.6.0", "Windows legacy, do not use")
    def use_game_capture(self):
        return True

    @property
    @deprecated("5.6.0", "Use obs_window instead")
    def window(self):
        return self.obs_window

    @window.setter
    @deprecated("5.6.0", "Use obs_window instead")
    def window(self, value):
        self.obs_window = value

    @property
    @deprecated("5.6.0", "Use obs_window_title_glob instead")
    def window_inexact(self):
        return self.obs_window_title_glob

    @window_inexact.setter
    @deprecated("5.6.0", "Use obs_window_title_glob instead")
    def window_inexact(self, value):
        self.obs_window_title_glob = value

    @property
    @deprecated("5.6.0", "Use mt_enabled instead")
    def mt(self):
        return self.mt_enabled

    @mt.setter
    @deprecated("5.6.0", "Use mt_enabled instead")
    def mt(self, value):
        self.mt_enabled = value

    @property
    @deprecated("5.6.0", "Use mt_source instead")
    def mt_str(self):
        return self.mt_source

    @mt_str.setter
    @deprecated("5.6.0", "Use mt_source instead")
    def mt_str(self, value):
        self.mt_source = value

    @property
    @deprecated("5.6.0", "Use rip_watchfile instead")
    def watchfile(self):
        return self.rip_watchfile

    @watchfile.setter
    @deprecated("5.6.0", "Use rip_watchfile instead")
    def watchfile(self, value):
        self.rip_watchfile = value

    @property
    @deprecated("5.6.0", "Use rip_is_inexact instead")
    def inexact(self):
        return self.rip_is_inexact

    @inexact.setter
    @deprecated("5.6.0", "Use rip_is_inexact instead")
    def inexact(self, value):
        self.rip_is_inexact = value

    @property
    @deprecated("5.6.0", "Use rip_is_infinite instead")
    def infinite(self):
        return self.rip_is_infinite

    @infinite.setter
    @deprecated("5.6.0", "Use rip_is_infinite instead")
    def infinite(self, value):
        self.rip_is_infinite = value

    def __str__(self) -> str:
        return str(self.game)


class DuelStats(peewee.Model):
    attacker = peewee.TextField()
    defender = peewee.TextField()
    losses = peewee.IntegerField(null=False, default=0)
    wins = peewee.IntegerField(null=False, default=0)

    class Meta:
        table_name = "duelstats"
        database = database
        primary_key = peewee.CompositeKey("attacker", "defender")


class SourceConfig(peewee.Model):
    game = peewee.ForeignKeyField(model=GameConfig, backref="sources")
    scene = peewee.CharField()
    source = peewee.CharField()
    state = peewee.BooleanField()

    class Meta:
        table_name = "sourceconfig"
        database = database


class BossStateEnum(Enum):
    CURRENT = 1
    PAUSED = 2
    DROPPED = 3
    DEFEATED = 4


class ExtraRipCounter(peewee.Model):
    game = peewee.ForeignKeyField(model=GameConfig, backref="extra_rips")
    name = peewee.CharField()
    cnt = peewee.IntegerField(default=1)
    state = peewee_enum_field.EnumField(
        enum=BossStateEnum, default=BossStateEnum.CURRENT
    )

    class Meta:
        table_name = "xripcount"
        database = database
