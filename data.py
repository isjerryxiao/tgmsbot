#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from peewee import *

SQLITE_MAX_INT: int = 2**63 -1
SQLITE_MIN_INT: int = -2**63
SQLITE_MAX_INT = SQLITE_MAX_INT // 2
SQLITE_MIN_INT = SQLITE_MIN_INT // 2

db = SqliteDatabase('tgmsbot.db', pragmas={
    'journal_mode': 'wal',
    'cache_size': -32 * 1000})

class SafeIntegerField(IntegerField):
    field_type = 'INT'

    def adapt(self, value):
        try:
            ivalue = int(value)
            if ivalue > SQLITE_MAX_INT:
                rvalue = SQLITE_MAX_INT
            elif ivalue < SQLITE_MIN_INT:
                rvalue = SQLITE_MIN_INT
            else:
                rvalue = value
            return rvalue
        except ValueError:
            return value


class Player(Model):
    user_id = SafeIntegerField(unique=True, primary_key=True)
    mines = SafeIntegerField()
    death = SafeIntegerField()
    wins = SafeIntegerField()
    restricted_until = SafeIntegerField()
    immunity_cards = SafeIntegerField()
    permission = SafeIntegerField()

    class Meta:
        database = db

db.connect()
db.create_tables([Player])

def get_player(user_id):
    player = Player.get_or_none(Player.user_id == user_id)
    if player is None:
        player = Player.create(user_id=user_id, mines=0, death=0, wins=0,
                               restricted_until=0, immunity_cards=0, permission=0)
        return player
    else:
        return player
