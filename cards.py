#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import run_async
from data import get_player
from random import randrange
from time import time

MAX_LEVEL: int = 100
MID_LEVEL: int = 80
LVL_UP_CARDS: int = 20


def display_username(user, atuser=True, shorten=False, markdown=True):
    """
        atuser and shorten has no effect if markdown is True.
    """
    name = user.full_name
    if markdown:
        mdtext = user.mention_markdown(name=user.full_name)
        return mdtext
    if shorten:
        return name
    if user.username:
        if atuser:
            name += " (@{})".format(user.username)
        else:
            name += " ({})".format(user.username)
    return name


def _msg_users(update):
    '''
        get from_user and reply_to_user
    '''
    if update.message:
        if update.message.reply_to_message:
            return (update.message.from_user,
                    update.message.reply_to_message.from_user)
        else:
            return (update.message.from_user, None)
    else:
        return (None, None)

@run_async
def getperm(update, context):
    (from_user, reply_to_user) = _msg_users(update)
    if not from_user:
        return
    if reply_to_user:
        tuser = reply_to_user
    else:
        tuser = from_user
    tplayer = get_player(int(tuser.id))
    update.message.reply_text((f"{display_username(tuser)} 等级为 {tplayer.permission}\n"
                               f"口袋里有 {tplayer.immunity_cards} 张免疫卡"),
                              parse_mode="Markdown")

@run_async
def setperm(update, context):
    (from_user, reply_to_user) = _msg_users(update)
    if not from_user:
        return
    if reply_to_user:
        if context.args and len(context.args) == 1:
            try:
                new_level = int(context.args[0])
            except ValueError:
                update.message.reply_text('数字不合法')
                return
        else:
            update.message.reply_text('请指定新的等级')
            return
        if get_player(int(from_user.id)).permission >= MAX_LEVEL:
            tplayer = get_player(int(reply_to_user.id))
            tplayer.permission = new_level
            tplayer.save()
            update.message.reply_text('请求成功')
        else:
            update.message.reply_text('请求忽略')
    else:
        update.message.reply_text('请回复被操作人')

@run_async
def lvlup(update, context):
    '''
        use LVL_UP_CARDS cards to level up 1 lvl
    '''
    (from_user, reply_to_user) = _msg_users(update)
    if not from_user:
        return
    if reply_to_user:
        fplayer = get_player(int(from_user.id))
        tplayer = get_player(int(reply_to_user.id))
        if fplayer.immunity_cards >= LVL_UP_CARDS:
            fplayer.immunity_cards -= LVL_UP_CARDS
            if tplayer.permission <= MAX_LEVEL - 2 or tplayer.permission >= MAX_LEVEL:
                tplayer.permission += 1
            fplayer.save()
            tplayer.save()
            update.message.reply_text((f"{display_username(from_user)} 消耗了{LVL_UP_CARDS}张免疫卡，"
                                       f"为 {display_username(reply_to_user)} 升了1级"),
                                       parse_mode="Markdown")
        else:
            update.message.reply_text(f"您的免疫卡不足({fplayer.immunity_cards})，{LVL_UP_CARDS}张免疫卡兑换1等级",
                                      parse_mode="Markdown")
    else:
        fplayer = get_player(int(from_user.id))
        if fplayer.immunity_cards >= LVL_UP_CARDS:
            fplayer.immunity_cards -= LVL_UP_CARDS
            if fplayer.permission <= MAX_LEVEL - 2 or fplayer.permission >= MAX_LEVEL:
                fplayer.permission += 1
            fplayer.save()
            update.message.reply_text((f"{display_username(from_user)} 消耗了{LVL_UP_CARDS}张免疫卡，"
                                        "为 自己 升了1级"), parse_mode="Markdown")
        else:
            update.message.reply_text(f"您的免疫卡不足({fplayer.immunity_cards})，{LVL_UP_CARDS}张免疫卡兑换1等级",
                                      parse_mode="Markdown")

@run_async
def transfer_cards(update, context):
    (from_user, reply_to_user) = _msg_users(update)
    if not from_user:
        return
    if reply_to_user:
        if context.args and len(context.args) == 1:
            try:
                amount = int(context.args[0])
            except ValueError:
                update.message.reply_text('数字不合法')
                return
        else:
            update.message.reply_text('请指定数量')
            return
        if from_user.id == reply_to_user.id:
            fplayer = get_player(int(from_user.id))
            if fplayer.permission >= MID_LEVEL:
                fplayer.immunity_cards += amount
                fplayer.save()
                update.message.reply_text(f'{display_username(from_user)} 转给了自己{amount}张卡', parse_mode="Markdown")
            else:
                update.message.reply_text(f'{display_username(from_user)} 转给了自己{amount}张卡', parse_mode="Markdown")
        else:
            fplayer = get_player(int(from_user.id))
            tplayer = get_player(int(reply_to_user.id))
            if (amount >= 0 and fplayer.immunity_cards >= amount) or \
               (fplayer.permission >= MID_LEVEL and tplayer.permission <= fplayer.permission):
                fplayer.immunity_cards -= amount
                tplayer.immunity_cards += amount
                fplayer.save()
                tplayer.save()
                update.message.reply_text(f'{display_username(from_user)} 转给了 {display_username(reply_to_user)} {amount}张卡',
                                          parse_mode="Markdown")
            else:
                update.message.reply_text(f'转账失败，你可能没有这么多卡哦({fplayer.immunity_cards}/{amount})',
                                          parse_mode="Markdown")
    else:
        update.message.reply_text('请回复被操作人')

