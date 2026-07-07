# mimizam

**mimizam** is a Python implementation for audio fingerprinting and video fingerprinting. Audio uses Shazam-like algorithms to generate unique fingerprints, while video generates per-frame fingerprints using AKAZE features + VLAD + PCA. Both achieve high-precision identification by matching against a database.

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-73%25-yellowgreen.svg)]()

## Key Features

- **High-Precision Audio Fingerprinting**: Robust fingerprint generation based on Shazam algorithms
- **Video Fingerprinting**: Per-frame fingerprints via AKAZE features + VLAD + PCA, with partial-clip search using per-frame ANN voting
- **Combined Audio + Video Search**: Evaluates audio and video matches with a unified score (with position-divergence checking)
- **Adaptive Parameter Optimization**: Automatic parameter adjustment based on audio characteristics
- **Multi-Database Support**: SQLite, MySQL, MariaDB, PostgreSQL, Elasticsearch (video-fingerprint ANN uses sqlite-vec / pgvector / Elasticsearch dense_vector / MariaDB native VECTOR)
- **Real-time Audio Recognition**: Instantly identify songs from short audio clips
- **Visualization**: Spectrogram and peak detection visualization

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/animalmatsuzawa/mimizam.git
cd mimizam

# Install dependencies
pip install -r requirements.txt

# Install package (development mode)
pip install -e .
```

The dependencies required for video fingerprinting (`opencv-contrib-python` / `scikit-learn` / `scenedetect`) are included as core dependencies. `sqlite-vec`, required for ANN in the default SQLite backend, is also a core dependency.

> **About OpenCV**: Video fingerprinting uses AKAZE, so `opencv-contrib-python` is required (do not install `opencv-python`, which conflicts with it). AKAZE is exposed as `cv2.AKAZE_create` on OpenCV 4.x and `cv2.xfeatures2d.AKAZE_create` on OpenCV 5.x; mimizam supports both.

### Basic Usage

```python
from mimizam import create_mimizam_sqlite

# Simple setup using SQLite
with create_mimizam_sqlite("my_music.db") as mimizam:
    # Add a song to the database
    song_id = mimizam.add_song("path/to/song.wav", "My Song", "Artist Name")
    print(f"Song added (ID: {song_id})")
    
    # Audio search
    results = mimizam.search_song("path/to/query.wav", min_confidence=0.3)
    for result in results:
        song = result['song']
        confidence = result['confidence']
        print(f"Found: {song.title} by {song.artist} (Confidence: {confidence:.2%})")
    
    # Audio identification (most likely song)
    identified = mimizam.identify_audio("path/to/query.wav")
    if identified:
        song, confidence = identified
        print(f"Identified: {song.title} (Confidence: {confidence:.2%})")
```

### Basic Video Usage

```python
from mimizam import create_mimizam_sqlite

with create_mimizam_sqlite("my_media.db") as mimizam:
    # Configure video fingerprinting at runtime (as a class feature, not env vars)
    mimizam.configure_video(scene_eval_fps=4.0, profile_frames=False)

    # Load the pre-trained codebook/PCA model (recommended)
    mimizam.load_video_model("model/codebook_model.npz")

    # Register a video
    # (If no model is loaded, the first added video trains the model on itself,
    #  but a codebook learned from a single video is low quality. Loading the
    #  pre-trained model above is strongly recommended.)
    video_id = mimizam.add_video("path/to/video.mp4", "My Video")

    # Search by video (per-frame ANN voting -> precise matching, with PiP detection)
    results = mimizam.search_video("path/to/clip.mp4", top_k=5)
    for result in results:
        print(result)
```

CLI tools that use the pretrained codebook model (`model/codebook_model.npz`) are also bundled.

```bash
# Register a video (registers combined audio + video fingerprints)
python examples/movie_fingerprinter.py path/to/video.mp4 --database ./media.db \
    --model ./model/codebook_model.npz

# Register while keeping raw AKAZE descriptors in the DB.
# Required if you later want to regenerate fingerprints after updating the
# model (rebuild_video_fingerprints); note the DB grows larger.
python examples/movie_fingerprinter.py path/to/video.mp4 --database ./media.db \
    --model ./model/codebook_model.npz --store-descriptors

