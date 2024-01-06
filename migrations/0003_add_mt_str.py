import sys

sys.path.insert(0, "..")

from playhouse.migrate import *

from config import database_file

my_db = SqliteDatabase("../" + database_file)
migrator = SqliteMigrator(my_db)

mt_str_field = CharField(default="iarspider/moar__/danzio_plagius")

with my_db.atomic():
    migrate(
        migrator.add_column("gameconfig", "mt_str", mt_str_field),
    )
