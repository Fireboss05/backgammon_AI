import queue
import threading
import json
import time

from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin

from src.launch_java_AI import launch_java_game
from src.move_not_possible_exception import MoveNotPossibleException
from src.board import Board
from src.colour import Colour
from src.compare_all_moves_strategy import CompareAllMovesSimple, \
    CompareAllMovesWeightingDistanceAndSingles, \
    CompareAllMovesWeightingDistanceAndSinglesWithEndGame, \
    CompareAllMovesWeightingDistanceAndSinglesWithEndGame2
from src.strategies import MoveRandomPiece, MoveFurthestBackStrategy
from src.game import Game
from random import randint
from src.strategies import Strategy

import logging

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)
cors = CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'

moves_to_make = queue.Queue()
move_results = queue.Queue()

black_moves_to_make = queue.Queue()
black_move_results = queue.Queue()

current_board = []
current_roll = []
used_die_rolls = []

to_play = -1


def set_current_move(dice_roll):
    current_roll.insert(0, dice_roll)
    del current_roll[1:]
    used_die_rolls.insert(0, [])
    del used_die_rolls[1:]


def game_thread(difficulty):
    class ApiStrategy(Strategy):

        def __init__(self) -> None:
            self.board_after_your_last_turn = Board.create_starting_board()

        def move(self, board, colour, dice_roll, make_move, opponents_activity):
            set_current_move(dice_roll.copy())

            global to_play
            to_play = colour

            board_json_before_opp_move = self.board_after_your_last_turn.to_json()

            def map_move(move):
                self.board_after_your_last_turn.move_piece(
                    self.board_after_your_last_turn.get_piece_at(move['start_location']),
                    move['die_roll']
                )
                move['board_after_move'] = self.board_after_your_last_turn.to_json()
                return move

            print('[Game]: Sending opponents activity (end of previous turn, start of new turn)')
            move_results.put({
                'result': 'success',
                'opponents_activity': {
                    'opponents_move': [map_move(move) for move in opponents_activity['opponents_move']],
                    'dice_roll': opponents_activity['dice_roll'],
                },
                'board_after_your_last_turn': board_json_before_opp_move,
            })
            while len(dice_roll) > 0:
                print('[Game]: Waiting for moves_to_make...')
                move = moves_to_make.get()
                if move == 'end_game':
                    print('[Game]: ...got end_game, so crashing')
                    raise Exception("Game ended")
                elif move == 'end_turn':
                    print('[Game]: ...got end_turn')
                    break
                print('[Game]: ...got move')
                try:
                    rolls_moved = make_move(move['location'], move['die_roll'])
                    for roll in rolls_moved:
                        dice_roll.remove(roll)
                        used_die_rolls[0].append(roll)

                    if len(dice_roll) > 0:
                        print('[Game]: Sending move success (middle of go)')
                        move_results.put({
                            'result': 'success'
                        })
                except:
                    print('[Game]: Sending move failed')
                    move_results.put({
                        'result': 'move_failed'
                    })

            self.board_after_your_last_turn = board.create_copy()
            print('[Game]: Done last move of turn. Going to wait for opponent information')

        def game_over(self, opponents_activity):
            board_json_before_opp_move = self.board_after_your_last_turn.to_json()

            def map_move(move):
                self.board_after_your_last_turn.move_piece(
                    self.board_after_your_last_turn.get_piece_at(move['start_location']),
                    move['die_roll']
                )
                move['board_after_move'] = self.board_after_your_last_turn.to_json()
                return move

            print('[Game]: Sending opponents activity (end of game)')
            move_results.put({
                'result': 'success',
                'opponents_activity': {
                    'opponents_move': [map_move(move) for move in opponents_activity['opponents_move']],
                    'dice_roll': opponents_activity['dice_roll'],
                },
                'board_after_your_last_turn': board_json_before_opp_move,
            })

    class ApiBlackStrategy(Strategy):

        def __init__(self) -> None:
            self.board_after_your_last_turn = Board.create_starting_board()

        def move(self, board, colour, dice_roll, make_move, opponents_activity):
            set_current_move(dice_roll.copy())

            global to_play
            to_play = colour

            board_json_before_opp_move = self.board_after_your_last_turn.to_json()

            def map_move(move):
                self.board_after_your_last_turn.move_piece(
                    self.board_after_your_last_turn.get_piece_at(move['start_location']),
                    move['die_roll']
                )
                move['board_after_move'] = self.board_after_your_last_turn.to_json()
                return move

            print('[Game]: Sending opponents activity (end of previous turn, start of new turn)')
            black_move_results.put({
                'result': 'success',
                'opponents_activity': {
                    'opponents_move': [map_move(move) for move in opponents_activity['opponents_move']],
                    'dice_roll': opponents_activity['dice_roll'],
                },
                'board_after_your_last_turn': board_json_before_opp_move,
            })
            while len(dice_roll) > 0:
                print('[Game]: Waiting for black_moves_to_make...')
                move = black_moves_to_make.get()
                if move == 'end_game':
                    print('[Game]: ...got end_game, so crashing')
                    raise Exception("Game ended")
                elif move == 'end_turn':
                    print('[Game]: ...got end_turn')
                    break
                print('[Game]: ...got move')
                try:
                    rolls_moved = make_move(move['location'], move['die_roll'])
                    for roll in rolls_moved:
                        dice_roll.remove(roll)
                        used_die_rolls[0].append(roll)

                    if len(dice_roll) > 0:
                        print('[Game]: Sending move success (middle of go)')
                        black_move_results.put({
                            'result': 'success'
                        })
                except:
                    print('[Game]: Sending move failed')
                    black_move_results.put({
                        'result': 'move_failed'
                    })

            self.board_after_your_last_turn = board.create_copy()
            print('[Game]: Done last move of turn. Going to wait for opponent information')

    print(difficulty)
    if difficulty == 'veryeasy':
        opponent_strategy = MoveFurthestBackStrategy()
    elif difficulty == 'easy':
        opponent_strategy = CompareAllMovesSimple()
    elif difficulty == 'medium':
        opponent_strategy = CompareAllMovesWeightingDistanceAndSingles()
    elif difficulty == 'hard':
        opponent_strategy = CompareAllMovesWeightingDistanceAndSinglesWithEndGame()
    elif difficulty == 'veryhard':
        opponent_strategy = CompareAllMovesWeightingDistanceAndSinglesWithEndGame2()
    elif difficulty == "expectiminimax":
        opponent_strategy = ApiBlackStrategy()
        thread = threading.Thread(target=launch_java_game, args=(1, "black", "expectiminimax"))
        thread.start()
    elif difficulty == "*-minimax":
        opponent_strategy = ApiBlackStrategy()
        thread = threading.Thread(target=launch_java_game, args=(2, "black", "*-minimax"))
        thread.start()
    elif difficulty == "mcgammon":
        opponent_strategy = ApiBlackStrategy()
        # thread = threading.Thread(target=launch_java_game, args=(1, "black", "mcgammon"))
        # thread.start()

    else:
        raise Exception('Not a valid strategy')

    print('[Game]: Starting game with strategy %s' % opponent_strategy.__class__.__name__)

    game = Game(
        white_strategy=ApiStrategy(),
        black_strategy=opponent_strategy,
        first_player=Colour(randint(0, 1))
    )
    current_board.append(game.board)
    game.run_game(verbose=False)

    # Thread is only ended by an 'end_game' move
    while True:
        print('[Game]: run_game has completed, waiting for moves_to_make...')
        if moves_to_make.get() == 'end_game':
            print('[Game] ... got end_game (in final bit)')
            break
        else:
            print('[Game] ... got non-end_game (in final bit)')
            move_results.put({
                        'result': 'move_failed'
                    })
        if black_moves_to_make.get() == 'end_game':
            print('[Game] ... got end_game (in final bit)')
            break
        else:
            print('[Game] ... got non-end_game (in final bit)')
            black_move_results.put({
                        'result': 'move_failed'
                    })