# Combined search by video (audio + video)
python examples/movie_search.py -D -k 10 -m ./model/codebook_model.npz \
    path/to/clip.mp4 --database ./media.db
```

### Running Demos

```bash
# Generate demo audio files
python scripts/create_demo_audio.py

# Run Mimizam demo
python examples/mimizam_demo.py
```

## Architecture

### Core Technologies

1. **Spectrogram Generation**: Time-frequency analysis using Short-Time Fourier Transform (STFT)
2. **Adaptive Peak Detection**: Dynamic threshold-based spectral peak extraction based on audio characteristics
3. **Scale-invariant Fingerprinting**: 32-bit bit-packed hashes derived from anchor + two-target peak triplets. Each hash encodes a time ratio `(t1-tA)/(t2-tA)` and frequency ratios `log2(f1/fA)`, `log2(f2/fA)`, making it inherently invariant to speed (time-stretch) and pitch (frequency-scale) changes. Not a cryptographic hash. (Replaces the former absolute `[f1][f2][Δt]` scheme; existing databases must be re-fingerprinted.)
4. **Single-search Matching**: One database lookup (no time/freq scale brute-force), followed by robust line-fit regression `db ≈ slope·query + offset` via Hough voting to recover the time scale/offset and score confidence from aligned inliers

### Video Fingerprinting

1. **Scene / Keyframe Selection**: Detect cuts with PySceneDetect (`ContentDetector`) over frames evaluated at `scene_eval_fps`, plus periodic sampling
2. **AKAZE Feature Extraction**: Extract local AKAZE (MLDB) descriptors per keyframe (`opencv-contrib-python` required). AKAZE is chosen because it is robust to rotation/scale/brightness changes (re-encoding, PiP downscaling), its nonlinear diffusion scale space preserves edges even under compression blur, its binary MLDB descriptor is compact and fast to match at the scale of ~1M descriptors per 1,000 frames, it is license-unencumbered and available on both OpenCV 4.x/5.x, and as a classical CV algorithm it runs on CPU only (no GPU or deep-learning model weights required, unlike ALIKED/DISK/LightGlue). See [the spec](docs/video_fingerprint_spec.md) for the full rationale.
3. **VLAD + PCA Encoding**: Aggregate descriptors into a per-frame fingerprint via VLAD over a learned codebook, then reduce dimensionality with PCA
4. **Per-frame ANN Voting**: Each query frame retrieves nearest neighbors via the backend's vector ANN, aggregating votes/similarity per video
5. **Geometric Verification (re-ranking)**: For the top candidates, query and DB frames are matched by AKAZE descriptor geometric verification (BF Hamming nearest-neighbor + Lowe's ratio test + homography RANSAC/USAC_MAGSAC inlier count). Verified pairs are clustered by DB timestamp proximity to determine matched segments (with PiP rectangle detection)

## Database Backends

mimizam supports multiple databases:

```python
from mimizam import (
    create_mimizam_sqlite,
    create_mimizam_mysql,
    create_mimizam_mariadb,
    create_mimizam_postgresql,
    create_mimizam_elasticsearch
)

# SQLite (Simple・Fast・Recommended; video ANN via sqlite-vec)
mimizam = create_mimizam_sqlite("fingerprints.db")

# MySQL (Scalability; video ANN via brute-force)
mimizam = create_mimizam_mysql(
    host="localhost", database="music_db",
    username="user", password="pass"
)

# MariaDB (video ANN via native VECTOR index on 11.7+)
mimizam = create_mimizam_mariadb(
    host="localhost", database="music_db",
    username="user", password="pass"
)

# PostgreSQL (High Performance; video ANN via pgvector)
mimizam = create_mimizam_postgresql(
    host="localhost", database="music_db",
    username="user", password="pass"
)

