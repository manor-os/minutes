"""
Transcription service using OpenAI Whisper API
Note: DeepSeek doesn't support audio transcription, so we use OpenAI Whisper
"""
import os
from typing import Optional
from openai import OpenAI
from loguru import logger

from .audio_service import AudioService


class TranscriptionService:
    """Service for transcribing audio to text"""
    
    def __init__(self):
        # For transcription, we need OpenAI Whisper (DeepSeek doesn't support audio)
        # IMPORTANT: Must use a valid OpenAI API key, not DeepSeek key
        # Whisper API requires OpenAI credentials
        api_key = os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            logger.warning("OPENAI_API_KEY not set. Audio transcription will fail. Please set a valid OpenAI API key for Whisper transcription.")
        elif api_key == os.getenv("DEEPSEEK_API_KEY"):
            logger.warning("OPENAI_API_KEY appears to be a DeepSeek key. Whisper requires a valid OpenAI API key. Transcription may fail.")
        
        # For Whisper, we always use OpenAI endpoint (not DeepSeek)
        self.client = OpenAI(api_key=api_key) if api_key else None
        self.audio_service = AudioService()
        self.model = "whisper-1"
    
    def transcribe(self, audio_filepath: str, language: Optional[str] = None) -> str:
        """
        Transcribe audio file to text using OpenAI Whisper
        
        Args:
            audio_filepath: Path to audio file
            language: Optional language code (e.g., 'en', 'zh')
        
        Returns:
            Transcribed text
        """
        try:
            if not self.client:
                raise ValueError("OpenAI API key not configured. Please set OPENAI_API_KEY environment variable with a valid OpenAI API key for Whisper transcription.")
            
            # Validate audio file
            if not self.audio_service.validate_audio_file(audio_filepath):
                raise ValueError(f"Invalid audio file: {audio_filepath}")
            
            # Open audio file
            with open(audio_filepath, "rb") as audio_file:
                # Call OpenAI Whisper API
                transcript = self.client.audio.transcriptions.create(
                    model=self.model,
                    file=audio_file,
                    language=language,
                    response_format="text"
                )
            
            logger.info(f"Transcription completed for {audio_filepath}")
            return transcript
            
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "invalid_api_key" in error_msg.lower():
                logger.error(f"Transcription failed: Invalid OpenAI API key. Please set a valid OPENAI_API_KEY environment variable. Whisper requires OpenAI credentials, not DeepSeek.")
                raise Exception("Transcription failed: Invalid or missing OpenAI API key. Please configure OPENAI_API_KEY with a valid OpenAI API key for Whisper transcription.")
            logger.error(f"Transcription failed for {audio_filepath}: {error_msg}")
            raise Exception(f"Transcription failed: {error_msg}")
    
    def transcribe_with_timestamps(self, audio_filepath: str, language: Optional[str] = None) -> dict:
        """
        Transcribe audio with word-level timestamps
        
        Returns:
            Dictionary with transcript, segments, and cost information
        """
        try:
            if not self.client:
                raise ValueError("OpenAI API key not configured. Please set OPENAI_API_KEY environment variable with a valid OpenAI API key for Whisper transcription.")
            
            import os
            from pathlib import Path
            import tempfile
            
            # Get audio file size for cost calculation
            audio_file_size = Path(audio_filepath).stat().st_size
            audio_duration = None
            
            # OpenAI Whisper API has a 25MB file size limit
            # If file is too large, compress it first
            MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB
            audio_file_to_use = audio_filepath
            temp_file_created = False
            
            if audio_file_size > MAX_FILE_SIZE:
                logger.warning(f"Audio file ({audio_file_size / 1024 / 1024:.2f}MB) exceeds Whisper limit (25MB). Compressing...")
                try:
                    # Get audio duration first to calculate appropriate bitrate
                    estimated_duration = self.audio_service.get_audio_duration(audio_filepath)
                    if estimated_duration <= 0:
                        # Fallback: estimate duration from file size (rough: 1MB ≈ 1 minute)
                        estimated_duration = audio_file_size / (1024 * 1024) * 60
                    
                    # Create a temporary compressed file
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
                    temp_file.close()
                    
                    # Use ffmpeg to compress audio to MP3 with lower bitrate
                    # Target: reduce to ~20MB to be safe
                    # Calculate bitrate: target_size (20MB) / duration (seconds) * 8 (bits per byte)
                    if estimated_duration > 0:
                        target_bitrate = max(32, int((20 * 1024 * 1024 * 8) / estimated_duration / 1000))  # kbps
                        target_bitrate = min(target_bitrate, 128)  # Cap at 128kbps
                    else:
                        target_bitrate = 64  # Default to 64kbps
                    
                    logger.info(f"Compressing audio with bitrate: {target_bitrate}kbps (estimated duration: {estimated_duration:.1f}s)")
                    self.audio_service.convert_to_mp3(audio_filepath, temp_file.name, bitrate=target_bitrate)
                    
                    # Check if compressed file is still too large
                    compressed_size = Path(temp_file.name).stat().st_size
                    if compressed_size > MAX_FILE_SIZE:
                        # Try even lower bitrate (32kbps minimum)
                        logger.warning(f"Compressed file still too large ({compressed_size / 1024 / 1024:.2f}MB). Trying 32kbps...")
                        os.remove(temp_file.name)
                        self.audio_service.convert_to_mp3(audio_filepath, temp_file.name, bitrate=32)
                        compressed_size = Path(temp_file.name).stat().st_size
                    
                    if compressed_size <= MAX_FILE_SIZE:
                        audio_file_to_use = temp_file.name
                        temp_file_created = True
                        logger.info(f"Audio compressed from {audio_file_size / 1024 / 1024:.2f}MB to {compressed_size / 1024 / 1024:.2f}MB")
                    else:
                        # If compression still doesn't work, try chunk-by-chunk transcription
                        logger.warning(f"Compressed file still too large ({compressed_size / 1024 / 1024:.2f}MB). Trying chunk-by-chunk transcription...")
                        os.remove(temp_file.name)
                        # Use chunk-by-chunk transcription instead
                        return self._transcribe_in_chunks(audio_filepath, language)
                except Exception as compress_error:
                    logger.error(f"Error compressing audio: {str(compress_error)}")
                    if temp_file_created and os.path.exists(temp_file.name):
                        os.remove(temp_file.name)
                    raise ValueError(f"Audio file too large ({audio_file_size / 1024 / 1024:.2f}MB) and compression failed: {str(compress_error)}")
            
            with open(audio_file_to_use, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model=self.model,
                    file=audio_file,
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["word", "segment"]
                )
                
                audio_duration = getattr(transcript, 'duration', None)
            
            # Clean up temporary file if created
            if temp_file_created and os.path.exists(audio_file_to_use):
                try:
                    os.remove(audio_file_to_use)
                except Exception as e:
                    logger.warning(f"Could not remove temporary file: {str(e)}")
            
            # Calculate Whisper cost: $0.006 per minute (as of 2024)
            # Whisper pricing is per minute of audio, not tokens
            # Use original file size for cost calculation if available
            whisper_cost_per_minute = 0.006
            cost = 0.0
            if audio_duration:
                minutes = audio_duration / 60.0
                cost = minutes * whisper_cost_per_minute
            elif audio_file_size:
                # Estimate duration from file size if duration not available
                # Rough estimate: 1MB ≈ 1 minute of audio at typical compression
                estimated_minutes = audio_file_size / (1024 * 1024)
                cost = estimated_minutes * whisper_cost_per_minute
            
            return {
                "text": transcript.text,
                "language": transcript.language,
                "duration": audio_duration,
                "words": [
                    {
                        "word": word.word,
                        "start": word.start,
                        "end": word.end
                    }
                    for word in transcript.words
                ] if hasattr(transcript, 'words') else [],
                "segments": [
                    {
                        "id": seg.id,
                        "start": seg.start,
                        "end": seg.end,
                        "text": seg.text
                    }
                    for seg in transcript.segments
                ] if hasattr(transcript, 'segments') else [],
                "cost": {
                    "service": "whisper-1",
                    "duration_seconds": audio_duration,
                    "duration_minutes": round(audio_duration / 60.0, 2) if audio_duration else 0,
                    "cost_per_minute": whisper_cost_per_minute,
                    "total_cost": round(cost, 4),
                    "currency": "USD"
                }
            }
            
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "invalid_api_key" in error_msg.lower():
                logger.error(f"Transcription failed: Invalid OpenAI API key. Please set a valid OPENAI_API_KEY environment variable. Whisper requires OpenAI credentials, not DeepSeek.")
                raise Exception("Transcription failed: Invalid or missing OpenAI API key. Please configure OPENAI_API_KEY with a valid OpenAI API key for Whisper transcription. Note: DeepSeek API keys cannot be used for Whisper - you need a separate OpenAI API key.")
            logger.error(f"Transcription with timestamps failed: {error_msg}")
            raise Exception(f"Transcription failed: {error_msg}")
    
    def _transcribe_in_chunks(self, audio_filepath: str, language: Optional[str] = None) -> dict:
        """
        Transcribe large audio file by splitting into chunks and transcribing each separately
        This is used when compression fails to get file below 25MB limit
        
        Args:
            audio_filepath: Path to audio file
            language: Optional language code
        
        Returns:
            Dictionary with combined transcript, segments, and cost information
        """
        try:
            import os
            from pathlib import Path
            import tempfile
            
            # Get audio duration
            duration = self.audio_service.get_audio_duration(audio_filepath)
            if duration <= 0:
                raise ValueError("Could not determine audio duration")
            
            # Split into chunks of ~10 minutes each (600 seconds)
            # This ensures each chunk is well under 25MB
            CHUNK_DURATION = 600  # 10 minutes
            chunk_count = int(duration / CHUNK_DURATION) + (1 if duration % CHUNK_DURATION > 0 else 0)
            
            logger.info(f"Transcribing {duration:.1f}s audio in {chunk_count} chunks of ~{CHUNK_DURATION}s each")
            
            all_segments = []
            all_words = []
            total_cost = 0.0
            temp_files = []
            
            try:
                for i in range(chunk_count):
                    start_time = i * CHUNK_DURATION
                    chunk_duration = min(CHUNK_DURATION, duration - start_time)
                    
                    if chunk_duration <= 0:
                        break
                    
                    logger.info(f"Processing chunk {i+1}/{chunk_count} ({start_time:.1f}s - {start_time + chunk_duration:.1f}s)")
                    
                    # Extract chunk
                    chunk_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
                    chunk_file.close()
                    temp_files.append(chunk_file.name)
                    
                    self.audio_service.extract_audio_segment(
                        audio_filepath,
                        start_time,
                        chunk_duration,
                        chunk_file.name
                    )
                    
                    # Compress chunk if needed
                    chunk_size = Path(chunk_file.name).stat().st_size
                    MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB
                    
                    if chunk_size > MAX_FILE_SIZE:
                        logger.warning(f"Chunk {i+1} is {chunk_size / 1024 / 1024:.2f}MB, compressing...")
                        compressed_chunk = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
                        compressed_chunk.close()
                        temp_files.append(compressed_chunk.name)
                        
                        # Calculate bitrate for this chunk
                        target_bitrate = max(32, int((20 * 1024 * 1024 * 8) / chunk_duration / 1000))
                        target_bitrate = min(target_bitrate, 128)
                        
                        self.audio_service.convert_to_mp3(chunk_file.name, compressed_chunk.name, bitrate=target_bitrate)
                        os.remove(chunk_file.name)
                        chunk_file.name = compressed_chunk.name
                    
                    # Transcribe chunk
                    with open(chunk_file.name, "rb") as chunk_audio:
                        chunk_transcript = self.client.audio.transcriptions.create(
                            model=self.model,
                            file=chunk_audio,
                            language=language,
                            response_format="verbose_json",
                            timestamp_granularities=["word", "segment"]
                        )
                    
                    # Adjust timestamps to account for chunk offset
                    chunk_offset = start_time
                    
                    # Adjust word timestamps
                    if hasattr(chunk_transcript, 'words') and chunk_transcript.words:
                        for word in chunk_transcript.words:
                            all_words.append({
                                "word": word.word,
                                "start": word.start + chunk_offset,
                                "end": word.end + chunk_offset
                            })
                    
                    # Adjust segment timestamps
                    if hasattr(chunk_transcript, 'segments') and chunk_transcript.segments:
                        for seg in chunk_transcript.segments:
                            all_segments.append({
                                "id": len(all_segments),
                                "start": seg.start + chunk_offset,
                                "end": seg.end + chunk_offset,
                                "text": seg.text
                            })
                    
                    # Calculate cost for this chunk
                    chunk_duration_actual = getattr(chunk_transcript, 'duration', chunk_duration)
                    chunk_cost = (chunk_duration_actual / 60.0) * 0.006
                    total_cost += chunk_cost
                    
                    logger.info(f"Chunk {i+1}/{chunk_count} transcribed: {len(getattr(chunk_transcript, 'text', ''))} chars, cost: ${chunk_cost:.4f}")
                
                # Combine all text
                combined_text = " ".join([seg["text"] for seg in all_segments])
                
                logger.info(f"Chunk-by-chunk transcription completed: {len(combined_text)} chars, {len(all_segments)} segments, total cost: ${total_cost:.4f}")
                
                return {
                    "text": combined_text,
                    "language": getattr(chunk_transcript, 'language', language or 'en'),
                    "duration": duration,
                    "words": all_words,
                    "segments": all_segments,
                    "cost": {
                        "service": "whisper-1",
                        "duration_seconds": duration,
                        "duration_minutes": round(duration / 60.0, 2),
                        "cost_per_minute": 0.006,
                        "total_cost": round(total_cost, 4),
                        "currency": "USD",
                        "chunk_count": chunk_count
                    }
                }
            
            finally:
                # Clean up temporary files
                for temp_file in temp_files:
                    try:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                    except Exception as e:
                        logger.warning(f"Could not remove temporary file {temp_file}: {str(e)}")
            
        except Exception as e:
            logger.error(f"Chunk-by-chunk transcription failed: {str(e)}")
            raise Exception(f"Chunk-by-chunk transcription failed: {str(e)}")
    
    def identify_speakers(self, transcript_text: str, segments: list = None) -> list:
        """
        Identify different speakers in the transcript using LLM analysis
        This analyzes the transcript to identify distinct speakers based on:
        - Speaking patterns
        - Context clues
        - Name mentions
        - Pronoun usage
        
        Returns:
            List of speaker-segmented transcript entries
        """
        try:
            import json
            from .llm_config import get_openrouter_client, get_llm_model

            client = get_openrouter_client()
            model = get_llm_model()
            
            # Prepare prompt for speaker identification
            if segments:
                segments_text = "\n".join([f"[{seg.get('start', 0):.1f}s-{seg.get('end', 0):.1f}s] {seg.get('text', '')}" for seg in segments[:20]])
                prompt = f"""Analyze the following meeting transcript with timestamps and identify different speakers. 
For each distinct speaker, assign them a label (Speaker 1, Speaker 2, etc.) or use their name if mentioned.

Transcript with timestamps:
{segments_text}

Return a JSON object with a "segments" array where each entry represents a segment of speech with:
- "speaker": The speaker label (e.g., "Speaker 1", "John", "Sarah")
- "text": The spoken text
- "start_time": Start time in seconds (if available, otherwise null)
- "end_time": End time in seconds (if available, otherwise null)

Try to identify at least 2-3 distinct speakers if the conversation suggests multiple people.
Look for patterns like:
- Different speaking styles
- Name mentions ("John said...", "Sarah mentioned...")
- Pronoun usage ("I think...", "We should...")
- Question/answer patterns

Return ONLY valid JSON with a "segments" key, no additional text."""
            else:
                # Break transcript into sentences for analysis
                sentences = transcript_text.split('. ')
                prompt = f"""Analyze the following meeting transcript and identify different speakers. 
For each distinct speaker, assign them a label (Speaker 1, Speaker 2, etc.) or use their name if mentioned.

Transcript:
{transcript_text}

Return a JSON object with a "segments" array where each entry represents a segment of speech with:
- "speaker": The speaker label (e.g., "Speaker 1", "John", "Sarah")
- "text": The spoken text (break into logical speaking segments)
- "start_time": null (not available)
- "end_time": null (not available)

Try to identify at least 2-3 distinct speakers if the conversation suggests multiple people.
Look for patterns like different speaking styles, name mentions, pronoun usage, and question/answer patterns.

Return ONLY valid JSON with a "segments" key, no additional text."""

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing meeting transcripts to identify different speakers. Return only valid JSON arrays."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Handle different response formats
            if "segments" in result:
                segments = result["segments"]
            elif "speakers" in result:
                segments = result["speakers"]
            elif isinstance(result, list):
                segments = result
            else:
                # Fallback: create a single speaker entry
                segments = [{"speaker": "Speaker 1", "text": transcript_text, "start_time": None, "end_time": None}]
            
            # Ensure all segments have required fields
            for seg in segments:
                if "speaker" not in seg:
                    seg["speaker"] = "Unknown"
                if "text" not in seg:
                    seg["text"] = ""
                if "start_time" not in seg:
                    seg["start_time"] = None
                if "end_time" not in seg:
                    seg["end_time"] = None
            
            return segments
                
        except Exception as e:
            logger.error(f"Speaker identification failed: {str(e)}")
            # Fallback: return transcript as single speaker
            return [{"speaker": "Speaker 1", "text": transcript_text, "start_time": None, "end_time": None}]
    
    def translate(self, audio_filepath: str, target_language: str = "en") -> str:
        """
        Transcribe and translate audio to target language
        
        Args:
            audio_filepath: Path to audio file
            target_language: Target language code
        
        Returns:
            Translated text
        """
        try:
            with open(audio_filepath, "rb") as audio_file:
                translation = self.client.audio.translations.create(
                    model=self.model,
                    file=audio_file,
                    response_format="text"
                )
            
            return translation
            
        except Exception as e:
            logger.error(f"Translation failed: {str(e)}")
            raise Exception(f"Translation failed: {str(e)}")

