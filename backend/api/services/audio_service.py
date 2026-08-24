"""
Audio processing service
"""
import os
from pathlib import Path
from typing import Optional
import subprocess


class AudioService:
    """Service for audio file processing and conversion"""
    
    def __init__(self):
        self.supported_formats = ['.webm', '.mp3', '.wav', '.m4a', '.ogg']
    
    def validate_audio_file(self, filepath: str) -> bool:
        """Validate audio file format and size"""
        path = Path(filepath)
        
        # Check if file exists
        if not path.exists():
            return False
        
        # Check file extension
        if path.suffix.lower() not in self.supported_formats:
            return False
        
        # Check file size (max 500MB)
        file_size = path.stat().st_size
        max_size = 500 * 1024 * 1024  # 500MB
        
        if file_size > max_size:
            return False
        
        return True
    
    def convert_to_wav(self, input_file: str, output_file: Optional[str] = None) -> str:
        """
        Convert audio file to WAV format using ffmpeg
        Returns path to converted file
        """
        if output_file is None:
            output_file = str(Path(input_file).with_suffix('.wav'))
        
        try:
            # Use ffmpeg to convert
            subprocess.run([
                'ffmpeg',
                '-i', input_file,
                '-ar', '16000',  # Sample rate
                '-ac', '1',      # Mono
                '-y',            # Overwrite output file
                output_file
            ], check=True, capture_output=True)
            
            return output_file
        except subprocess.CalledProcessError as e:
            raise Exception(f"Audio conversion failed: {e.stderr.decode()}")
        except FileNotFoundError:
            raise Exception("ffmpeg not found. Please install ffmpeg.")
    
    def convert_to_mp3(self, input_file: str, output_file: str, bitrate: int = 64) -> str:
        """
        Convert audio file to MP3 format with specified bitrate using ffmpeg
        Useful for compressing large audio files
        
        Args:
            input_file: Path to input audio file
            output_file: Path to output MP3 file
            bitrate: Bitrate in kbps (default: 64, can go as low as 32)
        
        Returns:
            Path to converted file
        """
        try:
            # Use ffmpeg to convert to MP3 with specified bitrate
            subprocess.run([
                'ffmpeg',
                '-i', input_file,
                '-codec:a', 'libmp3lame',  # MP3 codec
                '-b:a', f'{bitrate}k',      # Audio bitrate
                '-ar', '16000',            # Sample rate (16kHz is sufficient for speech)
                '-ac', '1',                # Mono
                '-y',                      # Overwrite output file
                output_file
            ], check=True, capture_output=True, timeout=300)  # 5 minute timeout
            
            return output_file
        except subprocess.TimeoutExpired:
            raise Exception("Audio compression timed out after 5 minutes")
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise Exception(f"Audio compression failed: {error_msg}")
        except FileNotFoundError:
            raise Exception("ffmpeg not found. Please install ffmpeg.")
    
    def get_audio_duration(self, filepath: str) -> float:
        """Get audio duration in seconds"""
        try:
            result = subprocess.run([
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                filepath
            ], capture_output=True, text=True, check=True)
            
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
            return 0.0
    
    def extract_audio_segment(self, input_file: str, start_time: float, duration: float, output_file: str) -> str:
        """
        Extract a segment from audio file
        
        Args:
            input_file: Path to input audio file
            start_time: Start time in seconds
            duration: Duration in seconds
            output_file: Path to output file (format determined by extension)
        
        Returns:
            Path to extracted file
        """
        try:
            # Determine codec based on output file extension
            codec_args = []
            if output_file.endswith('.mp3'):
                codec_args = ['-codec:a', 'libmp3lame', '-b:a', '64k']
            elif output_file.endswith('.wav'):
                codec_args = ['-codec:a', 'pcm_s16le']
            
            subprocess.run([
                'ffmpeg',
                '-i', input_file,
                '-ss', str(start_time),
                '-t', str(duration),
                '-ar', '16000',  # Sample rate
                '-ac', '1',      # Mono
                '-y',            # Overwrite
            ] + codec_args + [output_file], check=True, capture_output=True, timeout=300)
            
            return output_file
        except subprocess.TimeoutExpired:
            raise Exception("Audio extraction timed out after 5 minutes")
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise Exception(f"Audio extraction failed: {error_msg}")

