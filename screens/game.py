import ast
import queue
import socket
import threading
import time

from kivy.clock import Clock, mainthread
from kivy.lang import Builder
from kivy.logger import Logger
from kivy.properties import ObjectProperty
from kivy.uix.screenmanager import Screen
from kivy.vector import Vector

from widgets.car import Car


class GameScreen(Screen):
    car = ObjectProperty(rebind=True)
    game_area = ObjectProperty()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cars = {}

    def add_player(self, user_id):
        self.cars[user_id] = car = Car()

        if user_id == self.user_id:
            self.car = car
            car.bind(on_action=self.on_action)
        else:
            car.color = (1, .5, .5, 1)

        self.game_area.add_widget(car)

    def on_action(self, car, action):
        self.client.input_data.put(f'ACTION {action}'.encode())

    def do_host_game(self, name):
        self.server = GameServer(name)
        self.do_join_game(('127.0.0.1', 54321))

    def do_join_game(self, address):
        self.client = GameClient(address)
        self.client.connect()
        self.client_timer = Clock.schedule_interval(self.update_client, 0)

    def update_client(self, *args):
        while True:
            try:
                command, *arguments = self.client.output_data.get_nowait()
            except queue.Empty:
                break
            else:
                if command == 'ID':
                    self.user_id, = arguments
                    self.add_player(self.user_id)

                elif command == 'UPDATE':
                    user_id, attribute, value = arguments

                    if user_id not in self.cars:
                        self.add_player(user_id)

                    setattr(self.cars[user_id], attribute, value)


class GameServer(threading.Thread):
    def __init__(self, name):
        super().__init__(daemon=True)

        self.name = name

        self.socket = server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(('', 54321))
        server.settimeout(0)

        self.tickrate = 1 / 60
        self.next_tick_time = time.time()

        self.users = []

        self.start()

    def run(self):
        while True:
            if time.time() >= self.next_tick_time:
                self.update()
                self.next_tick_time += self.tickrate

            try:
                data, client = self.socket.recvfrom(1024)
            except BlockingIOError:
                time.sleep(self.tickrate / 2)
                continue

            command, _, arguments = data.decode().partition(' ')
            getattr(
                self,
                f'handle_{command.lower()}',
                lambda arguments: self.handle_invalid(client, command, arguments)
            )(client, arguments)

    def update(self):
        dt = self.tickrate
        max_acceleration = 750
        steering = .75
        friction = .98

        for user in self.users:
            old_user = user.copy()

            velocity_vector = Vector(user['velocity'])
            acceleration = None
            rotation = None
            going_backwards = velocity_vector.rotate(-user['angle']).y < 0

            if 'up' in user['current_actions']:
                acceleration = Vector(0, max_acceleration * dt)

            if 'down' in user['current_actions']:
                acceleration = Vector(0, -max_acceleration * dt * (
                    .5 if going_backwards else 1
                ))

            if 'left' in user['current_actions']:
                rotation = steering * velocity_vector.length() * dt * (
                    -1 if going_backwards else 1
                )

            if 'right' in user['current_actions']:
                rotation = -steering * velocity_vector.length() * dt * (
                    -1 if going_backwards else 1
                )

            if rotation:
                user['angle'] += rotation
                velocity_vector = velocity_vector.rotate(rotation)

            velocity_angle = velocity_vector.angle((0, 0))

            if acceleration:
                acceleration = acceleration.rotate(user['angle'])
                velocity_vector += acceleration

            user['velocity'] = velocity_vector * friction

            user['center'] = [
                cxy + vxy * dt
                for cxy, vxy in zip(user['center'], user['velocity'])
            ]

            for attribute in ('angle', 'center', 'velocity'):
                if old_user[attribute] != user[attribute]:
                    for recipient in self.users:
                        self.send_update(
                            recipient['id'],
                            user['id'],
                            attribute
                        )

    def handle_refresh(self, client, arguments):
        self.socket.sendto(self.name.encode(), client)

    def handle_connect(self, client, arguments):
        used_ids = {user['id'] for user in self.users}

        user_id = 1
        while user_id in used_ids:
            user_id += 1

        self.socket.sendto(f'ID {user_id}'.encode(), client)
        new_client = {
            'id': user_id,
            'angle': 0,
            'center': (400, 300),
            'velocity': (0, 0),
            'current_actions': [],
            'address': client,
        }
        self.users.append(new_client)
        self.send_update(user_id, user_id, 'center')

        for user in self.users:
            for attribute in ('angle', 'center'):
                self.send_update(user_id, user['id'], attribute)

    def handle_action(self, client, arguments):
        user = self.user_from_address(client)

        if not user:
            return

        sign, action = arguments[0], arguments[1:]
        current_actions = user['current_actions']

        if(
            (sign not in ('+', '-'))
            or (sign == '+' and action in current_actions)
            or (sign == '-' and action not in current_actions)
        ):
            return

        (
            current_actions.append if sign == '+' else current_actions.remove
        )(action)

    def handle_invalid(self, client, command, arguments):
        Logger.warning(
            f'{type(self).__name__}: '
            f'Received invalid command: {command}, '
            f'with arguments: {arguments}, '
            f'from client: {client}'
        )

    def send_update(self, recipient, sender, attribute):
        target_address = self.user_from_id(recipient)['address']
        user = self.user_from_id(sender)

        self.socket.sendto(
            f'UPDATE {sender} {attribute} {user[attribute]}'.encode(),
            target_address
        )

    def user_from_id(self, user_id):
        for user in self.users:
            if user['id'] == user_id:
                return user

    def user_from_address(self, address):
        for user in self.users:
            if user['address'] == address:
                return user


class GameClient(threading.Thread):
    def __init__(self, address):
        super().__init__(daemon=True)

        self.address = address

        self.socket = client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.connect(tuple(address))
        client.settimeout(0)

        self.input_data, self.output_data = queue.Queue(), queue.Queue()

        self.tickrate = 1 / 60
        self.next_tick_time = time.time()

        self.client_id = 0

        self.start()

    def run(self):
        client = self.socket
        input_data = self.input_data
        output_data = self.output_data

        while True:
            while True:
                try:
                    data = input_data.get_nowait()
                except queue.Empty:
                    break
                else:
                    client.send(data)

            try:
                data = client.recv(1024)
            except BlockingIOError:
                time.sleep(self.tickrate / 2)
                continue

            command, _, arguments = data.decode().partition(' ')
            getattr(
                self,
                f'handle_{command.lower()}',
                lambda arguments: self.handle_invalid(command, arguments)
            )(arguments)

    def connect(self):
        self.input_data.put(b'CONNECT')

    def handle_id(self, arguments):
        self.client_id = user_id = int(arguments)
        self.output_data.put(('ID', user_id))

    def handle_update(self, arguments):
        if not self.client_id:
            return

        user_id, attribute, value = arguments.split(' ', 2)
        user_id = int(user_id)
        value = ast.literal_eval(value)

        self.output_data.put(('UPDATE', user_id, attribute, value))

    def handle_invalid(self, command, arguments):
        Logger.warning(
            f'{type(self).__name__}: '
            f'Received invalid command: {command}, '
            f'with arguments: {arguments}'
        )


Builder.load_file('screens/game.kv')
