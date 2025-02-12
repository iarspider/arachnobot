import sys

sys.path.insert(0, "..")

from playhouse.migrate import *

from config import database_file

my_db = SqliteDatabase("../" + database_file)
migrator = SqliteMigrator(my_db)

game_source_bool_field = BooleanField(default=True)

with my_db.atomic():
    migrate(
        migrator.add_column("gameconfig", "use_game_capture", game_source_bool_field),
    )
