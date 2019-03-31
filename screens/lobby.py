import queue
import socket
import threading
import time

from kivy.clock import Clock
from kivy.factory import Factory
from kivy.lang import Builder
from kivy.uix.screenmanager import Screen
import netifaces


class LobbyScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.refresher = refresher = Refresher()
        self.server_queue = refresher.server_queue
        Clock.schedule_interval(self.update_refresher, 0)

    def update_refresher(self, *args):
        while True:
            try:
                servers = self.server_queue.get_nowait()
            except queue.Empty:
                break

            self.game_list.clear_widgets()

            for address, name in servers:
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

        broadcast_addresses = [
            address['broadcast']
            for interface in netifaces.interfaces()
            for addresses in netifaces.ifaddresses(interface).values()
            for address in addresses
            if 'broadcast' in address and 'netmask' in address
        ]

        while True:
            if not self.scan_enabled:
                time.sleep(1)
                continue

            for address in broadcast_addresses:
                client.sendto(b'REFRESH', (address, 54321))

            servers = []

            while True:
                try:
                    name, address = client.recvfrom(1024)
                except socket.timeout:
                    break

                servers.append((address, name.decode()))
                self.server_queue.put(servers)


Builder.load_file('screens/lobby.kv')
