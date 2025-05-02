import sys

sys.path.insert(0, "..")

from peewee import BooleanField, SqliteDatabase
from playhouse.migrate import SqliteMigrator, migrate

from config import database_file

my_db = SqliteDatabase("../" + database_file)
migrator = SqliteMigrator(my_db)

game_inexact_bool_field = BooleanField(default=False)

with my_db.atomic():
    migrate(
        migrator.add_column("gameconfig", "window_inexact", game_inexact_bool_field),
    )
