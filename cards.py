#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import run_async
from random import randrange
from time import time

import logging
logger = logging.getLogger('tgmsbot.cards')

# from the main module
get_player = lambda *args, **kwargs: None
game_manager = None

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
    logger.info(f'getperm from {getattr(update.effective_user, "id", None)}')
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
    logger.info(f'setperm from {getattr(update.effective_user, "id", None)}')
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
    logger.info(f'lvlup from {getattr(update.effective_user, "id", None)}')
    LVLUP_TIMEOUT = 10
    last_time = context.user_data.setdefault('lvlup_time', 0.0)
    ctime = time()
    if ctime - last_time < LVLUP_TIMEOUT:
        update.message.reply_text('别急，你不是刚刚才来过吗\nTips: /lvlup n 可以一次升n级哦')
        return
    else:
        context.user_data['lvlup_time'] = ctime
    (from_user, reply_to_user) = _msg_users(update)
    if context.args and len(context.args) == 1:
        try:
            amount = int(context.args[0])
        except ValueError:
            update.message.reply_text('数字不合法')
            return
    else:
        amount = 1
    if not from_user:
        return
    if reply_to_user:
        fplayer = get_player(int(from_user.id))
        tplayer = get_player(int(reply_to_user.id))
        amount = abs(amount)
        if fplayer.immunity_cards >= (used_cards := LVL_UP_CARDS * amount):
            fplayer.immunity_cards -= used_cards
            tplayer.permission = MAX_LEVEL - 1 if (_tpp := tplayer.permission + amount) >= MAX_LEVEL - 1 \
                                                  and tplayer.permission < MAX_LEVEL else _tpp
            fplayer.save()
            tplayer.save()
            update.message.reply_text((f"{display_username(from_user)} 消耗了{used_cards}张免疫卡，"
                                       f"为 {display_username(reply_to_user)} 升了{amount}级"),
                                       parse_mode="Markdown")
        else:
            update.message.reply_text(f"您的免疫卡不足({fplayer.immunity_cards})，{used_cards}张免疫卡兑换{amount}等级",
                                      parse_mode="Markdown")
    else:
        fplayer = get_player(int(from_user.id))
        if fplayer.immunity_cards >= (used_cards := LVL_UP_CARDS * amount):
            if amount < 0:
                if fplayer.permission + amount >= 0:
                    fplayer.immunity_cards += abs(used_cards)
                else:
                    fplayer.immunity_cards += LVL_UP_CARDS * fplayer.permission
            else:
                fplayer.immunity_cards -= abs(used_cards)
            fplayer.permission = MAX_LEVEL - 1 if (_fpp := fplayer.permission + amount) >= MAX_LEVEL - 1 \
                                                  and fplayer.permission < MAX_LEVEL else _fpp
            fplayer.save()
            update.message.reply_text((f"{display_username(from_user)} 消耗了{used_cards}张免疫卡，"
                                       f"为 自己 升了{amount}级"), parse_mode="Markdown")
        else:
            update.message.reply_text(f"您的免疫卡不足({fplayer.immunity_cards})，{used_cards}张免疫卡兑换{amount}等级",
                                      parse_mode="Markdown")

