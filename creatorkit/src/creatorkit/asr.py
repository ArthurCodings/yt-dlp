"""本地语音识别（faster-whisper），自动使用 NVIDIA 显卡。"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from .subtitles import Segment, format_clock

_PROMPTS = {
    'hans': '以下是普通话内容的逐字稿，使用简体中文，并带有标点符号。',
    'hant': '以下是國語內容的逐字稿，使用繁體中文，並帶有標點符號。',
    'hk': '以下是內容的逐字稿，使用繁體中文，並帶有標點符號。',
    'keep': '以下是中文内容的逐字稿，带有标点符号。',
}


class ASRUnavailable(RuntimeError):
    pass


def _setup_cuda_dlls() -> None:
    """pip 装的 nvidia-cublas/cudnn 把 DLL 放在 site-packages/nvidia/*/bin，需手动加入搜索路径。"""
    if sys.platform != 'win32':
        return
    for pkg in ('nvidia.cublas', 'nvidia.cudnn', 'nvidia.cuda_nvrtc'):
        try:
            spec = importlib.util.find_spec(pkg)
        except ModuleNotFoundError:
            continue
        if not spec or not spec.submodule_search_locations:
            continue
        for loc in spec.submodule_search_locations:
            bin_dir = Path(loc) / 'bin'
            if bin_dir.is_dir():
                os.add_dll_directory(str(bin_dir))
                os.environ['PATH'] = str(bin_dir) + os.pathsep + os.environ.get('PATH', '')


def cuda_available() -> bool:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


class Transcriber:
    def __init__(self, model: str = 'large-v3-turbo', device: str = 'auto', compute_type: str = 'auto',
                 log=print):
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.log = log
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            _setup_cuda_dlls()
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise ASRUnavailable(
                '未安装语音识别组件。请运行：pip install -e "creatorkit[cuda]"（有 N 卡）或 "creatorkit[asr]"') from e

        device = self.device
        if device == 'auto':
            device = 'cuda' if cuda_available() else 'cpu'
        attempts = [(device, self.compute_type)]
        if device == 'cuda':
            attempts.append(('cpu', 'auto'))
        last_err = None
        for dev, ct in attempts:
            if ct == 'auto':
                ct = 'float16' if dev == 'cuda' else 'int8'
            try:
                self.log(f'  加载语音识别模型 {self.model_name}（{dev}/{ct}），首次使用会自动下载……')
                kwargs = {'cpu_threads': min(os.cpu_count() or 4, 16)} if dev == 'cpu' else {}
                self._model = WhisperModel(self.model_name, device=dev, compute_type=ct, **kwargs)
                self.device, self.compute_type = dev, ct
                return self._model
            except Exception as e:  # CUDA/cuDNN 不可用时退回 CPU
                last_err = e
                self.log(f'  {dev} 加载失败：{e}')
        raise ASRUnavailable(f'语音识别模型加载失败：{last_err}')

    def transcribe(self, media: Path, language: str | None = None, script: str = 'hans') -> tuple[list[Segment], str]:
        model = self._load()
        from faster_whisper import decode_audio

        audio = decode_audio(str(media))
        duration = len(audio) / 16000
        if not language:
            # 先判语种：中文才加提示词（提示词会让模型偏向中文，不能对外语用）
            _, probe = model.transcribe(audio, vad_filter=True)
            language = probe.language
            self.log(f'  检测到语言：{language}（置信度 {probe.language_probability:.0%}）')
        kwargs = {
            'language': language,
            'vad_filter': True,
            'beam_size': 5,
            'condition_on_previous_text': False,  # 减少长音频里的重复/幻听
        }
        if language in ('zh', 'yue'):
            kwargs['initial_prompt'] = _PROMPTS.get(script, _PROMPTS['keep'])
        segments_iter, _ = model.transcribe(audio, **kwargs)
        segments = []
        for s in segments_iter:
            text = s.text.strip()
            if text:
                segments.append(Segment(s.start, s.end, text))
            if duration:
                sys.stderr.write(f'\r  识别进度 {format_clock(s.end)} / {format_clock(duration)}'
                                 f'（{min(s.end / duration, 1):.0%}）')
                sys.stderr.flush()
        sys.stderr.write('\n')
        return segments, language
