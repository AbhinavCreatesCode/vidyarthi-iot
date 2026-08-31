"""Simple end-to-end simulator for the new teacher -> mode -> student flow."""
import asyncio
import json
import os

import websockets


URI = os.getenv("TERMINAL_WS", "ws://localhost:8000/ws/terminal/gate-1")
TEACHER_UID = os.getenv("TEACHER_UID", "TEACHER_UID_HERE")
STUDENT_UID = os.getenv("STUDENT_UID", "STUDENT_UID_HERE")


async def send(ws, msg):
    await ws.send(json.dumps(msg))
    print("->", msg)


async def main():
    async with websockets.connect(URI) as ws:
        await send(ws, {"type": "heartbeat", "data": {"rssi": -54, "queue": 0}})

        # Teacher scans card and receives role classification.
        await send(ws, {"type": "card_scan", "data": {"uid": TEACHER_UID}})
        print("<-", await ws.recv())

        # Teacher chooses feedback mode using physical button 1.
        await send(ws, {
            "type": "start_mode",
            "data": {"mode": "feedback", "teacher_roll": os.getenv("TEACHER_ROLL", "T01")}
        })
        print("<-", await ws.recv())

        # Student scans, then rates session 4/4.
        await send(ws, {"type": "card_scan", "data": {"uid": STUDENT_UID}})
        print("<-", await ws.recv())
        await send(ws, {"type": "feedback", "data": {"uid": STUDENT_UID, "rating": 4}})
        print("<-", await ws.recv())

        # Teacher can rescan and switch to ration mode.
        await send(ws, {"type": "card_scan", "data": {"uid": TEACHER_UID}})
        print("<-", await ws.recv())
        await send(ws, {
            "type": "start_mode",
            "data": {"mode": "ration", "teacher_roll": os.getenv("TEACHER_ROLL", "T01")}
        })
        print("<-", await ws.recv())

        await send(ws, {"type": "card_scan", "data": {"uid": STUDENT_UID}})
        print("<-", await ws.recv())
        await send(ws, {"type": "ration_claim", "data": {"uid": STUDENT_UID}})
        print("<-", await ws.recv())


if __name__ == "__main__":
    asyncio.run(main())