def get_state(response={}, colour=Colour.WHITE):
    if len(current_board) == 0:
        return {'board': "{}", 'dice_roll': [], 'used_rolls': []}
    board = current_board[0]
    move = current_roll[0]

    moves_left = move.copy()
    for used_move in used_die_rolls[0]:
        moves_left.remove(used_move)

    state = {'board': board.to_json(),
             'dice_roll': move,
             'used_rolls': used_die_rolls[0],
             'player_can_move': not board.no_moves_possible(colour, moves_left),
             'to_play':to_play.value}
    if board.has_game_ended():
        state['winner'] = str(board.who_won())
    if 'opponents_activity' in response:
        # dict, keys: start_location, die_roll, end_location
        opponents_activity = response['opponents_activity']
        state['opp_move'] = opponents_activity['opponents_move']
        state['opp_roll'] = opponents_activity['dice_roll']
    if 'board_after_your_last_turn' in response:
        state['board_after_your_last_turn'] = response['board_after_your_last_turn']
    if 'result' in response:
        state['result'] = response['result']

    return state


@app.route('/start-game')
@cross_origin()
def start_game():
    return get_state()

@app.route('/black/start-game')
@cross_origin()
def black_start_game():
    return get_state(colour=Colour.BLACK)


@app.route('/move-piece')
@cross_origin()
def move_piece():
    print('[API]: move-piece called')
    if to_play.value == 0:
        location = request.args.get('location', default=1, type=int)
        die_roll = request.args.get('die-roll', default=1, type=int)
        end_turn = request.args.get('end-turn', default='', type=str)
        print(end_turn)
        if end_turn == 'true':
            print('[API]: Sending end_turn...')
            moves_to_make.put('end_turn')
        else:
            print('[API]: Sending moves_to_make...')
            moves_to_make.put({
                'location': location,
                'die_roll': die_roll
            })
        print('[API]: Waiting for move_results...')
        response = move_results.get()
        print('[API]: ...got result, responding to frontend')
        return get_state(response)
    else:
        return {
            "error": "not your turn",
            "your_turn": False
        }, 403

