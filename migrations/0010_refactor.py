from playhouse.migrate import SqliteMigrator, migrate
import peewee

from config import database_file

my_db = peewee.SqliteDatabase("../" + database_file)
migrator = SqliteMigrator(my_db)

with my_db.atomic():
    migrate(
        # OBS window
        migrator.rename_column("gameconfig", "window", "obs_window"),
        migrator.rename_column("gameconfig", "window_inexact", "obs_window_title_glob"),
        migrator.delete_column("gameconfig", "use_game_capture"),
        # MT integration
        migrator.rename_column("gameconfig", "mt", "mt_enabled"),
        migrator.rename_column("gameconfig", "mt_str", "mt_source"),
        # RIP / deaths
        migrator.rename_column("gameconfig", "watchfile", "rip_watchfile"),
        migrator.rename_column("gameconfig", "inexact", "rip_is_inexact"),
        migrator.rename_column("gameconfig", "infinite", "is_infinite"),
        migrator.rename_column("gameconfig", "is_infinite", "rip_is_infinite"),
    )

"""
class GameConfig(peewee.Model):
    game = peewee.CharField(primary_key=True)

    # ─── RIP / Death counter ──────────────────────────────
    rip_enabled = peewee.BooleanField(default=True)
    rip_total = peewee.IntegerField(default=0)
    rip_emoji = peewee.CharField(default="☠")

    # External source of truth (e.g. Minecraft mod)
    rip_watchfile = peewee.CharField(default="")
    rip_is_inexact = peewee.BooleanField(
        default=False,
        help_text="Deaths count is approximate (no reliable source)"
    )

    # ─── Stream / gameplay state ──────────────────────────
    rip_is_infinite = peewee.BooleanField(
        default=False,
        help_text="Streamer enabled immortality / cheats"
    )

    music_enabled = peewee.BooleanField(default=False)

    # ─── OBS capture (window mode) ────────────────────────
    obs_window = peewee.TextField(
        default="",
        help_text="OBS window string: id\\ntitle\\nclass"
    )
    obs_window_title_glob = peewee.BooleanField(
        default=False,
        help_text="Window title is glob-pattern"
    )

    # LEGACY (Windows OBS distinction)
    # use_game_capture = peewee.BooleanField(
    #     default=True,
    #     help_text="LEGACY: OBS Game Capture vs Window Capture"
    # )

    # ─── External integrations ────────────────────────────
    mt_enabled = peewee.BooleanField(default=False)
    mt_source = peewee.CharField(
        default="iarspider/moar__/danzio_plagius"
    )

    # ─── Twitch metadata ──────────────────────────────────
    tags = peewee.TextField(
        default="",
        help_text="Twitch tags (semicolon-separated, raw)"
    )

    class Meta:
        database = database

    # ─── Derived / helper properties ──────────────────────

    @property
    def has_external_rip_source(self) -> bool:
        return bool(self.rip_watchfile)

    @property
    @deprecated(version="5.6.0", reason="Use obs_window instead")
    def window(self):
        return bool(self.obs_window)
    
    @window.setter
    @deprecated(version="5.6.0", reason="Use obs_window instead")
    def window(self, value):
        self.obs_window = value

    @property
    @deprecated(version="5.6.0", reason="Use obs_window_title_glob instead")
    def window_inexact(self):
        return bool(self.obs_window_title_glob)
    
    @window_inexact.setter
    @deprecated(version="5.6.0", reason="Use obs_window_title_glob instead")
    def window_inexact(self, value):
        self.obs_window_title_glob = value
        
    
    
    def __str__(self) -> str:
        return self.game
"""
