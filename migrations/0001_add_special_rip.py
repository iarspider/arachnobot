from playhouse.migrate import *

from config import database_file

my_db = SqliteDatabase("../" + database_file)
migrator = SqliteMigrator(my_db)

infinite_field = BooleanField(default=False)
inexact_field = BooleanField(default=False)

with my_db.atomic():
    migrate(
        migrator.add_column("gameconfig", "infinite", infinite_field),
        migrator.add_column("gameconfig", "inexact", inexact_field),
    )
