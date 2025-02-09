import sys

sys.path.insert(0, "..")

from playhouse.migrate import *

from config import database_file

my_db = SqliteDatabase("../" + database_file)
migrator = SqliteMigrator(my_db)

watchfile_str_field = CharField(default="")

with my_db.atomic():
    migrate(
        migrator.add_column("gameconfig", "watchfile", watchfile_str_field),
    )
