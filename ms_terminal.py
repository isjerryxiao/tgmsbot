#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from mscore import Board
from copy import deepcopy

board = Board(8,8,1)

while True:
    ip = input("row, col: ")
    try:
        (row, col) = ip.split(',')
        row = int(row)
        col = int(col)
    except Exception as err:
        print(type(err), ': ', err)
        continue
    board.move((row, col))
    bmap = deepcopy(board.map)
    for i in range(8):
        for j in range(8):
            if bmap[i][j] <= 9:
                bmap[i][j] = 10
            elif bmap[i][j] >= 10:
                bmap[i][j] -= 10
    print(board.map)
    print("   0  1  2  3  4  5  6  7")
    print(bmap)
    if board.state != 1:
        print('exit ', board.state)
        break