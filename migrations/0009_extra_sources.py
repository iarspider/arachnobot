import sys

import peewee

sys.path.insert(0, "..")

from newbot import GameConfig

from config import database_file

my_db = peewee.SqliteDatabase("../" + database_file)
my_db.connect()


class SourceConfig(peewee.Model):
    game = peewee.ForeignKeyField(model=GameConfig, backref="sources")
    scene = peewee.CharField()
    source = peewee.CharField()
    state = peewee.BooleanField()

    class Meta:
        database = my_db
        table_name = "sourceconfig"


my_db.create_tables([SourceConfig])
my_db.close()
