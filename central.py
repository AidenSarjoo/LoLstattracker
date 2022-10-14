from flask import Flask, request

from riotwatcher import LolWatcher, ApiError
import time
from collections import defaultdict
import pandas as pd


class Form(object):
    def __init__(self, app, **configs):
        self.app = app
        self.configs(**configs)

    def configs(self, **configs):
        for config, value in configs:
            self.app.config[config.upper()] = value

    def create_endpoint(self, endpt=None, endpt_name=None, handler=None, methods=['POST', 'GET']):
        self.app.add_url_rule(endpt, endpt_name, handler, methods=methods)

    def run(self, **kwargs):
        self.app.run(**kwargs)


flask_app = Flask(__name__)

app = Form(flask_app)


def receive_input():
    # if POST request
    if request.method == 'POST':
        user = request.form.get('user')
        region = request.form.get('region')
        info = UserData(user, region)
        return info.display_stat_comparison()

    # generates the submission form
    return '''
           <form method="POST">
               <div><label>User: <input type="text" name="user"></label>
               <label>Region: <input type="text" name="region" value="na1"></label></div>
               <input type="submit" value="Submit">
           </form>'''


class UserData:
    def __init__(self, user, region, apikey=''):
        self.user = user
        self.region = region
        self.watcher = LolWatcher(apikey)
        self.latest = self.watcher.data_dragon.versions_for_region(self.region)['n']['champion']
        self.info = self.pull_account_info()
        self.matches = self.pull_match_info()

    def pull_account_info(self):
        return self.watcher.summoner.by_name(self.region, self.user)

    def pull_match_info(self, count=40):
        return self.watcher.match.matchlist_by_puuid(self.region, self.info['puuid'], count=count)

    def pull_user_info_from_match(self, matches):
        player_info = []
        match_count = 0
        for match in matches:
            players_in_match = self.watcher.match.by_id(self.region, match)['info']['participants']
            if match_count == 15:
                time.sleep(1)
                match_count = 0
            for player in players_in_match:
                if player['puuid'] == self.info['puuid']:
                    player_info.append(player)
        return player_info  # returns list of only the user's info from the matches

    def calculate_winrate(self, player_info):
        win_count = 0
        for match in player_info:
            if match['win']:
                win_count += 1
        return round((win_count / len(player_info)) * 100, 2)  # calculates wr

    def calculate_stats(self, matches,
                        stat_queries=None):
        if stat_queries is None:
            stat_queries = ['kills', 'deaths', 'assists', 'totalDamageDealtToChampions', 'kda',
                            'champLevel']
        player_info = self.pull_user_info_from_match(matches)
        player_stats = {}
        time.sleep(1)
        player_stats['mpc'] = self.calculate_mpc(player_info)
        player_stats['wr'] = self.calculate_winrate(player_info)
        for stat in stat_queries:
            player_stats[stat] = round(self.calculate_avg(player_info, stat), 2)
        return player_stats

    def calculate_avg(self, player_info, stat):
        total = 0
        for match in player_info:
            if stat == 'kda':
                total += match['challenges']['kda']
            else:
                total += match[stat]
        return total / len(player_info)

    def calculate_mpc(self, player_info):
        champs = defaultdict(int)
        for match in player_info:
            champ = match['championName']
            champs[champ] += 1
        return max(champs, key=champs.get) # returns the player's most used champs from the player's match data

    def compare_stats(self, old_stats, new_stats):
        comparisons = {}
        for key in old_stats:
            comparisons[key] = 0
        comparison = round(old_stats['wr'] - new_stats['wr'], 2)
        comparisons['wr'] = comparison
        for key in old_stats:
            if key != 'wr' and key != 'mpc':
                comparison = old_stats[key] - new_stats[key]
                comparisons[key] = comparison
        return comparisons

    def display_stat_comparison(self, matches=None):
        if matches is None:
            matches = self.matches
        new_stats = self.calculate_stats(matches[0:(len(matches) // 2) - 1])
        old_stats = self.calculate_stats(matches[len(matches) // 2:len(matches) - 1])
        comparisons = self.compare_stats(old_stats, new_stats)
        if comparisons['wr'] > 0:
            change = "decreased"
        else:
            change = "increased"

        header = '''<div><h1>{}, your winrate has {} by {}% over the last {} matches!</h1></div>'''. format(self.user, change, str(abs(comparisons['wr'])), str(len(matches)//2))
        if comparisons['wr'] == 0:
            header = '''<div><h1>{}, your winrate has stayed the same over the last {} matches!</h1></div>'''.format(self.user, str(len(matches)//2))

        body = '''<div>The rest of your stat changes are:</div>'''
        old_KDA = "{}/{}/{} ({})".format(old_stats['kills'], old_stats['deaths'], old_stats['assists'], old_stats['kda'])
        new_KDA = "{}/{}/{} ({})".format(new_stats['kills'], new_stats['deaths'], new_stats['assists'], new_stats['kda'])
        body += '''<div>Average KDA: {} &#8594; {} </div>'''.format(old_KDA, new_KDA)
        checked_stats = ['mpc', 'wr','kills','deaths','assists','kda']
        for stat in comparisons:
            if stat not in checked_stats:
                body += "<div>Average {}: {} &#8594; {}</div>".format(stat, old_stats[stat],new_stats[stat])
        old_mpc = old_stats['mpc']
        old_mpc_image = 'https://ddragon.leagueoflegends.com/cdn/{}/img/champion/{}.png'.format(self.latest, old_mpc)
        new_mpc = new_stats['mpc']
        new_mpc_image = 'https://ddragon.leagueoflegends.com/cdn/{}/img/champion/{}.png'.format(self.latest, new_mpc)
        body += '''<div> Your most played champ went from {} to {}</div>
                    <div><img src={} alt={}> <b>&#8594;</b1> <img src={} alt = {}></div>'''.format(old_mpc, new_mpc,old_mpc_image, old_mpc, new_mpc_image, new_mpc)
        return header + body

    def __str__(self):
        txt = ""
        for key in self.info:
            txt += "<div>{}: {}</div>".format(key, self.info[key])
        return txt



app.create_endpoint('/running', 'running', receive_input)

if __name__ == "__main__":
    app.run(debug=True)