from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.properties import (
    ListProperty,
    NumericProperty,
    ReferenceListProperty,
)
from kivy.uix.widget import Widget


class Car(Widget):
    __events__ = ('on_action',)

    angle = NumericProperty()

    velocity_x = NumericProperty()
    velocity_y = NumericProperty()
    velocity = ReferenceListProperty(velocity_x, velocity_y)

    current_actions = ListProperty()

    color = ListProperty((1, 1, 1, 1))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.bind(
            on_key_down=self.on_key_down,
            on_key_up=self.on_key_up,
        )
        self.pressed_keys = {}
        self.action_map = {
            'z': 'up',
            's': 'down',
            'q': 'left',
            'd': 'right',
        }

    def on_key_down(self, _, key, scancode, codepoint, modifier):
        if key not in self.pressed_keys:
            self.pressed_keys[key] = codepoint

            if(
                codepoint in self.action_map
                and self.action_map[codepoint] not in self.current_actions
            ):
                self.current_actions.append(self.action_map[codepoint])
                self.dispatch('on_action', f'+{self.action_map[codepoint]}')

    def on_key_up(self, _, key, scancode):
        if(
            self.pressed_keys[key] in self.action_map
            and self.action_map[self.pressed_keys[key]] in self.current_actions
        ):
            self.current_actions.remove(
                self.action_map[self.pressed_keys[key]]
            )
            self.dispatch(
                'on_action',
                f'-{self.action_map[self.pressed_keys[key]]}'
            )

        del self.pressed_keys[key]

    def on_action(self, action):
        pass


Builder.load_file('widgets/car.kv')
