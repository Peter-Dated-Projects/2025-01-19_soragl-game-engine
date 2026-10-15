import pytest

from soragl.system import signal


def test_receiver_gets_emitted_args_when_signal_is_handled():
    handler = signal.SignalHandler()
    handler.register_signal("hit", [int, str])
    received = []
    handler.register_receiver("hit", lambda amount, who: received.append((amount, who)))

    handler.emit_signal("hit", 3, "archer")
    assert received == []  # delivery waits for handle()
    handler.handle()

    assert received == [(3, "archer")]


def test_emitting_an_unregistered_signal_is_ignored():
    handler = signal.SignalHandler()

    handler.emit_signal("nobody-listens", 1)
    handler.handle()


def test_emitting_the_wrong_argument_type_raises():
    handler = signal.SignalHandler()
    handler.register_signal("hit", [int])
    handler.register_receiver("hit", lambda amount: None)

    handler.emit_signal("hit", "three")

    with pytest.raises(Exception, match="Invalid argument type"):
        handler.handle()


def test_subclass_instances_satisfy_the_argument_template():
    class Base:
        pass

    class Child(Base):
        pass

    handler = signal.SignalHandler()
    handler.register_signal("spawned", [Base])
    received = []
    handler.register_receiver("spawned", received.append)

    handler.emit_signal("spawned", Child())
    handler.handle()

    assert len(received) == 1


def test_wrong_argument_types_raise_a_type_error():
    handler = signal.SignalHandler()
    handler.register_signal("damaged", [int])
    handler.register_receiver("damaged", lambda amount: None)

    handler.emit_signal("damaged", "a lot")

    with pytest.raises(TypeError, match="damaged"):
        handler.handle()


def test_queued_packets_are_visible_until_handled():
    handler = signal.SignalHandler()
    handler.register_signal("ping", [])

    handler.emit_signal("ping")

    assert len(handler.get_signal_queue()) == 1
    handler.handle()
    assert handler.get_signal_queue() == []
