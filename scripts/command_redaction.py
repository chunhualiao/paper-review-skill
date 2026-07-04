#!/usr/bin/env python3
"""Shared command-line redaction helpers for audit artifacts."""

from __future__ import annotations

import shlex


SECRET_FLAGS = {"api-key", "apikey", "key", "token", "password", "secret"}
SECRET_NAME_PARTS = ("api-key", "apikey", "token", "password", "secret")


def normalized_flag_name(argument: str) -> str:
    return argument.lstrip("-").replace("_", "-").lower()


def is_secret_flag(argument: str) -> bool:
    flag = normalized_flag_name(argument.split("=", 1)[0])
    return flag in SECRET_FLAGS or any(part in flag for part in SECRET_NAME_PARTS)


def redact_command_args(command: list[str]) -> list[str]:
    redacted: list[str] = []
    skip_next = False
    for arg in command:
        if skip_next:
            redacted.append("<redacted>")
            skip_next = False
            continue
        flag = arg.split("=", 1)[0]
        if is_secret_flag(flag):
            if "=" in arg:
                redacted.append(f"{flag}=<redacted>")
            else:
                redacted.append(arg)
                skip_next = True
            continue
        redacted.append(arg)
    return redacted


def redact_command(command: list[str]) -> str:
    return shlex.join(redact_command_args(command))
