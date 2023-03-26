import websocket
import json
import threading
import time

class Utils:
    def rangeCorrector(ranges):
        if [0, 99] not in ranges:
            ranges.insert(0, [0, 99])
        return ranges

    def getRanges(index, multiplier, memberCount):
        initialNum = int(index*multiplier)
        rangesList = [[initialNum, initialNum+99]]
        if memberCount > initialNum+99:
            rangesList.append([initialNum+100, initialNum+199])
        return Utils.rangeCorrector(rangesList)

    def parseGuildMemberListUpdate(response):
        memberdata = {
            "online_count": response["d"]["online_count"],
            "member_count": response["d"]["member_count"],
            "id": response["d"]["id"],
            "guild_id": response["d"]["guild_id"],
            "hoisted_roles": response["d"]["groups"],
            "types": [],
            "locations": [],
            "updates": []
        }

        for chunk in response['d']['ops']:
            memberdata['types'].append(chunk['op'])
            if chunk['op'] in ('SYNC', 'INVALIDATE'):
                memberdata['locations'].append(chunk['range'])
                if chunk['op'] == 'SYNC':
                    memberdata['updates'].append(chunk['items'])
                else:  # invalidate
                    memberdata['updates'].append([])
            elif chunk['op'] in ('INSERT', 'UPDATE', 'DELETE'):
                memberdata['locations'].append(chunk['index'])
                if chunk['op'] == 'DELETE':
                    memberdata['updates'].append([])
                else:
                    memberdata['updates'].append(chunk['item'])

        return memberdata


