from fastapi import UploadFile
import tempfile
import os
import asyncio
from typing import Tuple
import aiohttp
import aiofiles
from app.core.logging import log_info, log_error
from app.config import settings

# Replace import
from faster_whisper import WhisperModel


class WhisperService:
    """
    Optimized Whisper service using faster-whisper for CPU/GPU acceleration.
    """

    def __init__(self):
        self.model = None
        self.model_loaded = False

    async def load_model(self, model_size: str = "base"):
        """
        Load faster-whisper model asynchronously.
        Uses int8 quantization on CPU for best speed on low-end hardware.
        """
        if self.model_loaded:
            return
        try:
            # Run the (blocking) model load in a thread pool
            loop = asyncio.get_event_loop()
            self.model = await loop.run_in_executor(
                None,
                lambda: WhisperModel(
                    model_size,
                    device="cpu",  # Force CPU (your Intel GPU isn't CUDA)
                    compute_type="int8",  # Fastest on CPU, lower memory
                    num_workers=1,  # Adjust based on CPU cores
                    cpu_threads=2,  # Limit threads to avoid overloading
                ),
            )
            self.model_loaded = True
            log_info(
                "Faster-Whisper model loaded",
                model_size=model_size,
                device="cpu",
                compute_type="int8",
            )
        except Exception as e:
            log_error(
                "Failed to load Faster-Whisper model",
                error=str(e),
                model_size=model_size,
            )
            # Fallback to float32 if int8 not available
            try:
                loop = asyncio.get_event_loop()
                self.model = await loop.run_in_executor(
                    None,
                    lambda: WhisperModel(
                        model_size,
                        device="cpu",
                        compute_type="float32",
                        num_workers=1,
                        cpu_threads=2,
                    ),
                )
                self.model_loaded = True
                log_info(
                    "Faster-Whisper model loaded with float32 fallback",
                    model_size=model_size,
                )
            except Exception as e2:
                log_error("Fallback also failed", error=str(e2))
                raise

    async def transcribe_audio_url(
        self, audio_url: str, language: str = "en"
    ) -> Tuple[str, float]:
        """Transcribe audio from a URL."""
        if not self.model_loaded:
            await self.load_model(settings.WHISPER_MODEL_SIZE)

        start_time = asyncio.get_event_loop().time()
        temp_path = None

        try:
            # Download to temporary file
            temp_path = await self._download_audio(audio_url)
            transcript = await self._transcribe_file(temp_path, language)
            processing_time = asyncio.get_event_loop().time() - start_time

            log_info(
                "URL transcription completed",
                audio_url=audio_url,
                processing_time=processing_time,
            )
            return transcript, processing_time
        except Exception as e:
            processing_time = asyncio.get_event_loop().time() - start_time
            log_error(
                "URL transcription failed",
                audio_url=audio_url,
                error=str(e),
                processing_time=processing_time,
            )
            raise
        finally:
            if temp_path:
                await self._cleanup_file(temp_path)

    async def transcribe_audio_file(
        self, audio_file: UploadFile, language: str = "en"
    ) -> Tuple[str, float]:
        """Transcribe an uploaded audio file."""
        if not self.model_loaded:
            await self.load_model(settings.WHISPER_MODEL_SIZE)

        start_time = asyncio.get_event_loop().time()
        temp_path = None

        try:
            # Save uploaded file to temporary location
            temp_path = await self._save_upload_file(audio_file)
            transcript = await self._transcribe_file(temp_path, language)
            processing_time = asyncio.get_event_loop().time() - start_time

            log_info(
                "File transcription completed",
                filename=audio_file.filename,
                processing_time=processing_time,
            )
            return transcript, processing_time
        except Exception as e:
            processing_time = asyncio.get_event_loop().time() - start_time
            log_error(
                "File transcription failed",
                filename=audio_file.filename,
                error=str(e),
                processing_time=processing_time,
            )
            raise
        finally:
            if temp_path:
                await self._cleanup_file(temp_path)

    async def transcribe_local_file(
        self, file_path: str, language: str = "en"
    ) -> Tuple[str, float]:
        """Transcribe a file already on disk."""
        if not self.model_loaded:
            await self.load_model(settings.WHISPER_MODEL_SIZE)

        # Fix Windows path if needed
        fixed_path = file_path.replace("\\\\", "\\")
        if not os.path.exists(fixed_path):
            raise FileNotFoundError(f"Audio file not found: {fixed_path}")

        start_time = asyncio.get_event_loop().time()
        try:
            transcript = await self._transcribe_file(fixed_path, language)
            processing_time = asyncio.get_event_loop().time() - start_time

            log_info(
                "Local file transcription completed",
                file_path=fixed_path,
                processing_time=processing_time,
            )
            return transcript, processing_time
        except Exception as e:
            processing_time = asyncio.get_event_loop().time() - start_time
            log_error(
                "Local file transcription failed",
                file_path=file_path,
                error=str(e),
                processing_time=processing_time,
            )
            raise

    async def _transcribe_file(self, audio_path: str, language: str) -> str:
        """
        Run faster-whisper transcription on the given audio file.
        Returns the full transcript as a single string.
        """
        try:
            loop = asyncio.get_event_loop()

            # faster-whisper transcribe is blocking; run in executor
            segments, info = await loop.run_in_executor(
                None,
                lambda: self.model.transcribe(  # type: ignore
                    audio_path,
                    language=(
                        language if language != "auto" else None
                    ),  # None lets the model detect
                    beam_size=1,  # Use greedy decoding for speed
                    word_timestamps=False,  # We only need text
                    vad_filter=False,  # Optional: set True if you want to filter out non-speech
                    vad_parameters=dict(min_silence_duration_ms=500),
                    log_progress=True,  # Enable logging for better visibility
                ),
            )

            # Collect all segment texts
            transcript_parts = []
            for segment in segments:
                transcript_parts.append(segment.text)

            full_text = " ".join(transcript_parts).strip()
            log_info(
                "Transcription completed",
                audio_path=audio_path,
                language=info.language,
                duration=info.duration,
            )
            return full_text

        except Exception as e:
            log_error("_transcribe_file failed", audio_path=audio_path, error=str(e))
            raise

    async def _download_audio(self, audio_url: str) -> str:
        """Download audio file to a temporary location."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(audio_url) as response:
                    if response.status != 200:
                        raise Exception(
                            f"Failed to download audio: HTTP {response.status}"
                        )

                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                    temp_path = temp_file.name
                    temp_file.close()

                    async with aiofiles.open(temp_path, "wb") as f:
                        await f.write(await response.read())

                    return temp_path
        except Exception as e:
            log_error("Audio download failed", audio_url=audio_url, error=str(e))
            raise

    async def _save_upload_file(self, upload_file: UploadFile) -> str:
        """Save an uploaded file to a temporary location."""
        try:
            # Preserve original extension
            suffix = os.path.splitext(str(upload_file.filename))[1] or ".tmp"
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            temp_path = temp_file.name
            temp_file.close()

            async with aiofiles.open(temp_path, "wb") as f:
                content = await upload_file.read()
                await f.write(content)

            return temp_path
        except Exception as e:
            log_error(
                "Failed to save uploaded file",
                filename=upload_file.filename,
                error=str(e),
            )
            raise

    async def _cleanup_file(self, file_path: str):
        """Delete a temporary file."""
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
        except Exception as e:
            log_error("File cleanup failed", file_path=file_path, error=str(e))
            raise


whisper_service = WhisperService()
