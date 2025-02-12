import sys

from peewee import TextField

sys.path.insert(0, "..")

from playhouse.migrate import *

from config import database_file

my_db = SqliteDatabase("../" + database_file)
migrator = SqliteMigrator(my_db)

game_tags_text_field = TextField(default="")

with my_db.atomic():
    migrate(
        migrator.add_column("gameconfig", "tags", game_tags_text_field),
    )
