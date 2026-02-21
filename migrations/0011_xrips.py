import sys

import peewee

sys.path.insert(0, "..")

from newbot import GameConfig

from config import database_file

my_db = peewee.SqliteDatabase("../" + database_file)
my_db.connect()


class ExtraRipCounter(peewee.Model):
    game = peewee.ForeignKeyField(model=GameConfig, backref="extra_rips")
    name = peewee.CharField()
    cnt = peewee.IntegerField(default=1)

    class Meta:
        table_name = "xripcount"
        database = my_db


my_db.create_tables([ExtraRipCounter])
my_db.close()