# Elasticsearch (Distributed Search; video ANN via dense_vector kNN)
mimizam = create_mimizam_elasticsearch(
    host="localhost", index_name="music_index"
)
```

For video-fingerprint frame ANN search, SQLite uses `sqlite-vec`, PostgreSQL uses `pgvector`, Elasticsearch uses `dense_vector`, and MariaDB uses a native `VECTOR` index. MySQL has no native ANN index, so it falls back to full brute-force while returning the same result format.

## Project Structure

```
mimizam/
├── src/
│   ├── mimizam.py                    # Integrated high-level API
│   ├── audio_fingerprinter.py        # Audio fingerprint generation
│   ├── fingerprint_database.py       # Database management
│   ├── database_backends.py          # Unified backend
│   ├── adaptive_parameters.py        # Adaptive parameter adjustment
│   └── backends/                     # Individual backend implementations
│   ├── video_fingerprinter.py        # Video fingerprint generation (AKAZE+VLAD+PCA)
│   ├── video_database.py             # Video fingerprint database
│   ├── pip_detector.py               # PiP (picture-in-picture) rectangle detection
│   └── backends/                     # Individual backend implementations (sqlite/mysql/mariadb/postgresql/elasticsearch)
├── examples/
│   ├── mimizam_demo.py               # Audio API demo
│   ├── movie_fingerprinter.py        # Combined audio + video registration CLI
│   ├── movie_search.py               # Combined audio + video search CLI
│   ├── audio_from_video_fingerprinter.py        # Extract audio from video and register audio fingerprints
│   ├── audio_from_video_search.py               # Search by audio extracted from video
│   ├── visual_from_video_fingerprinter.py       # Register video (visual) fingerprints from video
│   └── visual_from_video_search.py              # Search by video (visual) fingerprints
├── model/                            # Pretrained codebook model
├── test_media/                       # Demo audio files
├── tests/                           # Test suite
├── docs/                            # Documentation
└── scripts/                         # Utilities (model training, DB migration, etc.)
```

## Use Cases

### Audio Search
```python
# Identify songs from short audio clips
results = mimizam.search_song("humming.wav", top_k=3)
```

### Custom Audio Loading

```python
import numpy as np

# Generate fingerprints from custom audio data
audio_data = np.array([...])  # Audio samples
fingerprints = fingerprinter.fingerprint_audio(audio_data, sr=22050)
```

### Audio Registration

```python
import glob
from pathlib import Path

# File registration processing
audio_files = glob.glob("music/*.wav")
with create_mimizam_sqlite("batch.db") as mimizam:
    for file_path in audio_files:
        title = Path(file_path).stem
        mimizam.add_song(file_path, title, "Unknown Artist")
```

### Visualization

```python
# Visualize spectrogram and peak detection
audio = fingerprinter.load_audio("song.wav")
fingerprinter.visualize_analysis(audio, title="song.wav")
```

### Custom Configuration

```python
# High-precision settings
fingerprinter = AudioFingerprinter(
    n_fft=4096,           # Higher frequency resolution
    hop_length=256,       # Finer time resolution
    min_amplitude=-50     # More sensitive detection
)
```

## Performance Tips

1. **Audio Quality**: Best results with high-quality audio (44.1kHz+)
2. **Sample Length**: Better identification accuracy with 10+ seconds
3. **Adaptive Parameters**: Use enable_adaptive_params=True for speedup
4. **Database Selection**: SQLite for small scale, PostgreSQL for large scale

## Testing

```bash
# Run all tests
python run_tests.py
```

## Documentation

Detailed documentation is included in the `docs/` directory:

- [Video Fingerprint Specification](docs/video_fingerprint_spec.md)
- [Database Setup](docs/DATABASE_SETUP.md)
- [Fingerprint Generation Details](docs/fingerprint_generation_details.md)
- [Fingerprint Scoring Details](docs/fingerprint_scoring_details.md)

## License

mimizam is released under the [MIT License](LICENSE).

## Acknowledgments

- [Avery Li-Chun Wang](https://www.ee.columbia.edu/~dpwe/papers/Wang03-shazam.pdf) for the original Shazam algorithm
- Audio processing library [librosa](https://librosa.org/)
- Inspiration from various open-source audio fingerprinting implementations
  - [dejavu GitHub](https://github.com/worldveil/dejavu)
  - [audfprint GitHub](https://github.com/dpwe/audfprint)

## References

- Wang, A. L. C. (2003). "An Industrial Strength Audio Search Algorithm"
- Ellis, D. P. W. (2009). "Robust Landmark-Based Audio Fingerprinting"
- Cano, P. et al. (2005). "A Review of Audio Fingerprinting"

---

**Note**: 
- This implementation was created as a personal hobby project. It does not guarantee performance equivalent to commercial systems.
- This README.md was automatically translated from README_JP.md. For the most accurate and up-to-date information, please refer to the original Japanese version.