class DiscordSocket(websocket.WebSocketApp):
    def __init__(self, token, guild_id, channel_id, rbs):
        self.token = token
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.rbs = rbs

        self.socket_headers = {
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-WebSocket-Extensions": "permessage-deflate; client_max_window_bits",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.2 Safari/605.1.15"
        }

        super().__init__("wss://gateway.discord.gg/?encoding=json&v=9",
                         header=self.socket_headers,
                         on_open=lambda ws: self.sock_open(ws),
                         on_message=lambda ws, msg: self.sock_message(ws, msg),
                         on_close=lambda ws, close_code, close_msg: self.sock_close(
                             ws, close_code, close_msg)
                         )

        self.endScraping = False

        self.guilds = {}
        self.members = {}

        self.ranges = [[0, 0]]
        self.lastRange = 0
        self.packets_recv = 0

    def run(self):
        self.run_forever()
        return self.members

    def scrapeUsers(self):
        if self.endScraping == False:
            self.send('{"op":14,"d":{"guild_id":"' + self.guild_id +
                      '","typing":true,"activities":true,"threads":true,"channels":{"' + self.channel_id + '":' + json.dumps(self.ranges) + '}}}')

    def sock_open(self, ws):
        self.send('{"op":2,"d":{"token":"' + self.token + '","capabilities":125,"properties":{"os":"Windows","browser":"Firefox","device":"","system_locale":"it-IT","browser_user_agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:94.0) Gecko/20100101 Firefox/94.0","browser_version":"94.0","os_version":"10","referrer":"","referring_domain":"","referrer_current":"","referring_domain_current":"","release_channel":"stable","client_build_number":103981,"client_event_source":null},"presence":{"status":"online","since":0,"activities":[],"afk":false},"compress":false,"client_state":{"guild_hashes":{},"highest_last_message_id":"0","read_state_version":0,"user_guild_settings_version":-1,"user_settings_version":-1}}}')

    def heartbeatThread(self, interval):
        try:
            while True:
                #print("sending heartbeat")
                self.send('{"op":1,"d":' + str(self.packets_recv) + '}')
                time.sleep(interval)
        except Exception as e:
            pass  # print(e)
            return  # returns when socket is closed

    def sock_message(self, ws, message):
        decoded = json.loads(message)
        ids_scraped = len(self.members)

        if decoded is None:
            return

        if decoded["op"] != 11:
            self.packets_recv += 1

        if decoded["op"] == 10:
            threading.Thread(target=self.heartbeatThread, args=(
                decoded["d"]["heartbeat_interval"] / 1000, ), daemon=True).start()

        if decoded["t"] == "READY":
            for guild in decoded["d"]["guilds"]:
                self.guilds[guild["id"]] = {
                    "member_count": guild["member_count"]}

        if decoded["t"] == "READY_SUPPLEMENTAL":
            self.ranges = Utils.getRanges(
                0, 100, self.guilds[self.guild_id]["member_count"])
            self.scrapeUsers()

        elif decoded["t"] == "GUILD_MEMBER_LIST_UPDATE":
            parsed = Utils.parseGuildMemberListUpdate(decoded)

            if parsed['guild_id'] == self.guild_id and ('SYNC' in parsed['types'] or 'UPDATE' in parsed['types']):
                for elem, index in enumerate(parsed["types"]):
                    if index == "SYNC":
                        
                        if len(parsed['updates'][elem]) == 0:
                            self.endScraping = True
                            break

                        for item in parsed["updates"][elem]:
                            if "member" in item:
                                BADGES = {
                                    1 << 0:  'Discord Employee',
                                    1 << 1:  'Partnered Server Owner',
                                    1 << 2:  'HypeSquad Events',
                                    1 << 3:  'Bug Hunter Level 1',
                                    1 << 9:  'Early Supporter',
                                    1 << 10: 'Team User',
                                #    1 << 12: 'System',
                                    1 << 14: 'Bug Hunter Level 2',
                                #    1 << 16: 'Verified Bot',
                                    1 << 17: 'Early Verified Bot Developer',
                                    1 << 18: 'Discord Certified Moderator'
                                }

                                badges = []
                                mem = item["member"]
                                obj = {"tag": mem["user"]["username"] + "#" +
                                       mem["user"]["discriminator"], "id": mem["user"]["id"]}

                                flags = mem["user"]["public_flags"]
                                for badge_flag, badge_name in BADGES.items():
                                    if flags & badge_flag == badge_flag:
                                        badges.append(badge_name)

                                if self.rbs:
                                    if len(badges) > 0:
                                        self.members[mem["user"]["id"]] = obj
                                        self.members[mem["user"]["id"]]['badges'] = badges
                                else:
                                    self.members[mem["user"]["id"]] = obj

                    elif index == "UPDATE":
                        for item in parsed["updates"][elem]:
                            if "member" in item:
                                BADGES = {
                                    1 << 0:  'Discord Employee',
                                    1 << 1:  'Partnered Server Owner',
                                    1 << 2:  'HypeSquad Events',
                                    1 << 3:  'Bug Hunter Level 1',
                                    1 << 9:  'Early Supporter',
                                    1 << 10: 'Team User',
                                #    1 << 12: 'System',
                                    1 << 14: 'Bug Hunter Level 2',
                                #    1 << 16: 'Verified Bot',
                                    1 << 17: 'Early Verified Bot Developer',
                                    1 << 18: 'Discord Certified Moderator'
                                }

                                badges = []
                                mem = item["member"]
                                obj = {
                                    "tag": mem["user"]["username"] + "#" + mem["user"]["discriminator"],
                                    "id": mem["user"]["id"]
                                }
                                flags = mem["user"]["public_flags"]
                                for badge_flag, badge_name in BADGES.items():
                                    if flags & badge_flag == badge_flag:
                                        badges.append(badge_name)

                                if self.rbs:
                                    if len(badges) > 0:
                                        self.members[mem["user"]["id"]] = obj
                                        self.members[mem["user"]["id"]]['badges'] = badges
                                else:
                                    self.members[mem["user"]["id"]] = obj

                    self.lastRange += 1
                    self.ranges = Utils.getRanges(
                        self.lastRange, 100, self.guilds[self.guild_id]["member_count"])
                    time.sleep(0.35)
                    self.scrapeUsers()

            if self.endScraping:
                self.close()

    def sock_close(self, ws, close_code, close_msg):
        pass 


def scrape(token: str, guild_id: str, channel_id: str, rbs: bool):
    sb = DiscordSocket(token, guild_id, channel_id, rbs)
    return sb.run()
