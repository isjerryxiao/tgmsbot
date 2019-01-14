#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from peewee import *

db = SqliteDatabase('tgmsbot.db', pragmas={
    'journal_mode': 'wal',
    'cache_size': -32 * 1000})

class Player(Model):
    user_id = IntegerField(unique=True, primary_key=True)
    mines = IntegerField()
    death = IntegerField()
    wins = IntegerField()
    restricted_until = IntegerField()
    immunity_cards = IntegerField()
    class Meta:
        database = db
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        db.close()
    @staticmethod
    def db_close():
        db.close()

db.connect()
db.create_tables([Player])
db.close()

def get_player(user_id):
    db.connect()
    player = Player.get_or_none(Player.user_id == user_id)
    if player is None:
        player = Player.create(user_id=user_id, mines=0, death=0, wins=0,
                               restricted_until=0, immunity_cards=0)
        return player
    else:
        return player
