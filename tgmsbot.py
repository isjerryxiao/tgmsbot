#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from mscore import Board, check_params
from copy import deepcopy
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
from telegram.error import TimedOut as TimedOutError
from numpy import array_equal
import time
import logging

logging.basicConfig(level=logging.INFO,format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

token = "token_here"
updater = Updater(token, workers=16)

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
                    "/mine 开始新游戏"
LOSE_TEXT_TEMPLATE = "一道火光之后，你就在天上飞了呢…好奇怪喵\n" \
                    "地图：Op {s_op} / Is {s_is} / 3bv {s_3bv}\n操作总数 {ops_count}\n" \
                    "统计：\n{ops_list}\n{last_player} 是我们中出的叛徒！\n\n" \
                    "用时{time}秒，超时{timeouts}次\n\n" \
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
    def __init__(self, board, group, creator):
        self.board = board
        self.group = group
        self.creator = creator
        self.actions = dict()
        self.last_player = None
        self.start_time = time.time()
        self.extra = {"timeout": 0}
    def save_action(self, user, spot):
        '''spot is supposed to be a tuple'''
        self.last_player = user
        if self.actions.get(user, None):
            self.actions[user].append(spot)
        else:
            self.actions[user] = [spot,]
    def actions_sum(self):
        mysum = 0
        for user in self.actions:
            count = len(self.actions.get(user, list()))
            mysum += count
        return mysum
    def get_last_player(self):
        return display_username(self.last_player)
    def get_actions(self):
        '''Convert actions into text'''
        msg = ""
        for user in self.actions:
            count = len(self.actions.get(user, list()))
            msg = "{}{} - {}项操作\n".format(msg, display_username(user), count)
        return msg

class GameManager:
    __games = dict()
    def append(self, board, board_hash, group_id, creator_id):
        self.__games[board_hash] = Game(board, group_id, creator_id)
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



def send_keyboard(bot, update, args):
    msg = update.message
    logger.info("Mine from {0}".format(update.message.from_user.id))
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
    msg = update.message
    msg.reply_text("这是一个扫雷bot\n\n/mine 开始新游戏")
    logger.debug("Start from {0}".format(update.message.from_user.id))

def send_source(bot, update):
    logger.debug("Source from {0}".format(update.message.from_user.id))
    update.message.reply_text('Source code: https://git.jerryxiao.cc/Jerry/tgmsbot')

def send_status(bot, update):
    logger.info("Status from {0}".format(update.message.from_user.id))
    count = game_manager.count()
    update.message.reply_text('当前进行的游戏: {}'.format(count))

def update_keyboard(bot, bhash, game, chat_id, message_id):
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
        game.extra["timeout"] += 1

def handle_button_click(bot, update):
    msg = update.callback_query.message
    user = update.callback_query.from_user
    chat_id = update.callback_query.message.chat.id
    data = update.callback_query.data
    logger.debug('Button clicked by {}, data={}.'.format(user.id, data))
    bot.answer_callback_query(callback_query_id=update.callback_query.id)
    try:
        data = data.split(' ')
        data = [int(i) for i in data]
        (bhash, row, col) = data
    except Exception as err:
        logger.info('Unknown callback data: {} from user {}'.format(data, user.id))
        return
    game = game_manager.get_game_from_hash(bhash)
    if game is None:
        logger.debug("No game found for hash {}".format(bhash))
        return
    board = game.board
    if board.state == 0:
        mmap = None
        board.move((row, col))
        game.save_action(user, (row, col))
        update_keyboard(bot, bhash, game, chat_id, msg.message_id)
    else:
        mmap = deepcopy(board.map)
        board.move((row, col))
    if board.state != 1:
        # if this is the first move, there's no mmap
        if mmap is not None:
            game.save_action(user, (row, col))
            update_keyboard(bot, bhash, game, chat_id, msg.message_id)
        (s_op, s_is, s_3bv) = board.gen_statistics()
        ops_count = game.actions_sum()
        ops_list = game.get_actions()
        last_player = game.get_last_player()
        time_used = time.time() - game.start_time
        timeouts = game.extra["timeout"]
        if board.state == 2:
            template = WIN_TEXT_TEMPLATE
        else:
            template = LOSE_TEXT_TEMPLATE
        myreply = template.format(s_op=s_op, s_is=s_is, s_3bv=s_3bv, ops_count=ops_count,
                                            ops_list=ops_list, last_player=last_player,
                                            time=round(time_used, 4), timeouts=timeouts)
        msg.reply_text(myreply, parse_mode="Markdown")
        game_manager.remove(bhash)
    else:
        if mmap is not None and (not array_equal(board.map, mmap)):
            game.save_action(user, (row, col))
            update_keyboard(bot, bhash, game, chat_id, msg.message_id)



updater.dispatcher.add_handler(CommandHandler('start', send_help))
updater.dispatcher.add_handler(CommandHandler('mine', send_keyboard, pass_args=True))
updater.dispatcher.add_handler(CommandHandler('status', send_status))
updater.dispatcher.add_handler(CommandHandler('source', send_source))
updater.dispatcher.add_handler(CallbackQueryHandler(handle_button_click))
updater.start_polling()
updater.idle()
