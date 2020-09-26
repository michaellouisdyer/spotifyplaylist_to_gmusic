from ytmusicapi import YTMusic
from datetime import datetime
import os
import re
import argparse
import difflib
from SpotifyExport import Spotify
from tqdm import tqdm
from tqdm.contrib.concurrent import process_map, thread_map
import settings

path = os.path.dirname(os.path.realpath(__file__)) + os.sep


class YTMusicTransfer:
    def __init__(self):
        self.api = YTMusic('headers_auth.json')

    def create_playlist(self, name, info, privacy="PRIVATE"):
        return self.api.create_playlist(name, info, privacy)

    def get_best_fit_song_id(self, results, song):
        match_score = {}
        title_score = {}
        for res in results:
            if res['resultType'] not in ['song', 'video']:
                continue

            durationItems = res['duration'].split(':')
            duration = int(durationItems[0]) * 60 + int(durationItems[1])
            durationMatch = 1 - abs(duration - song['duration']) * 2 / song['duration']

            title = res['title']
            # for videos,
            if res['resultType'] == 'video':
                titleSplit = title.split('-')
                if len(titleSplit) == 2:
                    title = titleSplit[1]

            title_score[res['videoId']] = difflib.SequenceMatcher(a=title.lower(), b=song['name'].lower()).ratio()

            # import pdb; pdb.set_trace()
            if not res.get("artist"):
                res["artist"] = list(res["artists"][0].values())[0]
            # except:
            #     import pdb; pdb.set_trace()
            scores = [durationMatch * 5, title_score[res['videoId']],
                      difflib.SequenceMatcher(a=res['artist'].lower(), b=song['artist'].lower()).ratio()]

            #add album for songs only
            if res['resultType'] == 'song' and 'album' in res:
                scores.append(difflib.SequenceMatcher(a=res['album']["name"].lower(), b=song['album'].lower()).ratio())

            match_score[res['videoId']] = sum(scores) / (len(scores) + 1) * max(1, int(res['resultType'] == 'song') * 1.5)

        if len(match_score) == 0:
            return None

        #don't return songs with titles <45% match
        max_score = max(match_score, key=match_score.get)
        return max_score
    def search_song(self, song):
        query = song['artist'] + ' ' + song['name']
        query = query.replace(" &", "")
        result = self.api.search(query)
        if len(result) == 0:
            print("could not find " + query)
            return None
        else:
            targetSong = self.get_best_fit_song_id(result, song)
            return targetSong

    def search_songs(self, tracks):
        video_ids = thread_map(self.search_song, list(tracks))
        video_ids = [x for x in video_ids if video_ids is not None]

        # videoIds = []
        # songs = list(tracks)
        # notFound = list()
        # for i, song in tqdm(enumerate(songs), total =len(songs)):
        #     query = song['artist'] + ' ' + song['name']
        #     query = query.replace(" &", "")
        #     result = self.api.search(query)
        #     if len(result) == 0:
        #         notFound.append(query)
        #     else:
        #         targetSong = self.get_best_fit_song_id(result, song)
        #         if targetSong is None:
        #             notFound.append(query)
        #         else:
        #             videoIds.append(targetSong)

            # if i > 0 and i % 10 == 0:
            #     print(str(i) + ' searched')

        # with open(path + 'noresults_youtube.txt', 'w', encoding="utf-8") as f:
        #     f.write("\n".join(notFound))
        #     f.close()
        #
        return video_ids

    def add_playlist_items(self, playlistId, videoIds):
        self.api.add_playlist_items(playlistId, videoIds)

    def get_playlist_id(self, name):
        pl = self.api.get_library_playlists()
        try:
            playlist = next(x for x in pl if x['title'].find(name) != -1)['playlistId']
            return playlist
        except:
            raise Exception("Playlist title not found in playlists")

    def remove_songs(self, playlistId):
        items = self.api.get_playlist(playlistId)
        if len(items) > 0:
            self.api.remove_playlist_items(playlistId, items["tracks"])

    def remove_playlists(self, pattern):
        playlists = self.api.get_playlists()
        p = re.compile("{0}".format(pattern))
        matches = [pl for pl in playlists if p.match(pl['title'])]
        print("The following playlists will be removed:")
        print("\n".join([pl['title'] for pl in matches]))
        print("Please confirm (y/n):")

        choice = input().lower()
        if choice[:1] == 'y':
            [self.api.delete_playlist(pl['playlistId']) for pl in matches]
            print(str(len(matches)) + " playlists deleted.")
        else:
            print("Aborted. No playlists were deleted.")


