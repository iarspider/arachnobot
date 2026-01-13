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
        migrator.drop_column("gameconfig", "use_game_capture"),
        # MT integration
        migrator.rename_column("gameconfig", "mt", "mt_enabled"),
        migrator.rename_column("gameconfig", "mt_str", "mt_source"),
        # RIP / deaths
        migrator.rename_column("gameconfig", "watchfile", "rip_watchfile"),
        migrator.rename_column("gameconfig", "inexact", "rip_is_inexact"),
        migrator.rename_column("gameconfig", "infinite", "is_infinite"),
        migrator.rename_column("gameconfig", "is_infinite", "rip_is_infinite"),
    )
