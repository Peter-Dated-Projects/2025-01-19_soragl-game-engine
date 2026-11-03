"""Multiplayer demo: every player steers a square with the arrow keys.

    # a player hosts on their machine (others connect to its IP; forward the port for
    # internet play)
    uv run python examples/net_demo/main.py host --via p2p --model lockstep
    uv run python examples/net_demo/main.py join --via p2p --address 192.168.1.20:7777 --model lockstep

    # Steam carries the traffic (uv sync --extra steam; Steam running and signed in)
    uv run python examples/net_demo/main.py host --via steam --model authority
    uv run python examples/net_demo/main.py join --via steam --address <lobby id> --model authority

    # a dedicated server: a host with no player of its own, no window
    uv run python examples/net_demo/main.py host --via p2p --model authority --headless

`--bot` moves at random instead of reading keys; `--seconds N` quits after N seconds.
"""

import argparse
import json
import random
import sys
import time

import soragl.net as net

GAME = {"game_id": "soragl-net-demo", "version": "1"}
SIZE = 600
COLOURS = [
    (240, 200, 60),
    (90, 170, 250),
    (240, 90, 90),
    (120, 220, 120),
    (200, 120, 240),
]


class Squares:
    """Integer positions, so lockstep stays deterministic; `shown` is what is drawn
    (authority clients interpolate it between snapshots)."""

    def __init__(self, bot: bool, headless: bool):
        self.bot = bot
        self.headless = headless
        self.pos: dict[str, list[int]] = {}
        self.shown: dict[str, list[float]] = {}
        self.keys = 0
        self.rng = random.Random()

    def net_input(self) -> bytes:
        if self.headless and not self.bot:
            return b""  # a dedicated server has no player of its own
        if self.bot:
            if self.rng.random() < 0.1:
                self.keys = self.rng.choice([1, 2, 4, 8, 0])
        return bytes([self.keys])

    def net_step(self, dt, inputs):
        for pid in sorted(inputs):
            if not inputs[pid]:
                continue
            k = inputs[pid][0]
            x, y = self.pos.setdefault(str(pid), [SIZE // 2, SIZE // 2])
            x += 4 * ((k & 2) > 0) - 4 * ((k & 1) > 0)
            y += 4 * ((k & 8) > 0) - 4 * ((k & 4) > 0)
            self.pos[str(pid)] = [min(SIZE - 20, max(0, x)), min(SIZE - 20, max(0, y))]
        self.shown = {k: [float(v[0]), float(v[1])] for k, v in self.pos.items()}

    def net_snapshot(self) -> bytes:
        return json.dumps(self.pos, sort_keys=True).encode()

    def net_restore(self, data: bytes) -> None:
        self.pos = {k: [int(v[0]), int(v[1])] for k, v in json.loads(data).items()}
        self.shown = {k: [float(v[0]), float(v[1])] for k, v in self.pos.items()}

    def net_interpolate(self, older: bytes, newer: bytes, t: float) -> None:
        a, b = json.loads(older), json.loads(newer)
        self.net_restore(newer)
        self.shown = {
            k: [a[k][0] + (b[k][0] - a[k][0]) * t, a[k][1] + (b[k][1] - a[k][1]) * t]
            if k in a
            else [float(b[k][0]), float(b[k][1])]
            for k in b
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("role", choices=["host", "join"])
    ap.add_argument("--via", required=True, choices=["p2p", "steam"])
    ap.add_argument("--model", required=True, choices=["lockstep", "authority"])
    ap.add_argument("--address", help="join: ip:port (p2p) or lobby id (steam)")
    ap.add_argument("--port", type=int, default=net.DEFAULT_PORT)
    ap.add_argument("--name", default="")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--bot", action="store_true")
    ap.add_argument("--seconds", type=float)
    args = ap.parse_args()

    game = Squares(bot=args.bot, headless=args.headless)
    try:
        if args.role == "host":
            session = net.host(
                game,
                via=args.via,
                model=args.model,
                port=args.port,
                name=args.name or "Host",
                **GAME,
            )
            t = session.session.transport
            where = f"lobby {t.lobby_id}" if args.via == "steam" else f"port {t.port}"
            print(f"hosting on {where}", flush=True)
        else:
            if not args.address:
                ap.error("join needs --address")
            session = net.join(
                game,
                via=args.via,
                model=args.model,
                address=args.address,
                name=args.name,
                **GAME,
            )
    except RuntimeError as e:  # Steam not running, lobby missing...
        print(f"could not start: {e}", file=sys.stderr)
        return 1

    def report(ev):
        print(f"[{ev.kind}] player {ev.player} {ev.reason}".rstrip(), flush=True)

    if args.headless:
        net.run_headless(session, seconds=args.seconds, on_event=report)
        print(
            f"ran {getattr(session, 'tick', 0)} ticks; players {sorted(session.players)}"
        )
        session.close()
        return 0

    import pygame

    pygame.init()
    screen = pygame.display.set_mode((SIZE, SIZE))
    font = pygame.font.Font(None, 22)
    clock = pygame.time.Clock()
    start = last = time.monotonic()
    running = True
    while running and not session.session.closed:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
        held = pygame.key.get_pressed()
        game.keys = (
            held[pygame.K_LEFT]
            | held[pygame.K_RIGHT] << 1
            | held[pygame.K_UP] << 2
            | held[pygame.K_DOWN] << 3
        )
        now = time.monotonic()
        for ev in session.update(now - last):
            report(ev)
        last = now
        screen.fill((24, 26, 32))
        for pid, (x, y) in game.shown.items():
            colour = COLOURS[int(pid) % len(COLOURS)]
            pygame.draw.rect(screen, colour, (x, y, 20, 20))
            if int(pid) == session.player:
                pygame.draw.rect(screen, (255, 255, 255), (x - 2, y - 2, 24, 24), 2)
        names = ", ".join(p.get("name", "?") for p in session.players.values())
        status = "waiting for players" if getattr(session, "waiting", False) else ""
        hud = f"{args.via} / {args.model}  you: {session.player}  players: {names}  {status}"
        screen.blit(font.render(hud, True, (220, 220, 220)), (8, 8))
        pygame.display.flip()
        clock.tick(60)
        if args.seconds is not None and now - start >= args.seconds:
            break
    session.close()
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
