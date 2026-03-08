"""Speaker diarization service using SpeechBrain ECAPA-TDNN embeddings."""

import numpy as np
from pathlib import Path


MODELS_DIR = Path("data/models/ecapa-tdnn")

# Windowing parameters
WINDOW_SEC = 1.5
HOP_SEC = 0.75
MIN_SEGMENT_SEC = 0.5


class DiarizationService:
    """Speaker diarization using SpeechBrain ECAPA-TDNN embeddings + spectral clustering."""

    def __init__(self):
        self._encoder = None

    def _get_encoder(self):
        """Lazy-load the ECAPA-TDNN speaker encoder."""
        if self._encoder is not None:
            return self._encoder

        # torchaudio 2.10+ removed list_audio_backends(); patch for speechbrain compat
        import torchaudio
        if not hasattr(torchaudio, "list_audio_backends"):
            try:
                import torchcodec  # noqa: F401
                torchaudio.list_audio_backends = lambda: ["torchcodec"]
            except ImportError:
                torchaudio.list_audio_backends = lambda: ["soundfile"]

        from speechbrain.inference.speaker import EncoderClassifier

        print("Loading SpeechBrain ECAPA-TDNN speaker encoder...")
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        self._encoder = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=str(MODELS_DIR),
            run_opts={"device": "cpu"},
        )
        print("ECAPA-TDNN encoder loaded")
        return self._encoder

    def _extract_embeddings(self, wav_path: str) -> tuple[np.ndarray, list[tuple[float, float]]]:
        """Extract speaker embeddings from windowed segments.

        Returns:
            embeddings: numpy array of shape (n_windows, embedding_dim)
            timestamps: list of (start_sec, end_sec) for each window
        """
        import torch
        import torchaudio

        signal, sr = torchaudio.load(wav_path)
        # Ensure mono
        if signal.shape[0] > 1:
            signal = signal.mean(dim=0, keepdim=True)

        # Resample to 16kHz if needed
        if sr != 16000:
            signal = torchaudio.functional.resample(signal, sr, 16000)
            sr = 16000

        total_samples = signal.shape[1]
        total_duration = total_samples / sr
        window_samples = int(WINDOW_SEC * sr)
        hop_samples = int(HOP_SEC * sr)

        encoder = self._get_encoder()

        embeddings = []
        timestamps = []

        pos = 0
        while pos + window_samples <= total_samples:
            segment = signal[:, pos:pos + window_samples]
            with torch.no_grad():
                emb = encoder.encode_batch(segment)
            embeddings.append(emb.squeeze().numpy())
            start_sec = pos / sr
            end_sec = (pos + window_samples) / sr
            timestamps.append((start_sec, end_sec))
            pos += hop_samples

        # Handle trailing segment if long enough
        if pos < total_samples:
            remaining = total_samples - pos
            if remaining >= int(MIN_SEGMENT_SEC * sr):
                segment = signal[:, pos:]
                # Pad to window_samples for consistent embedding
                if segment.shape[1] < window_samples:
                    segment = torch.nn.functional.pad(
                        segment, (0, window_samples - segment.shape[1])
                    )
                with torch.no_grad():
                    emb = encoder.encode_batch(segment)
                embeddings.append(emb.squeeze().numpy())
                timestamps.append((pos / sr, total_duration))

        return np.array(embeddings), timestamps

    def _estimate_num_speakers(self, affinity_matrix: np.ndarray, max_speakers: int = 10) -> int:
        """Estimate number of speakers using eigenvalue gap heuristic."""
        from scipy.linalg import eigvalsh

        # Compute normalized Laplacian eigenvalues
        degree = np.sum(affinity_matrix, axis=1)
        degree_inv_sqrt = np.where(degree > 0, 1.0 / np.sqrt(degree), 0.0)
        D_inv_sqrt = np.diag(degree_inv_sqrt)
        L = np.eye(len(affinity_matrix)) - D_inv_sqrt @ affinity_matrix @ D_inv_sqrt

        eigenvalues = eigvalsh(L)
        eigenvalues = np.sort(eigenvalues)

        # Look at gaps between consecutive eigenvalues (skip first which is ~0)
        max_k = min(max_speakers, len(eigenvalues) - 1)
        if max_k < 2:
            return 1

        gaps = np.diff(eigenvalues[1:max_k + 1])
        if len(gaps) == 0:
            return 1

        # Number of speakers = index of largest gap + 2
        # (the gap after eigenvalue k means k+1 clusters)
        n_speakers = int(np.argmax(gaps) + 2)
        return max(1, n_speakers)

    def _cluster_speakers(
        self, embeddings: np.ndarray, num_speakers: int | None = None
    ) -> np.ndarray:
        """Cluster embeddings into speaker groups using spectral clustering.

        Returns array of speaker labels (0-indexed) for each embedding.
        """
        from scipy.spatial.distance import cosine
        from sklearn.cluster import SpectralClustering

        n = len(embeddings)
        if n <= 1:
            return np.zeros(n, dtype=int)

        # Build cosine similarity affinity matrix
        affinity = np.zeros((n, n))
        for i in range(n):
            for j in range(i, n):
                sim = 1.0 - cosine(embeddings[i], embeddings[j])
                affinity[i, j] = sim
                affinity[j, i] = sim

        # Clamp negative similarities to 0 (spectral clustering needs non-negative)
        affinity = np.maximum(affinity, 0)

        if num_speakers is None:
            num_speakers = self._estimate_num_speakers(affinity)

        if num_speakers <= 1:
            return np.zeros(n, dtype=int)

        clustering = SpectralClustering(
            n_clusters=num_speakers,
            affinity="precomputed",
            random_state=42,
        )
        labels = clustering.fit_predict(affinity)
        return labels

    def _merge_segments(
        self,
        timestamps: list[tuple[float, float]],
        labels: np.ndarray,
    ) -> list[dict]:
        """Merge consecutive windows with the same speaker into segments.

        Returns list of {speaker: int, start: float, end: float}.
        """
        if len(timestamps) == 0:
            return []

        segments = []
        current_speaker = int(labels[0])
        current_start = timestamps[0][0]
        current_end = timestamps[0][1]

        for i in range(1, len(timestamps)):
            speaker = int(labels[i])
            if speaker == current_speaker:
                # Extend current segment
                current_end = timestamps[i][1]
            else:
                segments.append({
                    "speaker": current_speaker,
                    "start": round(current_start, 2),
                    "end": round(current_end, 2),
                })
                current_speaker = speaker
                current_start = timestamps[i][0]
                current_end = timestamps[i][1]

        # Don't forget the last segment
        segments.append({
            "speaker": current_speaker,
            "start": round(current_start, 2),
            "end": round(current_end, 2),
        })

        return segments

    def diarize(self, wav_path: str, num_speakers: int | None = None) -> list[dict]:
        """Run the full diarization pipeline.

        Args:
            wav_path: Path to 16kHz mono WAV file.
            num_speakers: Optional known number of speakers. Auto-detected if None.

        Returns:
            List of segments: [{speaker: int, start: float, end: float}, ...]
            Speaker numbers are 1-indexed for display.
        """
        embeddings, timestamps = self._extract_embeddings(wav_path)

        if len(embeddings) == 0:
            return []

        labels = self._cluster_speakers(embeddings, num_speakers)
        segments = self._merge_segments(timestamps, labels)

        # Convert to 1-indexed speaker numbers
        for seg in segments:
            seg["speaker"] = seg["speaker"] + 1

        return segments


# Global instance
diarization_service = DiarizationService()
