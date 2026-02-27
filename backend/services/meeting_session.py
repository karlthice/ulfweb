"""Meeting session manager for chunked audio recording."""

import os
import subprocess
import tempfile
import uuid
from pathlib import Path


CHUNKS_DIR = Path("data/meeting_chunks")


class MeetingSessionManager:
    """Manages meeting recording sessions and audio chunk storage."""

    def __init__(self):
        self._sessions: dict[str, dict] = {}

    def create_session(self) -> str:
        """Create a new meeting session and return its ID."""
        session_id = uuid.uuid4().hex[:12]
        session_dir = CHUNKS_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        self._sessions[session_id] = {
            "dir": session_dir,
            "chunk_count": 0,
        }
        return session_id

    def session_exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    def add_chunk(self, session_id: str, chunk_data: bytes, chunk_index: int) -> None:
        """Save an audio chunk to disk."""
        session = self._sessions[session_id]
        chunk_path = session["dir"] / f"chunk_{chunk_index:04d}.webm"
        chunk_path.write_bytes(chunk_data)
        session["chunk_count"] = max(session["chunk_count"], chunk_index + 1)

    def assemble_chunks(self, session_id: str) -> str:
        """Concatenate all chunks into a single 16kHz mono WAV file.

        Returns the path to the assembled WAV file.
        """
        session = self._sessions[session_id]
        session_dir = session["dir"]

        # Find all chunk files sorted by name
        chunks = sorted(session_dir.glob("chunk_*.webm"))
        if not chunks:
            raise ValueError(f"No chunks found for session {session_id}")

        # Create concat list file for ffmpeg
        concat_list = session_dir / "concat.txt"
        with open(concat_list, "w") as f:
            for chunk in chunks:
                f.write(f"file '{chunk.resolve()}'\n")

        # Output WAV path
        wav_path = session_dir / "assembled.wav"

        # Use ffmpeg concat demuxer to join chunks, convert to 16kHz mono WAV
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list),
                "-ar", "16000",
                "-ac", "1",
                "-f", "wav",
                str(wav_path),
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg assembly failed: {result.stderr}")

        return str(wav_path)

    def cleanup_session(self, session_id: str) -> None:
        """Remove all files and directory for a session."""
        if session_id not in self._sessions:
            return

        session = self._sessions.pop(session_id)
        session_dir = session["dir"]

        # Remove all files in the directory
        if session_dir.exists():
            for f in session_dir.iterdir():
                f.unlink(missing_ok=True)
            session_dir.rmdir()


# Global instance
meeting_session_manager = MeetingSessionManager()
