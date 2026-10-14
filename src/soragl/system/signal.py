import logging
import uuid
from typing import Callable

logger = logging.getLogger(__name__)

# ======================================================================== #
# The Signal handler system
# ======================================================================== #


class SignalHandler:
    def __init__(self):
        self._signals = {}
        self._signal_packet_queue = []

    # ------------------------------------------------------------------------ #
    # logic

    def register_signal(self, signal_name: str, args_template: list[type]):
        self._signals[signal_name] = Signal(signal_name, args_template)
        self._signals[signal_name]._handler = self
        return self._signals[signal_name]

    def register_receiver(self, signal_name: str, function: Callable):
        return self._signals[signal_name].register_receiver(function)

    def emit_signal(self, signal_name: str, *args):
        self._signal_packet_queue.append(SignalPacket(signal_name, args))

    def handle(self):
        for packet in self._signal_packet_queue:
            # check if is valid emitted signal
            if packet._signal_name not in self._signals:
                continue
            # handle packet
            self._signals[packet._signal_name].handle_packet(*packet.args)
        self._signal_packet_queue = []

    # ------------------------------------------------------------------------ #
    # getters

    def get_signal_queue(self):
        return self._signal_queue

    def get_signals(self):
        return self._signals

    def get_signal(self, signal_name: str):
        return self._signals[signal_name]


# ======================================================================== #
# Signal
# ======================================================================== #


class Signal:
    def __init__(self, signal_name: str, args_template: list[type]):
        self._handler = None
        self._receivers = {}

        self._signal_name = signal_name
        self._args_template = args_template

    # ------------------------------------------------------------------------ #
    # logic

    def register_receiver(self, function: Callable):
        receiver = SignalReceiver(function)
        receiver._handler = self
        self._receivers[receiver._id] = receiver
        return receiver

    def emit(self, *args):
        if self._handler is None:
            raise Exception("Signal handler not set")
        self._handler.emit_signal(self._signal_name, *args)

    def handle_packet(self, *args):
        for key, receiver in self._receivers.items():
            logger.debug("%s %s %s", "EMITTING", self._signal_name, receiver._function)
            receiver.emit_signal(*args)


# ======================================================================== #
# Signal Receiver
# ======================================================================== #


class SignalReceiver:
    def __init__(self, function: Callable):
        self._handler = None

        self._function = function
        self._id = uuid.uuid4()

    # ------------------------------------------------------------------------ #
    # logic

    def emit_signal(self, *args):
        # check if args are valid
        for i in range(len(self._handler._args_template)):
            if type(args[i]) is not self._handler._args_template[i]:
                raise Exception("Invalid argument type")
        self._function(*args)


# ======================================================================== #
# Signal Packet
# ======================================================================== #


class SignalPacket:
    def __init__(self, signal_name: str, args: list[any]):
        self._signal_name = signal_name
        self.args = args

    def __repr__(self):
        return f"SignalPacket(signal_name={self._signal_name}, args={self.args})"
