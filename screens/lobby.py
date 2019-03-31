import queue
import socket
import threading
import time

from kivy.clock import Clock
from kivy.factory import Factory
from kivy.lang import Builder
from kivy.uix.screenmanager import Screen


class LobbyScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.refresher = refresher = Refresher()
        self.server_queue = refresher.server_queue
        Clock.schedule_interval(self.update_refresher, 0)

    def update_refresher(self, *args):
        while True:
            try:
                address, name = self.server_queue.get_nowait()
            except queue.Empty:
                break

            if address is None:
                self.game_list.clear_widgets()
                continue

            game = Factory.Game()
            game.name = name
            game.address = address
            game.lobby = self
            self.game_list.add_widget(game)

    def on_pre_enter(self):
        self.start_scanning()

    def on_pre_leave(self):
        self.stop_scanning()

    def start_scanning(self):
        self.refresher.scan_enabled = True

    def stop_scanning(self):
        self.refresher.scan_enabled = False

    def do_create_race(self, name):
        if not name:
            return

        self.manager.current = 'game'
        self.manager.current_screen.do_host_game(name)

    def do_join_race(self, address):
        self.manager.current = 'game'
        self.manager.current_screen.do_join_game(address)


class Refresher(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.scan_enabled = False
        self.server_queue = queue.Queue()
        self.start()

    def run(self):
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        client.settimeout(1)

        while True:
            if not self.scan_enabled:
                time.sleep(1)
                continue

            client.sendto(b'REFRESH', ('255.255.255.255', 54321))
            while True:
                try:
                    data, server = client.recvfrom(1024)
                except socket.timeout:
                    self.server_queue.put((None, None))
                    break
                else:
                    self.server_queue.put((server, data.decode()))


Builder.load_file('screens/lobby.kv')
