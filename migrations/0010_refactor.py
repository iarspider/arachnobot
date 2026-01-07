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
    @depreated("5.6.0, "Windows legacy, do not use")
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
        return self.game
"""