@run_async
def transfer_cards(update, context):
    logger.info(f'transfer_cards from {getattr(update.effective_user, "id", None)}')
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
    logger.info(f'rob_cards from {getattr(update.effective_user, "id", None)}')
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
            MSG_TEXT_SUCCESS = "抢劫成功，获得"
            MSG_TEXT_FAIL = "抢劫失败，反被抢走"
            if _fp >= MID_LEVEL and _tp >= MID_LEVEL:
                cards_amount = int(max(abs(fplayer.immunity_cards), abs(tplayer.immunity_cards)) * randrange(1000,8000)/10000)
                lvl_amount = int(max(_fp, _tp) * randrange(1000,8000)/10000)
                if (_tple if (_fp < MAX_LEVEL) ^ (_tple := _tp < MAX_LEVEL) else __chance(success_chance)):
                    msg_text = MSG_TEXT_SUCCESS
                else:
                    msg_text = MSG_TEXT_FAIL
                    cards_amount = -cards_amount
                    lvl_amount = -lvl_amount
                fplayer.immunity_cards += cards_amount
                tplayer.immunity_cards -= cards_amount
                fplayer.permission = _fpp if (_fpp := _fp + lvl_amount) < MAX_LEVEL or _fp >= MAX_LEVEL else MAX_LEVEL - 1
                tplayer.permission = _tpp if (_tpp := _tp - lvl_amount) < MAX_LEVEL or _tp >= MAX_LEVEL else MAX_LEVEL - 1
                fplayer.save()
                tplayer.save()
                update.message.reply_text((f'{display_username(from_user)} {msg_text}{abs(cards_amount)}张卡, '
                                           f'{abs(lvl_amount)}级'),
                                          parse_mode="Markdown")
            else:
                if __chance(success_chance):
                    msg_text = MSG_TEXT_SUCCESS
                else:
                    msg_text = MSG_TEXT_FAIL
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
    logger.info(f'cards_lottery from {getattr(update.effective_user, "id", None)}')
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
    logger.info(f'dist_cards from {getattr(update.effective_user, "id", None)}')
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
    logger.info(f'dist_cards_btn_click from {getattr(update.effective_user, "id", None)}')
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

@run_async
def reveal(update, context):
    logger.info(f'reveal from {getattr(update.effective_user, "id", None)}')
    (from_user, _) = _msg_users(update)
    if not from_user:
        return
    if (msg := update.effective_message) and (rmsg := msg.reply_to_message):
        try:
            assert (rmarkup := rmsg.reply_markup) and (kbd := rmarkup.inline_keyboard) \
                and type((btn := kbd[0][0])) is InlineKeyboardButton and (data := btn.callback_data)
            data = data.split(' ')
            data = [int(i) for i in data]
            (bhash, _, _, _) = data
        except:
            msg.reply_text('不是一条有效的消息')
            return
        game = game_manager.get_game_from_hash(bhash)
        if not game:
            msg.reply_text('这局似乎走丢了呢')
            return
        if (mmap := game.board.mmap) is None:
            msg.reply_text('这局似乎还没开始呢')
            return
        def map_to_msg():
            ZERO_CELL = '\u23f9'
            MINE_CELL = '\u2622'
            NUM_CELL_SUFFIX = '\ufe0f\u20e3'
            BAD_CELL = "\U0001f21a\ufe0f"
            msg_text = ""
            for row in mmap:
                for cell in row:
                    if cell == 0:
                        msg_text += ZERO_CELL
                    elif cell == 9:
                        msg_text += MINE_CELL
                    elif cell in range(1,9):
                        msg_text += str(cell) + NUM_CELL_SUFFIX
                    else:
                        msg_text += BAD_CELL
                msg_text += '\n'
            return msg_text
        fplayer = get_player(int(from_user.id))
        cards = abs(fplayer.immunity_cards) / 3
        def __floating(value):
            return randrange(5000,15000)/10000 * value
        cards = __floating(cards)
        cards = int(cards) if cards > 1 else 1
        extra_text = ""
        fplayer.immunity_cards -= cards
        if fplayer.permission >= MID_LEVEL and fplayer.permission < MAX_LEVEL:
            lvl = int(randrange(100,3000)/10000 * fplayer.permission)
            lvl = lvl if lvl > 0 else 1
            fplayer.permission -= lvl
            extra_text = f", {lvl}级"
        fplayer.save()
        msg.reply_text(f'本局地图如下:\n\n{map_to_msg()}\n您用去了{cards}张卡{extra_text}')
    else:
        msg.reply_text('请回复想要查看的雷区')
