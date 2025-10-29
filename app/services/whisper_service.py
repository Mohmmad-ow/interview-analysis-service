from fastapi import UploadFile
import whisper
import tempfile
import os
import asyncio
from functools import partial
from typing import Dict, Optional, Tuple
import aiohttp
import aiofiles
from app.core.logging import log_info, log_error
from app.config import settings
from app.models.analysis.response import AnalysisResult


class WhisperService:
    """
    Local Whisper service for speech-to-text transcription
    """

    def __init__(self):
        self.model = None
        self.model_loaded = False

    async def load_model(self, model_size: str = "base"):
        """
        Load Whisper model asynchronously
        """
        if self.model:
            return
        try:
            loop = asyncio.get_event_loop()
            self.model = await loop.run_in_executor(
                None, whisper.load_model, model_size
            )
            self.model_loaded = True
            log_info("Whisper model loaded", model_size=model_size)

        except Exception as e:
            log_error(
                "Failed to load Whisper model", error=str(e), model_size=model_size
            )
            raise

    async def transcribe_audio_url(
        self, audio_url: str, language: str = "en"
    ) -> Tuple[str, float]:
        """
        Transcribe audio from URL
        Returns: (transcript, processing_time)
        """
        if not self.model_loaded:
            await self.load_model(settings.WHISPER_MODEL_SIZE)

        start_time = asyncio.get_event_loop().time()

        try:
            # Download audio file
            # audio_path = await self._download_audio(audio_url)

            # Transcribe with CORRECT parameters
            result = await self._transcribe_file(audio_url, language)

            processing_time = asyncio.get_event_loop().time() - start_time

            log_info(
                "Audio transcribed successfully",
                audio_url=audio_url,
                language=language,
                processing_time=processing_time,
                audio_duration=result.get("duration", 0),
                word_count=len(result["text"].split()),
            )

            # Clean up temporary file
            # await self._cleanup_file(au)

            return result["text"].strip(), processing_time

        except Exception as e:
            processing_time = asyncio.get_event_loop().time() - start_time
            log_error(
                "Audio transcription failed",
                audio_url=audio_url,
                language=language,
                processing_time=processing_time,
                error=str(e),
            )
            raise

    async def transcribe_audio_file(
        self,
        audio_file: UploadFile,
        language: str = "en",
    ) -> Tuple[str, float]:
        """
        Transcribe audio from URL
        Returns: (transcript, processing_time)
        """
        if not self.model_loaded:
            await self.load_model(settings.WHISPER_MODEL_SIZE)

        start_time = asyncio.get_event_loop().time()

        try:
            # Download audio file
            # audio_path = await self._download_audio(audio_url)

            # Transcribe with CORRECT parameters
            result = await self._transcribe_file(audio_file, language)

            processing_time = asyncio.get_event_loop().time() - start_time

            log_info(
                "Audio transcribed successfully",
                audio_url="Just a file",
                language=language,
                processing_time=processing_time,
                audio_duration=result.get("duration", 0),
                word_count=len(result["text"].split()),
            )

            # Clean up temporary file
            # await self._cleanup_file(au)

            return result["text"].strip(), processing_time

        except Exception as e:
            processing_time = asyncio.get_event_loop().time() - start_time
            log_error(
                "Audio transcription failed",
                audio_url="Just a file",
                language=language,
                processing_time=processing_time,
                error=str(e),
            )
            raise

    async def _transcribe_file(
        self, file_path: str | UploadFile, language: str
    ) -> dict:
        """Transcribe audio file using Whisper with correct parameters"""
        try:
            loop = asyncio.get_event_loop()

            # CORRECT transcription parameters
            result = await loop.run_in_executor(
                None,
                self._use_transcribe,
                file_path,  # Audio file path
            )
            if not result:
                raise

            return result

        except Exception as e:
            log_error("Transcription failed", file_path=file_path, error=str(e))
            raise

    async def _download_audio(self, audio_url: str) -> str:
        """Download audio file to temporary location"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(audio_url) as response:
                    if response.status != 200:
                        raise Exception(
                            f"Failed to download audio: HTTP {response.status}"
                        )

                    # Create temporary file
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                    temp_path = temp_file.name
                    temp_file.close()

                    # Write audio data
                    async with aiofiles.open(temp_path, "wb") as f:
                        await f.write(await response.read())

                    return temp_path

        except Exception as e:
            log_error("Audio download failed", audio_url=audio_url, error=str(e))
            raise

    async def _cleanup_file(self, file_path: str):
        """Clean up temporary audio file"""
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
        except Exception as e:
            log_error("File cleanup failed", file_path=file_path, error=str(e))

    def _use_transcribe(self, audio_file):
        if self.model:
            return self.model.transcribe(
                audio=audio_file,
                # verbose=None,  # Whether to print progress
                # temperature=0,  # Sampling temperature
                # compression_ratio_threshold=2.4,  # Gzip compression ratio threshold
                # logprob_threshold=-1.0,  # Log probability threshold
                # no_speech_threshold=0.6,  # No speech threshold
                # condition_on_previous_text=True,  # Use previous text as prompt
                # initial_prompt=None,  # Initial prompt
                # word_timestamps=False,  # Include word-level timestamps
                # prepend_punctuations="\"'“¿([{-",  # Prepend these to words
                # append_punctuations="\"'.。,，!！?？:：”)]}、",  # Append these to words
            )
        else:
            return None

    async def _transcribe_file_with_language(
        self, file_path: str, language: str
    ) -> dict:
        """Transcribe with forced language using decode_options"""
        try:
            if not self.model:
                raise
            loop = asyncio.get_event_loop()

            # Load audio
            audio = whisper.load_audio(file_path)
            audio = whisper.pad_or_trim(audio)

            # Make log-Mel spectrogram
            mel = whisper.log_mel_spectrogram(audio).to(self.model.device)

            # Detect language if not specified
            if language == "auto":
                _, probs = self.model.detect_language(mel)
                language = max(probs, key=probs.get)  # type: ignore
                log_info("Language detected", language=language, confidence=probs[language])  # type: ignore

            # Decode with language option
            options = whisper.DecodingOptions(
                language=language,
                without_timestamps=True,
                fp16=False,  # Use FP32 for CPU compatibility
            )
            if not self.model:
                raise
            result = whisper.decode(self.model, mel, options)

            return {
                "text": result.text,  # type: ignore
                "language": language,
                "duration": len(audio) / whisper.audio.SAMPLE_RATE,  # Estimate duration
            }

        except Exception as e:
            log_error(
                "Transcription with language failed", file_path=file_path, error=str(e)
            )
            raise

    async def transcribe_local_file(
        self, file_path: str, language: str = "en"
    ) -> Tuple[str, float]:
        """
        Transcribe from local file path
        """
        if not self.model_loaded:
            await self.load_model(settings.WHISPER_MODEL_SIZE)
        if not self.model:
            raise
        start_time = asyncio.get_event_loop().time()

        try:
            # Fix Windows path - replace double backslashes with single
            fixed_path = file_path.replace("\\\\", "\\")

            # Verify file exists
            if not os.path.exists(fixed_path):
                raise FileNotFoundError(f"Audio file not found: {fixed_path}")

            log_info("Transcribing local file", file_path=fixed_path)
            # Transcribe directly from local file
            loop = asyncio.get_event_loop()
            # Create a zero-argument callable so run_in_executor receives a single callable argument
            func = partial(self.model.transcribe, fixed_path, verbose=False)
            result = await loop.run_in_executor(None, func)

            processing_time = asyncio.get_event_loop().time() - start_time

            log_info(
                "Local file transcription completed",
                file_path=fixed_path,
                processing_time=processing_time,
                audio_duration=result.get("duration", 0),
                word_count=len(result["text"].split()),  # type: ignore
            )

            return result["text"].strip(), processing_time  # type: ignore

        except Exception as e:
            processing_time = asyncio.get_event_loop().time() - start_time
            log_error(
                "Local file transcription failed",
                file_path=file_path,
                processing_time=processing_time,
                error=str(e),
            )
            raise


# Global service instance
whisper_service = WhisperService()