@run_async
def rob_cards(update, context):
    ROB_TIMEOUT = 10
    last_time = context.user_data.setdefault('rob_time', 0.0)
    ctime = time()
    if ctime - last_time < ROB_TIMEOUT:
        update.message.reply_text('别急，你不是刚刚才来过吗')
        return
    else:
        context.user_data['rob_time'] = ctime
    (from_user, reply_to_user) = _msg_users(update)
    if not from_user:
        return
    if reply_to_user:
        amount = randrange(1, 9)
        if from_user.id == reply_to_user.id:
            fplayer = get_player(int(from_user.id))
            fplayer.immunity_cards -= amount
            fplayer.save()
            update.message.reply_text(f'{display_username(from_user)} 自己抢走自己{amount}张卡', parse_mode="Markdown")
        else:
            fplayer = get_player(int(from_user.id))
            tplayer = get_player(int(reply_to_user.id))
            _fp = fplayer.permission if fplayer.permission > 0 else 0
            _tp = tplayer.permission if tplayer.permission > 0 else 0
            success_chance = _fp / (_fp + _tp) if _fp + _tp != 0 else 0.5
            def __chance(percentage):
                if randrange(0,10000)/10000 < percentage:
                    return True
                else:
                    return False
            if __chance(success_chance):
                msg_text = "抢劫成功，获得"
            else:
                msg_text = "抢劫失败，反被抢走"
                amount = -amount
            fplayer.immunity_cards += amount
            tplayer.immunity_cards -= amount
            fplayer.save()
            tplayer.save()
            update.message.reply_text(f'{display_username(from_user)} {msg_text}{abs(amount)}张卡', parse_mode="Markdown")
    else:
        update.message.reply_text('请回复被操作人')

@run_async
def cards_lottery(update, context):
    LOTTERY_TIMEOUT = 10
    last_time = context.user_data.setdefault('lottery_time', 0.0)
    ctime = time()
    if ctime - last_time < LOTTERY_TIMEOUT:
        update.message.reply_text('别急，你不是刚刚才来过吗')
        return
    else:
        context.user_data['lottery_time'] = ctime
    (from_user, _) = _msg_users(update)
    if not from_user:
        return
    fplayer = get_player(int(from_user.id))
    cards = abs(fplayer.immunity_cards) / 3
    def __floating(value):
        return randrange(5000,15000)/10000 * value
    cards = __floating(cards)
    cards = int(cards) if cards > 1 else 1
    cards *= randrange(-1, 2, 2)
    fplayer.immunity_cards += cards
    fplayer.save()
    update.message.reply_text(f'您{"获得" if cards >= 0 else "血亏"}了{abs(cards)}张卡')

@run_async
def dist_cards(update, context):
    (from_user, _) = _msg_users(update)
    if not from_user:
        return
    try:
        if context.args and len(context.args) == 2:
            (cards, damount) = [int(a) for a in context.args]
            assert (cards > 0 and damount > 0)
            fplayer = get_player(int(from_user.id))
            assert fplayer.immunity_cards >= cards
            fplayer.immunity_cards -= cards
            fplayer.save()
            red_packets = context.chat_data.setdefault('red_packets', dict())
            rphash = str(hash(f"{update.effective_chat.id} {update.effective_message.message_id}"))[:8]
            red_packets[rphash] = [cards, damount]
            update.message.reply_text(f'{display_username(from_user)}的红包🧧', parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup.from_button(
                                                   InlineKeyboardButton(text=f"{cards} / {damount}",
                                                                        callback_data=f"dist {rphash}")
                                                   ))
        else:
            raise ValueError('')
    except (ValueError, AssertionError):
        update.message.reply_text(f'数字不合法: /dist 卡 红包数量')

@run_async
def dist_cards_btn_click(update, context):
    data = update.callback_query.data
    user = update.callback_query.from_user
    omsg = update.callback_query.message
    red_packets = context.chat_data.setdefault('red_packets', dict())
    try:
        (_, rphash) = data.split(' ')
        rp = red_packets.get(str(rphash), None)
        if rp:
            (cards, damount) = [int(a) for a in rp]
            assert (cards > 0 and damount > 0)
            def __floating(value):
                return randrange(5000,15000)/10000 * value
            got_cards = int(__floating(cards/damount))
            got_cards = got_cards if got_cards <= cards else cards
            got_cards = 1 if got_cards == 0 and randrange(0,10000)/10000 < 0.2 else got_cards
            got_cards = got_cards if damount != 1 else cards
            rp[0] -= got_cards
            rp[1] -= 1
            (cards, damount) = rp
            fplayer = get_player(int(user.id))
            fplayer.immunity_cards += got_cards
            fplayer.save()
            update.callback_query.answer(text=f"你得到了{got_cards}张卡", show_alert=False)
            if cards > 0 and damount > 0:
                omsg.reply_markup.inline_keyboard[0][0].text = f"{cards} / {damount}"
                omsg.edit_reply_markup(reply_markup=omsg.reply_markup)
            else:
                raise AssertionError('')
        else:
            raise AssertionError('')
    except (ValueError, AssertionError):
        try:
            update.callback_query.answer()
        except Exception:
            pass
        def free_mem(job_context):
            try:
                red_packets.pop(rphash)
            except KeyError:
                pass
        if rphash:
            rp = red_packets.get(rphash, [0, 0])
            if rp[0] != -1:
                rp[0] = -1
                omsg.edit_text(omsg.text_markdown + "褪裙了", parse_mode="Markdown", reply_markup=None)
                context.job_queue.run_once(free_mem, 5)
