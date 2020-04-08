#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from mscore import Board, check_params
from copy import deepcopy
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, run_async
from telegram.error import TimedOut as TimedOutError, RetryAfter as RetryAfterError
from numpy import array_equal
from random import randint, choice, randrange
from math import log
from threading import Lock
import time
from pathlib import Path
import pickle
import logging
from traceback import format_exc

logging.basicConfig(level=logging.INFO,format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('tgmsbot')

try:
    from data import get_player, db
except ModuleNotFoundError:
    logger.warning('using data_ram instead of data')
    from data_ram import get_player, db

token = "token_here"
updater = Updater(token, workers=8, use_context=True)
job_queue = updater.job_queue
job_queue.start()

PICKLE_FILE = 'tgmsbot.pickle'

KBD_MIN_INTERVAL = 0.5
KBD_DELAY_SECS = 0.5
GARBAGE_COLLECTION_INTERVAL = 86400
MAX_GAMES_PER_USER = 10

HEIGHT = 8
WIDTH = 8
MINES = 9

UNOPENED_CELL = "\u2588"
FLAGGED_CELL = "\U0001f6a9"
STEPPED_CELL = "\u2622"
NUM_CELL_0 = "\u2800"
NUM_CELL_ORD = ord("\uff11") - 1

WIN_TEXT_TEMPLATE = "哇所有奇怪的地方都被你打开啦…好羞羞\n" \
                    "地图：Op {s_op} / Is {s_is} / 3bv {s_3bv}\n操作总数 {ops_count}\n" \
                    "统计：\n{ops_list}\n{last_player} 你要对人家负责哟/// ///\n\n" \
                    "用时{time}秒，超时{timeouts}次\n\n" \
                    "{last_player} {reward}\n\n" \
                    "/mine 开始新游戏"
STEP_TEXT_TEMPLATE = "{last_player} 踩到了地雷!\n" \
                    "时间{time}秒，超时{timeouts}次\n\n" \
                    "{last_player} {reward}\n\n" \
                    "雷区生命值：({remain}/{ttl})"
LOSE_TEXT_TEMPLATE = "一道火光之后，你就在天上飞了呢…好奇怪喵\n" \
                    "地图：Op {s_op} / Is {s_is} / 3bv {s_3bv}\n操作总数 {ops_count}\n" \
                    "统计：\n{ops_list}\n{last_player} 是我们中出的叛徒！\n\n" \
                    "用时{time}秒，超时{timeouts}次\n\n" \
                    "{last_player} {reward}\n\n" \
                    "/mine 开始新游戏"


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

class Saved_Game:
    def __init__(self, board, group, creator, lives=1):
        self.board = board
        self.group = group
        self.creator = creator
        self.msgid = None
        self.__actions = dict()
        self.last_player = None
        self.start_time = time.time()
        self.stopped = False
        # timestamp of the last update keyboard action,
        # it is used to calculate time gap between
        # two actions and identify unique actions.
        self.last_action = 0
        # number of timeout error catched
        self.timeouts = 0
        self.lives = lives
        self.ttl_lives = lives
    def save_action(self, user, spot):
        '''spot is supposed to be a tuple'''
        self.last_player = user
        if self.__actions.get(user, None):
            self.__actions[user].append(spot)
        else:
            self.__actions[user] = [spot,]
    def actions_sum(self):
        mysum = 0
        for user in self.__actions:
            game_count(user)
            count = len(self.__actions.get(user, list()))
            mysum += count
        return mysum
    def get_last_player(self):
        return display_username(self.last_player)
    def get_actions(self):
        '''Convert actions into text'''
        msg = ""
        for user in self.__actions:
            count = len(self.__actions.get(user, list()))
            msg = "{}{} - {}项操作\n".format(msg, display_username(user), count)
        return msg

class Game:
    def __init__(self, *args, **kwargs):
        if 'unpickle' in args:
            assert len(args) == 2 and args[0] == 'unpickle'
            self.__sg = args[1]
        else:
            self.__sg = Saved_Game(*args, **kwargs)
        self.lock = Lock()
    def pickle(self):
        return self.__sg
    def __getattr__(self, name):
        return getattr(self.__sg, name)
    def __setattr__(self, name, val):
        if name in ('_Game__sg', 'lock'):
            self.__dict__[name] = val
        else:
            return setattr(self.__sg, name, val)

class GameManager:
    def __init__(self):
        self.__games = dict()
        self.__pf = Path(PICKLE_FILE)
        if self.__pf.exists():
            try:
                with open(self.__pf, 'rb') as fhandle:
                    saved_games = pickle.load(fhandle, fix_imports=True, errors="strict")
                    self.__games = {bhash: Game('unpickle', saved_games[bhash]) for bhash in saved_games}
            except Exception as err:
                logger.error(f'Unable to load pickle file, {type(err).__name__}: {err}')
        assert type(self.__games) is dict
        for board_hash in self.__games:
            self.__games[board_hash].lock = Lock()
    def append(self, board, board_hash, group_id, creator_id):
        lives = int(board.mines/3)
        if lives <= 0:
            lives = 1
        self.__games[board_hash] = Game(board, group_id, creator_id, lives=lives)
        self.save_async()
    def remove(self, board_hash):
        board = self.get_game_from_hash(board_hash)
        if board:
            self.__games.pop(board_hash)
            self.save_async()
            return True
        else:
            return False
    def get_game_from_hash(self, board_hash):
        return self.__games.get(board_hash, None)
    def iter_game_from_user(self, user_id):
        for g in self.__games.copy().values():
            if g.creator.id == user_id:
                yield g
    def iter_all_open_game(self):
        for g in self.__games.copy().values():
            if g.group.type == 'supergroup':
                yield g
    def iter_game_from_chat(self, chat_id):
        for g in self.__games.copy().values():
            if g.group.id == chat_id:
                yield g
    def count(self):
        return len(self.__games)
    @run_async
    def save_async(self):
        self.save()
    def save(self):
        try:
            games_without_locks = {bhash: self.__games[bhash].pickle() for bhash in self.__games}
            with open(self.__pf, 'wb') as fhandle:
                pickle.dump(games_without_locks, fhandle, fix_imports=True)
        except Exception as err:
            logger.error(f'Unable to save pickle file, {type(err).__name__}: {err}')
    def do_garbage_collection(self, context):
        g_checked: int = 0
        g_freed:   int = 0
        games = self.__games
        for board_hash in games.copy():
            g_checked += 1
            gm = games[board_hash]
            start_time = getattr(gm, 'start_time', 0.0)
            if time.time() - start_time > 86400*10:
                g_freed += 1
                games.pop(board_hash)
        self.save_async()
        logger.info((f'Scheduled garbage collection checked {g_checked} games, '
                     f'freed {g_freed} games.'))

game_manager = GameManager()

@run_async
def list_games(update, context):
    logger.info("List from {0}".format(update.message.from_user.id))
    if (_is_open_all := context.args and context.args[0] in ('open', 'all')):
        _iter_func = game_manager.iter_all_open_game
        _iter_args = list()
    else:
        _iter_func = game_manager.iter_game_from_chat
        _iter_args = [update.effective_chat.id,]
    if not _is_open_all and (not update.effective_chat or update.effective_chat.type != 'supergroup'):
        if update.message:
            update.message.reply_text('本功能仅在超级群组中可用')
        return
    games_avail = list()
    for gm in _iter_func(*_iter_args):
        if len(games_avail) >= 10:
            break
        elif gm.group and gm.group.type and gm.group.type == 'supergroup' and gm.creator and gm.msgid:
            if context.args and context.args[0] == 'open' and not gm.group.username:
                continue
            games_avail.append(gm)
    if not games_avail:
        if _is_open_all:
            nrep_text = "没有找到符合条件的游戏"
        else:
            nrep_text = "本群没有正在进行的游戏\n试试 /list open 或 /list all"
        update.message.reply_text(nrep_text)
        return
    links = list()
    def gen_link(chat, msgid, text):
        if chat.username:
            return f"[{text}](https://t.me/{chat.username}/{msgid})"
        chat_id = int(chat.id)
        assert chat_id < -1000000000000
        chat_id = (-chat_id) - 1000000000000
        return f"[{text}](https://t.me/c/{chat_id}/{msgid})"
    for gm in games_avail:
        links.append(gen_link(gm.group, gm.msgid, f"{gm.creator.first_name} created on {time.ctime(gm.start_time)}"))
    update.message.reply_text("\n".join(links), parse_mode="Markdown")

@run_async
def send_keyboard(update, context):
    (bot, args) = (context.bot, context.args)
    msg = update.message
    logger.info("Mine from {0}".format(update.message.from_user.id))
    if check_restriction(update.message.from_user):
        update.message.reply_text("爆炸这么多次还想扫雷？")
        return
    for (_gid, _) in enumerate(game_manager.iter_game_from_user(update.message.from_user.id)):
        if _gid + 1 > MAX_GAMES_PER_USER:
            update.message.reply_text((f"汝已经创建了超过{MAX_GAMES_PER_USER}个游戏了\n"
                                        "请结束一个先前创建的游戏并继续"))
            return
    # create a game board
    if args is None:
        args = list()
    if len(args) == 3:
        height = HEIGHT
        width = WIDTH
        mines = MINES
        try:
            height = int(args[0])
            width = int(args[1])
            mines = int(args[2])
        except:
            pass
        # telegram doesn't like keyboard width to exceed 8
        if width > 8:
            width = 8
            msg.reply_text('宽度太大，已经帮您设置成8了')
        # telegram doesn't like keyboard keys to exceed 100
        if height * width > 100:
            msg.reply_text('格数不能超过100')
            return
        ck = check_params(height, width, mines)
        if ck[0]:
            board = Board(height, width, mines)
        else:
            msg.reply_text(ck[1])
            return
    elif len(args) == 0:
        board = Board(HEIGHT, WIDTH, MINES)
    else:
        msg.reply_text('你输入的是什么鬼！')
        return
    bhash = hash(board)
    game_manager.append(board, bhash, msg.chat, msg.from_user)
    # create a new keyboard
    keyboard = list()
    for row in range(board.height):
        current_row = list()
        for col in range(board.width):
            cell = InlineKeyboardButton(text=UNOPENED_CELL, callback_data="{} {} {}".format(bhash, row, col))
            current_row.append(cell)
        keyboard.append(current_row)
    # send the keyboard
    try:
        gmsg = bot.send_message(chat_id=msg.chat.id, text="路过的大爷～来扫个雷嘛～", reply_to_message_id=msg.message_id,
                                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception:
        game_manager.remove(bhash)
        raise
    game_manager.get_game_from_hash(bhash).msgid = gmsg.message_id

def send_help(update, context):
    logger.debug("Start from {0}".format(update.message.from_user.id))
    msg = update.message
    msg.reply_text("这是一个扫雷bot\n\n/mine 开始新游戏")

def send_source(update, context):
    logger.debug("Source from {0}".format(update.message.from_user.id))
    update.message.reply_text('Source code: https://git.jerryxiao.cc/Jerry/tgmsbot')

def send_status(update, context):
    logger.info("Status from {0}".format(update.message.from_user.id))
    count = game_manager.count()
    update.message.reply_text('当前进行的游戏: {}'.format(count))

def gen_reward(user, negative=True):
    ''' Reward the player :) '''
    def __chance(percentage):
        if randrange(0,10000)/10000 < percentage:
            return True
        else:
            return False
    def __floating(value):
        return randrange(8000,12000)/10000 * value
    def __lose_cards(cardnum):
        if cardnum <= 6:
            return 1
        else:
            return int(__floating(log(cardnum, 2)))
    def __get_cards(cardnum):
        if cardnum >= 2:
            cards = __floating(1 / log(cardnum, 100))
            if cards > 1.0:
                return int(cards)
            else:
                return int(__chance(cards))
        else:
            return int(__floating(8.0))
    # Negative rewards
    def restrict_mining(player):
        lost_cards = __lose_cards(player.immunity_cards)
        player.immunity_cards -= lost_cards
        if player.immunity_cards >= 0:
            ret = "用去{}张免疫卡，还剩{}张".format(lost_cards, player.immunity_cards)
        else:
            now = int(time.time())
            seconds = randint(30, 120)
            player.restricted_until = now + seconds
            ret = "没有免疫卡了，被限制扫雷{}秒".format(seconds)
        return ret
    # Positive rewards
    def give_immunity_cards(player):
        rewarded_cards = __get_cards(player.immunity_cards)
        player.immunity_cards += rewarded_cards
        if rewarded_cards == 0:
            return "共有{}张免疫卡".format(player.immunity_cards)
        else:
            return "被奖励了{}张免疫卡，共有{}张".format(rewarded_cards, player.immunity_cards)

    player = get_player(user.id)
    try:
        if negative:
            player.death += 1
            return restrict_mining(player)
        else:
            player.wins += 1
            return give_immunity_cards(player)
    finally:
        player.save()

def game_count(user):
    player = get_player(user.id)
    player.mines += 1
    player.save()

def check_restriction(user):
    player = get_player(user.id)
    now = int(time.time())
    if now >= player.restricted_until:
        return False
    else:
        return player.restricted_until - now

@run_async
def player_statistics(update, context):
    logger.info("Statistics from {0}".format(update.message.from_user.id))
    user = update.message.from_user
    player = get_player(user.id)
    mines = player.mines
    death = player.death
    wins = player.wins
    cards = player.immunity_cards
    TEMPLATE = "一共玩了{mines}局，爆炸{death}次，赢了{wins}局\n" \
               "口袋里有{cards}张免疫卡"
    update.message.reply_text(TEMPLATE.format(mines=mines, death=death,
                                              wins=wins, cards=cards))


def update_keyboard_request(context, bhash, game, chat_id, message_id):
    current_action_timestamp = time.time()
    if current_action_timestamp - game.last_action <= KBD_MIN_INTERVAL:
        logger.debug('Rate limit triggered.')
        game.last_action = current_action_timestamp
        job_queue.run_once(update_keyboard, KBD_DELAY_SECS,
                           context=(bhash, game, chat_id, message_id, current_action_timestamp))
    else:
        game.last_action = current_action_timestamp
        update_keyboard(context, noqueue=(bhash, game, chat_id, message_id))
def update_keyboard(context, noqueue=None):
    (bot, job) = (context.bot, context.job)
    if noqueue:
        (bhash, game, chat_id, message_id) = noqueue
    else:
        (bhash, game, chat_id, message_id, current_action_timestamp) = job.context
        if current_action_timestamp != game.last_action:
            logger.debug('New update action requested, abort this one.')
            return
    def gen_keyboard(board):
        keyboard = list()
        for row in range(board.height):
            current_row = list()
            for col in range(board.width):
                if board.map[row][col] <= 9:
                    cell_text = UNOPENED_CELL
                elif board.map[row][col] == 10:
                    cell_text = NUM_CELL_0
                elif board.map[row][col] == 19:
                    cell_text = FLAGGED_CELL
                elif board.map[row][col] == 20:
                    cell_text = STEPPED_CELL
                else:
                    cell_text = chr(NUM_CELL_ORD + board.map[row][col] - 10)
                cell = InlineKeyboardButton(text=cell_text, callback_data="{} {} {}".format(bhash, row, col))
                current_row.append(cell)
            keyboard.append(current_row)
        return keyboard
    keyboard = gen_keyboard(game.board)
    try:
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id,
                                        reply_markup=InlineKeyboardMarkup(keyboard))
    except (TimedOutError, RetryAfterError):
        logger.debug('time out in game {}.'.format(bhash))
        game.timeouts += 1
    except Exception:
        logger.critical(format_exc())

@run_async
def handle_button_click(update, context):
    bot = context.bot
    msg = update.callback_query.message
    user = update.callback_query.from_user
    chat_id = update.callback_query.message.chat.id
    data = update.callback_query.data
    logger.debug('Button clicked by {}, data={}.'.format(user.id, data))
    restriction = check_restriction(user)
    if restriction:
        bot.answer_callback_query(callback_query_id=update.callback_query.id,
                                  text="还有{}秒才能扫雷".format(restriction), show_alert=True)
        return
    bot.answer_callback_query(callback_query_id=update.callback_query.id)
    try:
        data = data.split(' ')
        data = [int(i) for i in data]
        (bhash, row, col) = data
    except:
        logger.info('Unknown callback data: {} from user {}'.format(data, user.id))
        return
    game = game_manager.get_game_from_hash(bhash)
    if game is None:
        logger.debug("No game found for hash {}".format(bhash))
        return
    try:
        if game.stopped:
            return
        game.lock.acquire()
        board = game.board
        if board.state == 0:
            mmap = None
        else:
            mmap = deepcopy(board.map)
        board.move((row, col))
        if board.state != 1:
            game.stopped = True
            game.lock.release()
            game.save_action(user, (row, col))
            if not array_equal(board.map, mmap):
                update_keyboard_request(context, bhash, game, chat_id, msg.message_id)
            (s_op, s_is, s_3bv) = board.gen_statistics()
            ops_count = game.actions_sum()
            ops_list = game.get_actions()
            last_player = game.get_last_player()
            time_used = time.time() - game.start_time
            timeouts = game.timeouts
            remain = 0
            ttl = 0
            if board.state == 2:
                reward = gen_reward(game.last_player, negative=False)
                template = WIN_TEXT_TEMPLATE
            elif board.state == 3:
                reward = gen_reward(game.last_player, negative=True)
                game.lives -= 1
                if game.lives <= 0:
                    template = LOSE_TEXT_TEMPLATE
                else:
                    game.stopped = False
                    board.state = 1
                    remain = game.lives
                    ttl = game.ttl_lives
                    template = STEP_TEXT_TEMPLATE
            else:
                # Should not reach here
                reward = None
            myreply = template.format(s_op=s_op, s_is=s_is, s_3bv=s_3bv, ops_count=ops_count,
                                    ops_list=ops_list, last_player=last_player,
                                    time=round(time_used, 4), timeouts=timeouts, reward=reward,
                                    remain=remain, ttl=ttl)
            try:
                msg.reply_text(myreply, parse_mode="Markdown")
            except (TimedOutError, RetryAfterError):
                logger.debug('timeout sending report for game {}'.format(bhash))
            except Exception:
                logger.critical(format_exc())
            if game.stopped:
                game_manager.remove(bhash)
        elif mmap is None or (not array_equal(board.map, mmap)):
            game.lock.release()
            game.save_action(user, (row, col))
            update_keyboard_request(context, bhash, game, chat_id, msg.message_id)
        else:
            game.lock.release()
    except:
        try:
            game.lock.release()
        except RuntimeError:
            pass
        raise


import cards
setattr(cards, 'get_player', get_player)
setattr(cards, 'game_manager', game_manager)
updater.dispatcher.add_handler(CommandHandler('getlvl', cards.getperm))
updater.dispatcher.add_handler(CommandHandler('setlvl', cards.setperm))
updater.dispatcher.add_handler(CommandHandler('lvlup', cards.lvlup))
updater.dispatcher.add_handler(CommandHandler('transfer', cards.transfer_cards))
updater.dispatcher.add_handler(CommandHandler('rob', cards.rob_cards))
updater.dispatcher.add_handler(CommandHandler('lottery', cards.cards_lottery))
updater.dispatcher.add_handler(CommandHandler('dist', cards.dist_cards))
updater.dispatcher.add_handler(CommandHandler('reveal', cards.reveal))
updater.dispatcher.add_handler(CallbackQueryHandler(cards.dist_cards_btn_click, pattern=r'dist'))


updater.dispatcher.add_handler(CommandHandler('start', send_help))
updater.dispatcher.add_handler(CommandHandler('list', list_games))
updater.dispatcher.add_handler(CommandHandler('mine', send_keyboard))
updater.dispatcher.add_handler(CommandHandler('status', send_status))
updater.dispatcher.add_handler(CommandHandler('stats', player_statistics))
updater.dispatcher.add_handler(CommandHandler('source', send_source))
updater.dispatcher.add_handler(CallbackQueryHandler(handle_button_click))
updater.job_queue.run_repeating(game_manager.do_garbage_collection, GARBAGE_COLLECTION_INTERVAL, first=30)
try:
    updater.start_polling()
    updater.idle()
finally:
    game_manager.save()
    logger.info('Game_manager saved.')
    db.close()
    logger.info('DB closed.')
