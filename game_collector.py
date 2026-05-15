import base64
import json
from datetime import datetime
import os
import psutil
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# localiza o processo do League Client e extrai:
# - porta da API LCU
# - senha
def get_lcu_credentials():
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            name = proc.info['name']

            if name and 'LeagueClientUx' in name:
                cmdline = proc.info['cmdline']

                port = None
                password = None

                for arg in cmdline:
                    if '--app-port=' in arg:
                        port = arg.split('=')[1]

                    if '--remoting-auth-token=' in arg:
                        password = arg.split('=')[1]

                if port and password:
                    return port, password

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return None, None

# Faz requests autenticadas para a LCU API
class LCUClient:
    def __init__(self, port, password):
        auth = base64.b64encode(f'riot:{password}'.encode()).decode()

        self.headers = {
            'Authorization': f'Basic {auth}'
        }

        self.base_url = f'https://127.0.0.1:{port}'

    def get(self, endpoint):
        url = self.base_url + endpoint

        response = requests.get(
            url,
            headers=self.headers,
            verify=False
        )

        response.raise_for_status()

        return response.json()

def get_champion_mapping(client):

    champs = client.get(
        '/lol-game-data/assets/v1/champion-summary.json'
    )

    mapping = {}

    for champ in champs:

        champion_id = champ.get('id')
        champion_name = champ.get('name')

        mapping[champion_id] = champion_name

    return mapping

# Recupera últimas partidas
def get_match_history(client, start=0, count=20):
    endpoint = (
        f'/lol-match-history/v1/products/lol/current-summoner/'
        f'matches?begIndex={start}&endIndex={start+count}'
    )

    return client.get(endpoint)

def get_match_detail(client, game_id):
    endpoint = (
        f'/lol-match-history/v1/games/{game_id}'
    )

    return client.get(endpoint)

# MAIN
def main():
    print('Procurando cliente do League...')
    custom_games = []

    port, password = get_lcu_credentials()

    if not port:
        print('League Client não encontrado.')
        return

    print(f'LCU encontrada na porta {port}')

    client = LCUClient(port, password)
    champion_mapping = get_champion_mapping(client)

    try:
        data = get_match_history(client)
        games = data.get('games', {}).get('games', [])

        # coleta as ultimas 20 partidas do historico
        # filtra as CUSTOM_GAME
        # salva o id de cada CUSTOM_GAME
        for game in games:
            if game.get('gameType') == "CUSTOM_GAME" and game.get('endOfGameResult') != "Abort_TooFewPlayers":
                custom_games.append(game.get('gameId'))

        # coleta detalhes de cada uma das partidas coletadas anteriormente
        details = []

        for gameId in custom_games:

            game = get_match_detail(client, gameId)

            blue_team = []
            red_team = []

            for player, champion in zip(
                    game.get('participantIdentities', []),
                    game.get('participants', [])
            ):

                player_data = {
                    'name': (
                        f"{player.get('player').get('gameName')}"
                        f"#{player.get('player').get('tagLine')}"
                    ),

                    'champion': champion_mapping[
                        champion.get('championId')
                    ]
                }

                # 100 = blue side
                if champion.get('teamId') == 100:
                    blue_team.append(player_data)

                # 200 = red side
                elif champion.get('teamId') == 200:
                    red_team.append(player_data)

            # conversao de tipos
            data = game.get('gameCreationDate')
            duracao = game.get('gameDuration')

            date_obj = datetime.fromisoformat(
                data.replace('Z', '+00:00')
            )

            formatted_date = date_obj.strftime(
                '%d/%m/%Y %H:%M:%S'
            )

            minutes = duracao // 60
            seconds = duracao % 60

            formatted_duration = f'{minutes}m {seconds}s'

            match_data = {
                'gameId': gameId,
                'date': formatted_date,
                'duration': formatted_duration,
                'blueTeam': blue_team,
                'redTeam': red_team
            }


            details.append(match_data)

        print(details)

        with open('matches.json', 'w', encoding='utf-8') as f:
            json.dump(details, f, indent=4, ensure_ascii=False)

    except requests.HTTPError as e:
        print('Erro ao acessar LCU API:')
        print(e)

if __name__ == '__main__':
    main()