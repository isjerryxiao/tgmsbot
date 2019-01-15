#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from mscore import Board, check_params
from copy import deepcopy
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, run_async
from telegram.error import TimedOut as TimedOutError
from numpy import array_equal
# If no peewee orm is installed, try `from data_ram import get_player`
from data import get_player
from random import randint, choice
import time
import logging

logging.basicConfig(level=logging.INFO,format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

token = "token_here"
updater = Updater(token, workers=8)
job_queue = updater.job_queue
job_queue.start()

KBD_MIN_INTERVAL = 0.5
KBD_DELAY_SECS = 0.5

HEIGHT = 8
WIDTH = 8
MINES = 9

UNOPENED_CELL = "\u2588"
FLAGGED_CELL = "\u259a"
STEPPED_CELL = "*"

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

class Game():
    def __init__(self, board, group, creator, lives=1):
        self.board = board
        self.group = group
        self.creator = creator
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

class GameManager:
    __games = dict()
    def append(self, board, board_hash, group_id, creator_id):
        lives = int(board.mines/3)
        if lives <= 0:
            lives = 1
        self.__games[board_hash] = Game(board, group_id, creator_id, lives=lives)
    def remove(self, board_hash):
        board = self.get_game_from_hash(board_hash)
        if board:
            del self.__games[board_hash]
            return True
        else:
            return False
    def get_game_from_hash(self, board_hash):
        return self.__games.get(board_hash, None)
    def count(self):
        return len(self.__games)

game_manager = GameManager()


@run_async
def send_keyboard(bot, update, args):
    msg = update.message
    logger.info("Mine from {0}".format(update.message.from_user.id))
    if check_restriction(update.message.from_user):
        update.message.reply_text("爆炸这么多次还想扫雷？")
        return
    # create a game board
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
    bot.send_message(chat_id=msg.chat.id, text="路过的大爷～来扫个雷嘛～", reply_to_message_id=msg.message_id,
                     parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

def send_help(bot, update):
    logger.debug("Start from {0}".format(update.message.from_user.id))
    msg = update.message
    msg.reply_text("这是一个扫雷bot\n\n/mine 开始新游戏")

def send_source(bot, update):
    logger.debug("Source from {0}".format(update.message.from_user.id))
    update.message.reply_text('Source code: https://git.jerryxiao.cc/Jerry/tgmsbot')

def send_status(bot, update):
    logger.info("Status from {0}".format(update.message.from_user.id))
    count = game_manager.count()
    update.message.reply_text('当前进行的游戏: {}'.format(count))

def gen_reward(user, negative=True):
    ''' Reward the player :) '''
    # Negative rewards
    def restrict_mining(player):
        if player.immunity_cards >= 1:
            if player.immunity_cards >= 10:
                lost_cards = randint(2,4)
            elif player.immunity_cards >= 5:
                lost_cards = randint(1,3)
            else:
                lost_cards = 1
            player.immunity_cards -= lost_cards
            ret = "用去{}张免疫卡，还剩{}张".format(lost_cards, player.immunity_cards)
        else:
            now = int(time.time())
            seconds = randint(30, 120)
            player.restricted_until = now + seconds
            ret = "没有免疫卡了，被限制扫雷{}秒".format(seconds)
        player.save()
        return ret
    # Positive rewards
    def give_immunity_cards(player):
        rewarded_cards = 0
        if player.immunity_cards <= 3:
            rewarded_cards = randint(1, 2)
        elif player.immunity_cards <= 10:
            if randint(1, 5) == 5:
                rewarded_cards = 1
        elif randint(1, 10) == 10:
            rewarded_cards = 1
        player.immunity_cards += rewarded_cards
        player.save()
        if rewarded_cards == 0:
            return "共有{}张免疫卡".format(player.immunity_cards)
        else:
            return "被奖励了{}张免疫卡，共有{}张".format(rewarded_cards, player.immunity_cards)

    player = get_player(user.id)
    if negative:
        player.death += 1
        return restrict_mining(player)
    else:
        player.wins += 1
        return give_immunity_cards(player)

def game_count(user):
    player = get_player(user.id)
    player.mines += 1
    player.save()

def check_restriction(user):
    player = get_player(user.id)
    player.db_close()
    now = int(time.time())
    if now >= player.restricted_until:
        return False
    else:
        return player.restricted_until - now

@run_async
def player_statistics(bot, update):
    logger.info("Statistics from {0}".format(update.message.from_user.id))
    user = update.message.from_user
    player = get_player(user.id)
    player.db_close()
    mines = player.mines
    death = player.death
    wins = player.wins
    cards = player.immunity_cards
    TEMPLATE = "一共玩了{mines}局，爆炸{death}次，赢了{wins}局\n" \
               "口袋里有{cards}张免疫卡"
    update.message.reply_text(TEMPLATE.format(mines=mines, death=death,
                                              wins=wins, cards=cards))


def update_keyboard_request(bot, bhash, game, chat_id, message_id):
    current_action_timestamp = time.time()
    if current_action_timestamp - game.last_action <= KBD_MIN_INTERVAL:
        logger.debug('Rate limit triggered.')
        game.last_action = current_action_timestamp
        job_queue.run_once(update_keyboard, KBD_DELAY_SECS,
                           context=(bhash, game, chat_id, message_id, current_action_timestamp))
    else:
        game.last_action = current_action_timestamp
        update_keyboard(bot, None, noqueue=(bhash, game, chat_id, message_id))
def update_keyboard(bot, job, noqueue=None):
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
                    cell_text = " "
                elif board.map[row][col] == 19:
                    cell_text = FLAGGED_CELL
                elif board.map[row][col] == 20:
                    cell_text = STEPPED_CELL
                else:
                    cell_text = str(board.map[row][col] - 10)
                cell = InlineKeyboardButton(text=cell_text, callback_data="{} {} {}".format(bhash, row, col))
                current_row.append(cell)
            keyboard.append(current_row)
        return keyboard
    keyboard = gen_keyboard(game.board)
    try:
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id,
                                        reply_markup=InlineKeyboardMarkup(keyboard))
    except TimedOutError:
        logger.debug('time out in game {}.'.format(bhash))
        game.timeouts += 1

@run_async
def handle_button_click(bot, update):
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
    elif game.stopped:
        return
    board = game.board
    if board.state == 0:
        mmap = None
        board.move((row, col))
        game.save_action(user, (row, col))
        update_keyboard_request(bot, bhash, game, chat_id, msg.message_id)
    else:
        mmap = deepcopy(board.map)
        board.move((row, col))
    if board.state != 1:
        game.stopped = True
        # if this is the first move, there's no mmap
        if mmap is not None:
            game.save_action(user, (row, col))
            if not array_equal(board.map, mmap):
                update_keyboard_request(bot, bhash, game, chat_id, msg.message_id)
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
        except TimedOutError:
            logger.debug('timeout sending report for game {}'.format(bhash))
        if game.stopped:
            game_manager.remove(bhash)
    elif mmap is not None and (not array_equal(board.map, mmap)):
        game.save_action(user, (row, col))
        update_keyboard_request(bot, bhash, game, chat_id, msg.message_id)



updater.dispatcher.add_handler(CommandHandler('start', send_help))
updater.dispatcher.add_handler(CommandHandler('mine', send_keyboard, pass_args=True))
updater.dispatcher.add_handler(CommandHandler('status', send_status))
updater.dispatcher.add_handler(CommandHandler('stats', player_statistics))
updater.dispatcher.add_handler(CommandHandler('source', send_source))
updater.dispatcher.add_handler(CallbackQueryHandler(handle_button_click))
updater.start_polling()
updater.idle()