@app.route('/black/move-piece')
@cross_origin()
def black_move_piece():
    print('[API]: black-move-piece called')
    if to_play.value == 1:
        location = request.args.get('location', default=1, type=int)
        die_roll = request.args.get('die-roll', default=1, type=int)
        end_turn = request.args.get('end-turn', default='', type=str)
        print(end_turn)
        if end_turn == 'true':
            print('[API]: Sending end_turn...')
            black_moves_to_make.put('end_turn')
        else:
            print('[API]: Sending moves_to_make...')
            black_moves_to_make.put({
                'location': location,
                'die_roll': die_roll
            })
        print('[API]: Waiting for move_results...')
        response = black_move_results.get()
        print('[API]: ...got result, responding to frontend')
        return get_state(response)
    else:
        return {
            "error": "not your turn",
            "your_turn": False
        }, 403

@app.route('/new-game')
@cross_origin()
def new_game():
    difficulty = request.args.get('difficulty', default='hard', type=str)
    print(difficulty)
    print('[API]: new-game called')
    if len(current_board) != 0:
        print('[API]: Sending end_game')
        moves_to_make.put('end_game')
        black_moves_to_make.put('end_game')
    current_board.clear()
    current_roll.clear()
    time.sleep(1)
    print('[API]: Starting new game thread')
    threading.Thread(target=game_thread, args=[difficulty]).start()
    print('[API]: Waiting for move_results...')
    response = move_results.get()
    print('[API]: ...got result, responding to frontend')
    return get_state(response)

@app.route('/get-possible-moves', methods=['POST'])
@cross_origin()
def get_possible_moves():
    print('[API]: get-possible-moves called')
    data = request.get_json()

    board_data = data.get("board")
    colour = Colour.load(data.get("colour").lower())
    dice_rolls = data.get("dice_roll")  # ex: [5], [3,3,3,3], etc.

    # Reconstruire un Board à partir du dict
    board = Board.reconstruct_board_from_data(board_data)

    bar_location = 0 if colour == Colour.WHITE else 25
    has_piece_on_zero = any(piece.location == bar_location for piece in board.get_pieces(colour))

    seen_moves = set()

    # Formatage du résultat : list of dicts
    response = []

    for die_roll in dice_rolls:
        for piece in board.get_pieces(colour):
            if has_piece_on_zero and piece.location != bar_location:
                continue  # On ignore tous les pions sauf ceux en 0

            if board.is_move_possible(piece, die_roll):
                move_key = (piece.location, die_roll)
                if move_key not in seen_moves:
                    seen_moves.add(move_key)
                    response.append({
                        "from": piece.location,
                        "die_roll": die_roll
                    })

    return jsonify(response)

@app.route('/simul-move', methods=['POST'])
@cross_origin()
def simul_moves():
    print('[API]: simul-move called')
    data = request.get_json()

    board_data = data.get("board")
    die_data = data.get("die")
    location_data = data.get("location")

    # Reconstruire un Board à partir du dict
    board = Board.reconstruct_board_from_data(board_data)
    
    new_board = board.simul_move(location_data, die_data)

    board_json_str = new_board.to_json()  # renvoie JSON string
    board_dict = json.loads(board_json_str)  # parse en dict Python

    # Retourner dict complet comme dans get_state
    response = {
        'board': board_dict,
        # tu peux ajouter d'autres infos si besoin, par exemple:
        # 'dice_roll': [...], 'used_rolls': [...], 'player_can_move': ...
    }

    return response

@app.route('/simul-multi-move', methods=['POST'])
@cross_origin()
def simul_multi_moves():
    print('[API]: simul-move called')
    data = request.get_json()

    board_data = data.get("board")
    moves_data = data.get("moves")

    # Reconstruire un Board à partir du dict
    board = Board.reconstruct_board_from_data(board_data)
    
    responses = []

    for move in moves_data:
        die = move.get("die_roll")
        location = move.get("from")

        if die is None or location is None:
            continue  # ou return error 400 if you prefer stricter validation

        try:
            # Important : clone le board avant de simuler
            new_board = board.simul_move(location, die)

            board_json_str = new_board.to_json()  # renvoie JSON string
            board_dict = json.loads(board_json_str)
            responses.append({
                "board":board_dict
            })

        except Exception as e:
            # responses.append({
            #     "error": f"Invalid move from {location} with die {die}: {str(e)}"
            # })
            new_board = board.create_copy()
            board_json_str = new_board.to_json()  # renvoie JSON string
            board_dict = json.loads(board_json_str)
            responses.append({
                "board":board
            })

    return jsonify(responses)

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
