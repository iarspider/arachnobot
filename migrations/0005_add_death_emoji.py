import sys

sys.path.insert(0, "..")

from playhouse.migrate import *

from config import database_file

my_db = SqliteDatabase("../" + database_file)
migrator = SqliteMigrator(my_db)

rip_emoji_str_field = CharField(default="☠")

with my_db.atomic():
    migrate(
        migrator.add_column("gameconfig", "rip_emoji", rip_emoji_str_field),
    )