def get_args():
    parser = argparse.ArgumentParser(description='Transfer spotify playlist to YouTube Music.')
    parser.add_argument("playlist", type=str, help="Provide a playlist Spotify link. Alternatively, provide a text file (one song per line)")
    parser.add_argument("-u", "--update", type=str, help="Delete all entries in the provided Google Play Music playlist and update the playlist with entries from the Spotify playlist.")
    parser.add_argument("-n", "--name", type=str, help="Provide a name for the YouTube Music playlist. Default: Spotify playlist name")
    parser.add_argument("-i", "--info", type=str, help="Provide description information for the YouTube Music Playlist. Default: Spotify playlist description")
    parser.add_argument("-d", "--date", action='store_true', help="Append the current date to the playlist name")
    parser.add_argument("-p", "--public", action='store_true', help="Make the playlist public. Default: private")
    parser.add_argument("-r", "--remove", action='store_true', help="Remove playlists with specified regex pattern.")
    #parser.add_argument("-a", "--all", action='store_true', help="Transfer all public playlists of the specified user (Spotify User ID).")
    return parser.parse_args()


def update_one(spotify_link, gpm_playlist_name):
    ytmusic = YTMusicTransfer()
    try:
        playlist = Spotify().getSpotifyPlaylist(spotify_link)
    except Exception as ex:
        print("Could not get Spotify playlist. Please check the playlist link.\n Error: " + repr(ex))
        return

    try:
        playlistId = ytmusic.get_playlist_id(gpm_playlist_name)
        ytmusic.remove_songs(playlistId)
    except Exception as e:
        print(e)
        print(f"No playlist {gpm_playlist_name} found. Adding...")
        playlistId = ytmusic.create_playlist(gpm_playlist_name, playlist["description"], 'PRIVATE')
    videoIds = ytmusic.search_songs(playlist['tracks'])
    ytmusic.add_playlist_items(playlistId, videoIds)

def multiple():
    playlists = {
    "https://open.spotify.com/playlist/37i9dQZF1DX4dyzvuaRJ0n" : "mint",
    "https://open.spotify.com/playlist/37i9dQZF1DX2L0iB23Enbq" : "TikTok Hits",
    "https://open.spotify.com/playlist/37i9dQZF1DWSJHnPb1f0X3": "Cardio (Spotify)",
    "https://open.spotify.com/playlist/37i9dQZF1DX4JAvHpjipBk": "New Music Friday (Spotify)",
    "https://open.spotify.com/playlist/37i9dQZF1DX8AliSIsGeKd" : "Electronic Rising",
    "https://open.spotify.com/playlist/37i9dQZF1DWYs83FtTMQFw" : "Hot Rhythmic",
    "https://open.spotify.com/playlist/37i9dQZF1DX4WYpdgoIcn6" : "Chill Hits",
    "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M" : "Today's Top Hits (Spotify)"
     }
    for spotify_link, gpm_playlist_name in tqdm(playlists.items()):
        tqdm.write("Playlist: " + gpm_playlist_name)
        update_one(spotify_link, gpm_playlist_name)

        tqdm.write("Finished " + gpm_playlist_name)

def main():
    multiple()

def one():
    args = get_args()
    ytmusic = YTMusicTransfer()

    if args.remove:
        ytmusic.remove_playlists(args.playlist)
        return

    date = ""
    if args.date:
        date = " " + datetime.today().strftime('%m/%d/%Y')
    try:
        playlist = Spotify().getSpotifyPlaylist(args.playlist)
    except Exception as ex:
        print("Could not get Spotify playlist. Please check the playlist link.\n Error: " + repr(ex))
        return

    name = args.name + date if args.name else playlist['name'] + date
    info = playlist['description'] if (args.info is None) else args.info

    if args.update:
        playlistId = ytmusic.get_playlist_id(args.update)
        videoIds = ytmusic.search_songs(playlist['tracks'])
        ytmusic.remove_songs(playlistId)
        ytmusic.add_playlist_items(playlistId, videoIds)

    else:
        videoIds = ytmusic.search_songs(playlist['tracks'])
        playlistId = ytmusic.create_playlist(name, info, 'PUBLIC' if args.public else 'PRIVATE')
        ytmusic.add_playlist_items(playlistId, videoIds)

        print("Success: created playlist \"" + name + "\"")


if __name__ == "__main__":
    main()
