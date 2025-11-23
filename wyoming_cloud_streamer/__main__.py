#!/usr/bin/env python3
import argparse
import asyncio
import json
import logging
from functools import partial
from pathlib import Path
from typing import Any, Dict, Set
import os

from wyoming.info import Attribution, Info, TtsProgram, TtsVoice, TtsVoiceSpeaker
from wyoming.server import AsyncServer

from . import __version__
from .handler import CloudStreamerEventHandler

_LOGGER = logging.getLogger(__name__)

async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default="stdio://", help="unix:// or tcp://")
    parser.add_argument("--debug", action="store_true", help="Log DEBUG messages")
    parser.add_argument(
        "--log-format", default=logging.BASIC_FORMAT, help="Format for log messages"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
        help="Print version and exit",
    )
    
    parser.add_argument(
        "--streaming",
        action="store_true",
        help="Enable audio streaming on sentence boundaries",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO, format=args.log_format
    )
    _LOGGER.debug(args)


    # Load builtin voices first. For Home Assistant add-on layout the
    # file is available at `/app/wyoming_cloud_streamer/voices.json`.
    voices_file = "/app/wyoming_cloud_streamer/voices.json"
    try:
        with open(voices_file, "r", encoding="utf-8") as f:
            voices_data = json.load(f)
    except FileNotFoundError:
        _LOGGER.exception("Builtin voices.json not found at %s", voices_file)
        raise

    # Optionally merge a user-provided custom voices JSON file. The path
    # can be provided via the `CUSTOM_VOICES_PATH` environment variable.
    # The file should be a JSON object with the same shape as `voices.json`.
    custom_path = os.getenv("CUSTOM_VOICES_PATH", "")
    if custom_path:
        try:
            custom_file = Path(custom_path)
            if custom_file.exists():
                with open(custom_file, "r", encoding="utf-8") as cf:
                    custom_data = json.load(cf)
                # Merge provider keys; for lists we keep unique entries while
                # preserving order (existing first, then custom additions).
                for provider, pdata in custom_data.items():
                    if provider not in voices_data:
                        voices_data[provider] = pdata
                        continue
                    # Merge 'voices' list
                    base_voices = voices_data[provider].get("voices", [])
                    for v in pdata.get("voices", []):
                        if v not in base_voices:
                            base_voices.append(v)
                    voices_data[provider]["voices"] = base_voices
                    # Merge 'languages' list
                    base_langs = voices_data[provider].get("languages", [])
                    for l in pdata.get("languages", []):
                        if l not in base_langs:
                            base_langs.append(l)
                    voices_data[provider]["languages"] = base_langs
            else:
                _LOGGER.warning("CUSTOM_VOICES_PATH set but file does not exist: %s", custom_path)
        except Exception as exc:
            _LOGGER.exception("Failed to load custom voices from %s: %s", custom_path, exc)

    voices = []
    for key in voices_data.keys():
        for voice in voices_data[key]["voices"]:
            for language in voices_data[key]["languages"]:
                voice_name = ""
                voice_description = ""
                if key == "google":
                    voice_name = language.replace('_', '-', 1)+"-Chirp3-HD-"+voice
                    voice_description = "google_"+voice
                    attribution=Attribution(
                            name="Google", url="https://cloud.google.com/text-to-speech/docs/chirp3-hd"
                        )
                elif key == "openai":
                    voice_name = language.replace('_', '-', 1)+"-openai-"+voice
                    voice_description = "openai_"+voice
                    attribution=Attribution(
                            name="OpenAI", url="https://platform.openai.com/docs/guides/text-to-speech"
                        )
                else:
                    voice_name = language.replace('_', '-', 1)+"-"+key+"-"+voice
                    voice_description = key+"_"+voice
                    attribution=Attribution(
                            name=key.capitalize(), url=""
                        )
                voices.append(
                    TtsVoice(
                        name=voice_name,
                        description=voice_description,
                        attribution=attribution,
                        installed=True,
                        version=None,
                        languages=[language],
                        speakers=None,
                    )
                )

    wyoming_info = Info(
        tts=[
            TtsProgram(
                name="Cloud TTS Streamer",
                description="Wyoming streaming proxy for cloud TTS providers",
                attribution=Attribution(
                    name="eslavnov", url="https://github.com/eslavnov/wyoming-cloud-streamer"
                ),
                installed=True,
                voices=sorted(voices, key=lambda v: v.name),
                version=__version__,
                supports_synthesize_streaming=True,
            )
        ],
    )

    # Start server 
    server = AsyncServer.from_uri(args.uri)

    _LOGGER.info("Ready")
    await server.run(
        partial(
            CloudStreamerEventHandler,
            wyoming_info,
            args,
            voices,
        )
    )

def run():
    asyncio.run(main())

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        pass
