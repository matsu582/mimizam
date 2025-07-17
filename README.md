# mimizam

**mimizam** is a Python implementation of Shazam-like algorithms for audio fingerprinting and identification. It generates unique fingerprints from audio and performs high-precision music identification by matching against a database.

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-73%25-yellowgreen.svg)]()

## Key Features

- **High-Precision Audio Fingerprinting**: Robust fingerprint generation based on Shazam algorithms
- **Adaptive Parameter Optimization**: Automatic parameter adjustment based on audio characteristics
- **Multi-Database Support**: SQLite, MySQL, PostgreSQL, Elasticsearch
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
3. **Hash-based Fingerprinting**: SHA-256 hash generation from anchor-target peak pairs
4. **Intelligent Matching**: Time alignment and confidence scoring

## Database Backends

mimizam supports multiple databases:

```python
from mimizam import (
    create_mimizam_sqlite,
    create_mimizam_mysql,
    create_mimizam_postgresql,
    create_mimizam_elasticsearch
)

# SQLite (Simple・Fast・Recommended)
mimizam = create_mimizam_sqlite("fingerprints.db")

# MySQL (Scalability)
mimizam = create_mimizam_mysql(
    host="localhost", database="music_db",
    username="user", password="pass"
)

# PostgreSQL (High Performance)
mimizam = create_mimizam_postgresql(
    host="localhost", database="music_db",
    username="user", password="pass"
)

# Elasticsearch (Distributed Search)
mimizam = create_mimizam_elasticsearch(
    host="localhost", index_name="music_index"
)
```

## Project Structure

```
mimizam/
├── src/
│   ├── mimizam.py                    # Integrated high-level API
│   ├── audio_fingerprinter.py        # Audio fingerprint generation
│   ├── fingerprint_database.py       # Database management
│   ├── database_backends.py          # Unified backend
│   ├── adaptive_parameters.py        # Adaptive parameter adjustment
│   ├── parallel_processing.py        # Parallel processing support
│   └── backends/                     # Individual backend implementations
├── examples/
│   ├── mimizam_demo.py               # API demo
│   ├── video_search.py               # Video audio search
│   └── video_fingerprinter.py        # Video audio processing
├── test_media/                       # Demo audio files
├── tests/                           # Test suite
├── docs/                            # Documentation
└── scripts/                         # Utilities
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
