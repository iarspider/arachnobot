import sys

sys.path.insert(0, "..")

from playhouse.migrate import *
from peewee_enum_field import EnumField
from models import BossStateEnum

from config import database_file

my_db = SqliteDatabase("../" + database_file)
migrator = SqliteMigrator(my_db)

xrip_state_field = EnumField(enum=BossStateEnum, default=BossStateEnum.CURRENT)

with my_db.atomic():
    migrate(
        migrator.add_column("xripcount", "state", xrip_state_field),
    )
