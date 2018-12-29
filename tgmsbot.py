#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from mscore import Board, check_params
from copy import deepcopy
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
from numpy import array_equal
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
    def __init__(self, board, board_hash, group, creators):
        self.board = board
        self.board_hash = board_hash
        self.group = group
        self.creators = creators
        self.actions = dict()
    def save_action(self, user, spot):
        '''spot is supposed to be a tuple'''
        if self.actions.get(user, None):
            self.actions[user].append(spot)
        else:
            self.actions[user] = [spot,]
    def get_actions(self):
        '''Convert actions into text'''
        msg = ""
        for user in self.actions:
            count = len(self.actions.get(user, list()))
            msg = "{}{}: {}项操作\n".format(msg, display_username(user), count)
        return msg

class GameManager:
    __games = list()
    def append(self, board, board_hash, group_id, creator_id):
        self.__games.append(Game(board, board_hash, group_id, creator_id))
    def remove(self, board_hash):
        board = self.get_game_from_hash(board_hash)
        if board:
            self.__games.remove(board)
            return True
        else:
            return False
    def get_game_from_hash(self, board_hash):
        for gm in self.__games:
            if gm.board_hash == board_hash:
                return gm
        else:
            return None
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

def send_source(bot, update):
    logger.debug("Source from {0}".format(update.message.from_user.id))
    update.message.reply_text('Source code: https://git.jerryxiao.cc/Jerry/tgmsbot')

def send_status(bot, update):
    logger.info("Status from {0}".format(update.message.from_user.id))
    count = game_manager.count()
    update.message.reply_text('当前进行的游戏: {}'.format(count))

def gen_keyboard(board):
    pass

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
        logger.info("No game found for hash {}".format(bhash))
        return
    board = game.board
    FIRST_MOVE = False
    if board.state == 0:
        FIRST_MOVE = True
    else:
        mmap = deepcopy(board.map)
    board.move((row, col))
    if FIRST_MOVE or (not array_equal(board.map, mmap)) or board.state == 2:
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
        if board.state != 1:
            if board.state == 2:
                reply_text = "Win"
                game_manager.remove(bhash)
            elif board.state == 3:
                reply_text = "Lose"
                game_manager.remove(bhash)
        else:
            reply_text = msg.text_markdown
        bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id,
                              text=reply_text, parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup(keyboard))


updater.dispatcher.add_handler(CommandHandler('start', send_help))
updater.dispatcher.add_handler(CommandHandler('mine', send_keyboard, pass_args=True))
updater.dispatcher.add_handler(CommandHandler('status', send_status))
updater.dispatcher.add_handler(CommandHandler('source', send_source))
updater.dispatcher.add_handler(CallbackQueryHandler(handle_button_click))
updater.start_polling()
updater.idle()
